"""Tests for the idempotency-key replay cache -- see app/idempotency.py
and docs/TECHNICAL-HARDENING-REPORT.md's "no idempotency key" remaining
risk. `idempotency_keys` stores its response as TEXT (a JSON string), not
JSONB, specifically so this table -- unlike patients/encounters -- is
creatable on SQLite and this is a real, running test of the actual
dedup/replay/expiry logic, not just a description of intent.

Full end-to-end coverage through POST /patients|/encounters|/triage isn't
possible here (those tables use JSONB); this instead verifies the
mechanism those routers call directly.
"""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "test-secret")

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.idempotency import check_idempotency, record_idempotency
from app.models import IdempotencyKey


def _session():
    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    IdempotencyKey.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_no_key_never_touches_the_cache():
    db = _session()
    assert check_idempotency(db, None, "create_patient") is None
    record_idempotency(db, None, "create_patient", 201, {"id": "x"})
    db.commit()
    assert db.query(IdempotencyKey).count() == 0


def test_first_call_is_a_miss_second_call_with_same_key_replays_the_response():
    db = _session()
    key = "op-123"

    assert check_idempotency(db, key, "create_patient") is None

    record_idempotency(db, key, "create_patient", 201, {"abha_number": "12-3456-7890-1234"})
    db.commit()

    replayed = check_idempotency(db, key, "create_patient")
    assert replayed is not None
    assert replayed.status_code == 201
    assert replayed.body == b'{"abha_number":"12-3456-7890-1234"}'


def test_same_key_different_endpoint_is_a_separate_cache_entry():
    """The same client-generated id can legitimately be reused across the
    encounter and triage halves of one offline-queue operation (see
    apps/web/lib/offline-queue.ts) -- endpoint is part of the cache key so
    they never collide."""
    db = _session()
    key = "shared-op-id"

    record_idempotency(db, key, "create_encounter", 201, {"id": "encounter-1"})
    db.commit()

    assert check_idempotency(db, key, "submit_triage") is None
    record_idempotency(db, key, "submit_triage", 201, {"id": "triage-1"})
    db.commit()

    assert check_idempotency(db, key, "create_encounter").body == b'{"id":"encounter-1"}'
    assert check_idempotency(db, key, "submit_triage").body == b'{"id":"triage-1"}'


def test_expired_key_is_treated_as_a_miss():
    db = _session()
    key = "old-op"
    db.add(
        IdempotencyKey(
            idempotency_key=key,
            endpoint="create_patient",
            response_status=201,
            response_body='{"id":"stale"}',
            created_at=datetime.now(timezone.utc) - timedelta(hours=48),
        )
    )
    db.commit()

    assert check_idempotency(db, key, "create_patient") is None
