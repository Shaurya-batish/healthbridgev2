"""Regression test for the ABHA-uniqueness race condition found during the
2026-09-13 technical hardening pass: create_patient's "check, then insert"
pattern is a TOCTOU race -- two concurrent registrations for the same ABHA
number can both pass the pre-check before either commits, and the second
commit hits the DB's unique constraint. Before the fix, that IntegrityError
was unhandled and surfaced as a raw 500. Since `patients` uses a JSONB
column (Postgres-only, not creatable on SQLite -- see conftest.py's module
docstring), this test verifies the fix with a stub Session that reproduces
the exact failure the real unique constraint would raise, rather than
needing a live Postgres to actually race two connections.
"""

import os
import uuid

os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db import get_db
from app.main import app
from tests.conftest import auth_headers


class _FakeSession:
    """Minimal stand-in: the pre-check finds nothing (simulating the race
    window), but commit() raises IntegrityError (simulating the unique
    constraint firing on the concurrent duplicate)."""

    def scalar(self, *args, **kwargs):
        return None

    def add(self, *args, **kwargs):
        pass

    def commit(self):
        raise IntegrityError("INSERT INTO patients ...", {}, Exception("duplicate key value violates unique constraint"))

    def rollback(self):
        pass

    def refresh(self, *args, **kwargs):
        pass


def test_concurrent_duplicate_abha_returns_409_not_500():
    app.dependency_overrides[get_db] = lambda: _FakeSession()
    try:
        client = TestClient(app)
        client.headers.update(auth_headers())
        res = client.post(
            "/patients",
            json={
                "abha_number": "12-3456-7890-1234",
                "name": "Race Condition Patient",
                "dob": "2020-01-01",
                "gender": "female",
            },
        )
        assert res.status_code == 409
        assert res.json()["detail"] == "abha_number_already_registered"
    finally:
        app.dependency_overrides.clear()
