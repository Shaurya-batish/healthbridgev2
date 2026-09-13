"""Real ABDM Gateway (HIP-side) client -- see docs/REAL-INTEGRATION-AUDIT.md.

This replaces the former `MockAbdmClient`, which fabricated deterministic
fake FHIR bundles and never touched a network. Per the 2026-09-13 "no mock
features" policy: this client builds and sends the *real* request shapes
documented for the ABDM Gateway (session-token acquisition, the required
header set, the care-context discovery call) against a configurable base
URL. It requires real NHA-issued credentials that this project does not
have (HIP registration, bridge-portal clientId/clientSecret, a registered
HIP_ID -- see the audit doc for the full registration path). Without them,
every call fails honestly. Nothing in this module ever returns a
fabricated bundle.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.config import get_settings


class AbdmClient(Protocol):
    def fetch_patient_bundle(self, abha_number: str) -> dict:
        """Return a FHIR Bundle for the given ABHA number."""
        ...


class AbdmNotConfiguredError(Exception):
    """ABDM_CLIENT_ID/SECRET/HIP_ID/base URL are not set.

    Callers must surface this to the caller as a clear "not connected"
    signal (see app/routers/abdm.py) -- never substitute a fabricated bundle.
    """


class AbdmUnavailableError(Exception):
    """ABDM is configured but the real Gateway call failed (network, auth, or Gateway-side error)."""


class AbdmGatewayClient:
    """Real HIP-side ABDM Gateway client. The only concrete `AbdmClient` implementation."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        # `transport` lets tests inject an httpx.MockTransport to verify the
        # real request shape without a network call -- this is what "test
        # everything possible without credentials" means for this adapter.
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _require_config(self):
        settings = get_settings()
        if not (
            settings.abdm_gateway_base_url
            and settings.abdm_client_id
            and settings.abdm_client_secret
            and settings.abdm_hip_id
        ):
            raise AbdmNotConfiguredError(
                "ABDM_GATEWAY_BASE_URL / ABDM_CLIENT_ID / ABDM_CLIENT_SECRET / ABDM_HIP_ID are not set. "
                "Real ABDM access requires NHA HIP registration and certification -- "
                "see docs/REAL-INTEGRATION-AUDIT.md for the exact steps and credentials required."
            )
        return settings

    def _client(self, base_url: str) -> httpx.Client:
        return httpx.Client(base_url=base_url, transport=self._transport, timeout=10.0)

    def _get_session_token(self, settings) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        try:
            with self._client(settings.abdm_gateway_base_url) as client:
                res = client.post(
                    "/gateway/v3/sessions",
                    json={
                        "clientId": settings.abdm_client_id,
                        "clientSecret": settings.abdm_client_secret,
                        "grantType": "client_credentials",
                    },
                )
                res.raise_for_status()
        except httpx.HTTPError as exc:
            raise AbdmUnavailableError(f"ABDM session token request failed: {exc}") from exc

        body = res.json()
        self._token = body["accessToken"]
        # Real ABDM guidance: refresh 30s before the token's stated expiry.
        self._token_expires_at = time.monotonic() + max(body.get("expiresIn", 1200) - 30, 0)
        return self._token

    def _headers(self, token: str, settings) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "REQUEST-ID": str(uuid.uuid4()),
            "TIMESTAMP": datetime.now(timezone.utc).isoformat(),
            "X-CM-ID": settings.abdm_cm_id,
            "X-HIP-ID": settings.abdm_hip_id,
            "Content-Type": "application/json",
        }

    def fetch_patient_bundle(self, abha_number: str) -> dict:
        """Real care-context discovery request against the ABDM Gateway.

        Raises `AbdmNotConfiguredError` (no credentials configured) or
        `AbdmUnavailableError` (configured but the call failed) -- never
        returns a fabricated bundle.
        """
        settings = self._require_config()
        token = self._get_session_token(settings)

        try:
            with self._client(settings.abdm_gateway_base_url) as client:
                res = client.post(
                    "/v0.5/patients/care-context/discover",
                    json={
                        "requestId": str(uuid.uuid4()),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "patient": {"id": abha_number},
                    },
                    headers=self._headers(token, settings),
                )
                res.raise_for_status()
        except httpx.HTTPError as exc:
            raise AbdmUnavailableError(f"ABDM care-context discovery failed: {exc}") from exc

        return res.json()
