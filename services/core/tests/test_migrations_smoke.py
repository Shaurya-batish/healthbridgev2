"""Runs the real Alembic migrations against a real Postgres, then rolls the
newest ones back and forward again.

Why this exists: the rest of the suite builds most tables with
`model.__table__.create(engine)` against in-memory SQLite, so until
2026-09-13 nothing had ever executed `migrations/`. `alembic upgrade head`
failed on any clean database -- every postgresql.ENUM was pre-created with
`.create(checkfirst=True)` and then handed to `create_table`, which emits
CREATE TYPE a second time:

    psycopg2.errors.DuplicateObject: type "facility_level" already exists

The Postgres comes from DATABASE_URL when reachable, otherwise from a
throwaway `pgserver` instance (see conftest.pg_admin_url). It never touches
the application database.
"""
import sqlalchemy as sa

from tests.conftest import pg_url_string, run_alembic

EXPECTED_TABLES = {
    "alembic_version", "audit_log", "complaint_captures", "diagnostic_orders", "encounters",
    "escalation_events", "facilities", "follow_ups", "idempotency_keys",
    "medication_orders", "medicine_ingredients", "medicine_sources", "medicines",
    "medicine_stock", "medicine_stock_movements", "observations", "patients",
    "queue_tokens", "referrals", "substitution_requests", "teleconsults", "triage_records", "users",
}


def _tables(url) -> set[str]:
    engine = sa.create_engine(url)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_alembic_upgrade_head_on_a_clean_database(pg_migrated_url):
    target = pg_url_string(pg_migrated_url)
    missing = EXPECTED_TABLES - _tables(pg_migrated_url)
    assert not missing, f"migrations ran but these tables are missing: {sorted(missing)}"

    # Re-running must be a no-op, not a DuplicateObject.
    again = run_alembic(target, "upgrade", "head")
    assert again.returncode == 0, f"second upgrade head failed:\n{again.stdout}\n{again.stderr}"

    # The new migrations must be reversible and re-appliable.
    down = run_alembic(target, "downgrade", "0004")
    assert down.returncode == 0, f"downgrade to 0004 failed:\n{down.stdout}\n{down.stderr}"
    after_down = _tables(pg_migrated_url)
    assert not {"complaint_captures", "medicines", "substitution_requests"} & after_down
    engine = sa.create_engine(pg_migrated_url)
    try:
        assert "medicine_id" not in {c["name"] for c in sa.inspect(engine).get_columns("medicine_stock")}
    finally:
        engine.dispose()

    up = run_alembic(target, "upgrade", "head")
    assert up.returncode == 0, f"re-upgrade failed:\n{up.stdout}\n{up.stderr}"
    assert EXPECTED_TABLES <= _tables(pg_migrated_url)
