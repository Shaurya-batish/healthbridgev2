"""Tests for the real ABDM Gateway client -- see docs/REAL-INTEGRATION-AUDIT.md.

No live network call is made or possible without real NHA credentials.
These tests verify (a) the client fails honestly when unconfigured, and
(b) the request-building logic (session-token flow, headers, discovery
body) matches the real published shape, using an httpx.MockTransport in
place of the real ABDM Gateway.
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret")

import httpx
import pytest

from app.adapters.abdm_client import (
    AbdmGatewayClient,
    AbdmNotConfiguredError,
    AbdmUnavailableError,
)
from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_fails_honestly_when_not_configured(monkeypatch):
    monkeypatch.delenv("ABDM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ABDM_GATEWAY_BASE_URL", raising=False)
    client = AbdmGatewayClient()

    with pytest.raises(AbdmNotConfiguredError):
        client.fetch_patient_bundle("12-3456-7890-1234")


def test_never_returns_a_bundle_when_unconfigured():
    """Regression guard: the old MockAbdmClient always returned a bundle. The real client must not."""
    client = AbdmGatewayClient()
    try:
        result = client.fetch_patient_bundle("11-1111-1111-1111")
    except AbdmNotConfiguredError:
        result = None
    assert result is None


def test_real_request_shape_against_mock_transport(monkeypatch):
    monkeypatch.setenv("ABDM_GATEWAY_BASE_URL", "https://abdm.example")
    monkeypatch.setenv("ABDM_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ABDM_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("ABDM_HIP_ID", "IN0000000001")
    get_settings.cache_clear()

    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.url.path == "/gateway/v3/sessions":
            body = request.read()
            assert b'"grantType":"client_credentials"' in body or b'"grantType": "client_credentials"' in body
            return httpx.Response(200, json={"accessToken": "fake-session-token", "expiresIn": 1200})
        if request.url.path == "/v0.5/patients/care-context/discover":
            assert request.headers["Authorization"] == "Bearer fake-session-token"
            assert request.headers["X-HIP-ID"] == "IN0000000001"
            assert "REQUEST-ID" in request.headers
            return httpx.Response(200, json={"resourceType": "Bundle", "entry": []})
        return httpx.Response(404)

    client = AbdmGatewayClient(transport=httpx.MockTransport(handler))
    bundle = client.fetch_patient_bundle("12-3456-7890-1234")

    assert bundle["resourceType"] == "Bundle"
    assert len(requests_seen) == 2
    assert requests_seen[0].url.path == "/gateway/v3/sessions"
    assert requests_seen[1].url.path == "/v0.5/patients/care-context/discover"


def test_gateway_error_raises_unavailable_not_a_fabricated_bundle(monkeypatch):
    monkeypatch.setenv("ABDM_GATEWAY_BASE_URL", "https://abdm.example")
    monkeypatch.setenv("ABDM_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ABDM_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("ABDM_HIP_ID", "IN0000000001")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = AbdmGatewayClient(transport=httpx.MockTransport(handler))
    with pytest.raises(AbdmUnavailableError):
        client.fetch_patient_bundle("12-3456-7890-1234")
