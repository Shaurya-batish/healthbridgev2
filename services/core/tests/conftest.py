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

import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import (
    AuditLog,
    DiagnosticOrder,
    FollowUp,
    Medicine,
    MedicineIngredient,
    MedicineSource,
    MedicineStock,
    MedicineStockMovement,
    Referral,
    Teleconsult,
)
from app.security import create_access_token

NEW_MODELS = (
    Referral,
    DiagnosticOrder,
    MedicineSource,
    Medicine,
    MedicineIngredient,
    MedicineStock,
    MedicineStockMovement,
    FollowUp,
    Teleconsult,
    AuditLog,
)

CORE_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
_DEFAULT_PG_URL = "postgresql://healthbridge:healthbridge@localhost:5432/healthbridge"


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


# --- Real PostgreSQL (for JSONB tables, migrations, row locks) ----------------
#
# Uses DATABASE_URL's server if reachable; otherwise starts a throwaway local
# PostgreSQL via the `pgserver` wheel (requirements-dev.txt) so these tests run
# without Docker. Skipped only when neither is available. Never touches the
# application database: a scratch database is created and dropped.


def pg_url_string(url) -> str:
    return url.render_as_string(hide_password=False)


def _pg_reachable(url) -> bool:
    engine = sa.create_engine(url, connect_args={"connect_timeout": 2})
    try:
        with engine.connect():
            return True
    except Exception:
        return False
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def pg_admin_url():
    configured = make_url(os.environ.get("DATABASE_URL", _DEFAULT_PG_URL))
    if configured.get_backend_name() == "postgresql" and _pg_reachable(configured.set(database="postgres")):
        yield configured.set(database="postgres")
        return
    try:
        import pgserver
    except ImportError:
        pytest.skip("no reachable PostgreSQL and pgserver is not installed (pip install -r requirements-dev.txt)")
    server = pgserver.get_server(tempfile.mkdtemp(prefix="hb-pg-"), cleanup_mode="delete")
    try:
        yield make_url(server.get_uri())
    finally:
        server.cleanup()


def run_alembic(url_string: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=CORE_DIR,
        env={**os.environ, "DATABASE_URL": url_string},
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session")
def pg_migrated_url(pg_admin_url):
    admin = sa.create_engine(pg_admin_url, isolation_level="AUTOCOMMIT")
    scratch = f"hb_test_{uuid.uuid4().hex[:8]}"
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{scratch}"'))
    target = pg_admin_url.set(database=scratch)
    try:
        up = run_alembic(pg_url_string(target), "upgrade", "head")
        assert up.returncode == 0, f"alembic upgrade head failed:\n{up.stdout}\n{up.stderr}"
        yield target
    finally:
        with admin.connect() as conn:
            conn.execute(sa.text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :d"), {"d": scratch})
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{scratch}"'))
        admin.dispose()


@pytest.fixture
def pg_engine(pg_migrated_url):
    engine = sa.create_engine(pg_migrated_url)
    with engine.begin() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'")
            )
        ]
        conn.execute(sa.text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))
    yield engine
    engine.dispose()


@pytest.fixture
def pg_client(pg_engine):
    session_factory = sessionmaker(bind=pg_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
