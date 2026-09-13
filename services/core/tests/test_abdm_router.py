"""Router-level test for GET /abdm/patient/{abha_number} -- no DB involved,
so a real FastAPI TestClient call works without any test-only setup. Confirms
the honest status codes reach the HTTP layer, not just the adapter."""

import os

os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_unconfigured_abdm_returns_501_not_a_bundle(monkeypatch):
    monkeypatch.delenv("ABDM_CLIENT_ID", raising=False)
    get_settings.cache_clear()

    client = TestClient(app)
    res = client.get("/abdm/patient/12-3456-7890-1234", headers=auth_headers())

    assert res.status_code == 501
    assert res.json()["detail"] == "abdm_not_configured"


def test_unauthenticated_request_is_rejected(monkeypatch):
    monkeypatch.delenv("ABDM_CLIENT_ID", raising=False)
    get_settings.cache_clear()

    client = TestClient(app)
    res = client.get("/abdm/patient/12-3456-7890-1234")

    assert res.status_code == 401
