"""Shared fixtures for router-level tests against the new real internal
workflows (referrals/diagnostics/medicine-stock/follow-ups/teleconsults).

These six tables don't use Postgres-only JSONB (unlike patients/encounters/
observations), so a real insert/query round trip against an in-memory
SQLite database is possible and meaningful -- this is genuine test
coverage of the router logic, not a fake pass. Patient/Encounter/Facility
rows are never created in these tests (their tables use JSONB, which
SQLite can't compile) -- tests that need a foreign id just use a random
UUID, since none of the new routers dereference those tables except
diagnostics.py's encounter-existence check, handled separately in its own
test file.
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret")

import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import DiagnosticOrder, FollowUp, MedicineStock, MedicineStockMovement, Referral, Teleconsult
from app.security import create_access_token

NEW_MODELS = (Referral, DiagnosticOrder, MedicineStock, MedicineStockMovement, FollowUp, Teleconsult)


def mint_token(role: str = "admin", facility_id: uuid.UUID | None = None) -> str:
    """Mints a real JWT the same way Core's own /auth/login does (same
    function, same secret) -- no DB/user row needed since
    create_access_token is pure. Default role is admin so the bulk of the
    functional test suite (business logic, not authorization) can keep
    using arbitrary random facility ids without every call needing to
    match one fixed facility -- admin intentionally bypasses the
    facility-scoping check (see app/security.py::require_facility_access).
    Authorization itself is regression-tested separately in
    test_authorization.py with non-admin roles."""
    return create_access_token(uuid.uuid4(), role, facility_id)


def auth_headers(role: str = "admin", facility_id: uuid.UUID | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_token(role, facility_id)}"}


@pytest.fixture
def db_engine():
    # StaticPool: an in-memory SQLite DB is connection-local, so without a
    # single shared connection every new Session would see an empty
    # database -- this is what actually makes the tables created below
    # visible to the router's own DB session later.
    engine = sa.create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for model in NEW_MODELS:
        model.__table__.create(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(db_engine):
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    test_client.headers.update(auth_headers())  # admin by default -- see mint_token docstring
    yield test_client
    app.dependency_overrides.clear()
