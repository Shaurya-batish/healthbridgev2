"""Runs the real Alembic migrations against a real Postgres, then rolls them
back.

Why this exists: the rest of the suite builds its tables with
`model.__table__.create(engine)` against in-memory SQLite, so until
2026-09-13 nothing had ever executed `migrations/`. `alembic upgrade head`
failed on any clean database -- every postgresql.ENUM was pre-created with
`.create(checkfirst=True)` and then handed to `create_table`, which emits
CREATE TYPE a second time:

    psycopg2.errors.DuplicateObject: type "facility_level" already exists

The schema could not be created at all, and no test could see it.

The test is skipped when no Postgres is reachable, so it stays harmless in a
SQLite-only environment. It never touches the application database: it
creates its own throwaway database and drops it again.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

CORE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_URL = "postgresql://healthbridge:healthbridge@localhost:5432/healthbridge"

EXPECTED_TABLES = {
    "alembic_version", "audit_log", "diagnostic_orders", "encounters",
    "escalation_events", "facilities", "follow_ups", "idempotency_keys",
    "medicine_stock", "medicine_stock_movements", "observations", "patients",
    "queue_tokens", "referrals", "teleconsults", "triage_records", "users",
}


def _admin_url():
    url = make_url(os.environ.get("DATABASE_URL", DEFAULT_URL))
    return url.set(database="postgres")


def _postgres_available(url) -> bool:
    try:
        engine = sa.create_engine(url, connect_args={"connect_timeout": 2})
        with engine.connect():
            return True
    except Exception:
        return False
    finally:
        try:
            engine.dispose()
        except Exception:
            pass


@pytest.mark.skipif(
    not _postgres_available(_admin_url()),
    reason="no reachable Postgres; migrations can only be smoke-tested against the real engine",
)
def test_alembic_upgrade_head_on_a_clean_database():
    admin = sa.create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    scratch = f"hb_migration_smoke_{uuid.uuid4().hex[:8]}"
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{scratch}"'))
    try:
        target = str(_admin_url().set(database=scratch))
        env = {**os.environ, "DATABASE_URL": target}
        up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=CORE_DIR, env=env, capture_output=True, text=True
        )
        assert up.returncode == 0, f"alembic upgrade head failed:\n{up.stdout}\n{up.stderr}"

        engine = sa.create_engine(target)
        try:
            found = set(sa.inspect(engine).get_table_names())
        finally:
            engine.dispose()
        missing = EXPECTED_TABLES - found
        assert not missing, f"migrations ran but these tables are missing: {sorted(missing)}"

        # Re-running must be a no-op, not a DuplicateObject.
        again = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=CORE_DIR, env=env, capture_output=True, text=True
        )
        assert again.returncode == 0, f"second upgrade head failed:\n{again.stdout}\n{again.stderr}"
    finally:
        with admin.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :d"
                ),
                {"d": scratch},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{scratch}"'))
        admin.dispose()
