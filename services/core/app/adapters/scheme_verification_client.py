"""Real PM-JAY / state-scheme verification client -- see docs/REAL-INTEGRATION-AUDIT.md.

Before this pass, `patients.scheme_status` was just a value the ASHA typed
in at registration, displayed as if it meant something was verified. It
wasn't -- there was no verification call at all. This module is the real
adapter shape for PM-JAY's Beneficiary Identification System (BIS), gated
on NHA hospital-empanelment operator credentials this project does not
have. Without them, every call fails honestly with
`SchemeVerificationNotConfiguredError`; nothing here fabricates a
"verified" result.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal, Protocol

import httpx

from app.config import get_settings

VerificationResult = Literal["verified", "failed"]


class SchemeVerificationClient(Protocol):
    def verify_beneficiary(self, abha_number: str, scheme_status: str) -> VerificationResult: ...


class SchemeVerificationNotConfiguredError(Exception):
    """NHA operator credentials are not set. Callers must surface this as `unverified`, never as a fabricated `verified`."""


class SchemeVerificationUnavailableError(Exception):
    """Configured but the real NHA BIS call failed."""


class NhaBeneficiaryClient:
    """Real PM-JAY Beneficiary Identification System (BIS) operator-side client."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _require_config(self):
        settings = get_settings()
        if not (settings.nha_beneficiary_base_url and settings.nha_operator_username and settings.nha_operator_password):
            raise SchemeVerificationNotConfiguredError(
                "NHA_BENEFICIARY_BASE_URL / NHA_OPERATOR_USERNAME / NHA_OPERATOR_PASSWORD are not set. "
                "Real PM-JAY verification requires NHA hospital empanelment -- "
                "see docs/REAL-INTEGRATION-AUDIT.md."
            )
        return settings

    def verify_beneficiary(self, abha_number: str, scheme_status: str) -> VerificationResult:
        settings = self._require_config()

        try:
            with httpx.Client(base_url=settings.nha_beneficiary_base_url, transport=self._transport, timeout=10.0) as client:
                res = client.post(
                    "/api/beneficiary/verify",
                    json={
                        "requestId": str(uuid.uuid4()),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "identifier": {"type": "abha_number", "value": abha_number},
                        "scheme": scheme_status,
                    },
                    auth=(settings.nha_operator_username, settings.nha_operator_password),
                )
                res.raise_for_status()
        except httpx.HTTPError as exc:
            raise SchemeVerificationUnavailableError(f"NHA BIS verification call failed: {exc}") from exc

        body = res.json()
        return "verified" if body.get("eligible") else "failed"
