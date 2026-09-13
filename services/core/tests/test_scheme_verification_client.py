"""Tests for the real PM-JAY/scheme verification client -- see docs/REAL-INTEGRATION-AUDIT.md.

No live network call is made or possible without real NHA operator
credentials. Verifies (a) honest failure when unconfigured, and (b) the
real request shape (operator basic auth, body fields) via httpx.MockTransport.
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret")

import httpx
import pytest

from app.adapters.scheme_verification_client import (
    NhaBeneficiaryClient,
    SchemeVerificationNotConfiguredError,
    SchemeVerificationUnavailableError,
)
from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_fails_honestly_when_not_configured(monkeypatch):
    monkeypatch.delenv("NHA_BENEFICIARY_BASE_URL", raising=False)
    client = NhaBeneficiaryClient()
    with pytest.raises(SchemeVerificationNotConfiguredError):
        client.verify_beneficiary("12-3456-7890-1234", "PMJAY")


def test_real_request_shape_against_mock_transport(monkeypatch):
    monkeypatch.setenv("NHA_BENEFICIARY_BASE_URL", "https://bis.example")
    monkeypatch.setenv("NHA_OPERATOR_USERNAME", "op-user")
    monkeypatch.setenv("NHA_OPERATOR_PASSWORD", "op-pass")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/beneficiary/verify"
        assert "Authorization" in request.headers  # basic auth from operator creds
        return httpx.Response(200, json={"eligible": True})

    client = NhaBeneficiaryClient(transport=httpx.MockTransport(handler))
    result = client.verify_beneficiary("12-3456-7890-1234", "PMJAY")
    assert result == "verified"


def test_ineligible_response_yields_failed_not_verified(monkeypatch):
    monkeypatch.setenv("NHA_BENEFICIARY_BASE_URL", "https://bis.example")
    monkeypatch.setenv("NHA_OPERATOR_USERNAME", "op-user")
    monkeypatch.setenv("NHA_OPERATOR_PASSWORD", "op-pass")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"eligible": False})

    client = NhaBeneficiaryClient(transport=httpx.MockTransport(handler))
    result = client.verify_beneficiary("12-3456-7890-1234", "PMJAY")
    assert result == "failed"


def test_gateway_error_raises_unavailable(monkeypatch):
    monkeypatch.setenv("NHA_BENEFICIARY_BASE_URL", "https://bis.example")
    monkeypatch.setenv("NHA_OPERATOR_USERNAME", "op-user")
    monkeypatch.setenv("NHA_OPERATOR_PASSWORD", "op-pass")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = NhaBeneficiaryClient(transport=httpx.MockTransport(handler))
    with pytest.raises(SchemeVerificationUnavailableError):
        client.verify_beneficiary("12-3456-7890-1234", "PMJAY")
