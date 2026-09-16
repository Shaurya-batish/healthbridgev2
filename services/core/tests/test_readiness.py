from fastapi.testclient import TestClient

from app.main import app
from app.routers import health


def test_readiness_fails_when_database_is_unavailable(monkeypatch):
    monkeypatch.setattr(health, "db_reachable", lambda: False)
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert response.headers["cache-control"] == "no-store"


def test_readiness_does_not_depend_on_ai_or_redis(monkeypatch):
    monkeypatch.setattr(health, "db_reachable", lambda: True)
    monkeypatch.setattr(health, "redis_reachable", lambda: False)
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
