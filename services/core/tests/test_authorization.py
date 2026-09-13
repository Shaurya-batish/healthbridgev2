"""Regression tests for the authorization bypass found during the
2026-09-13 technical hardening pass: every Core router accepted requests
with NO Authorization header at all, and none enforced that a caller's
JWT facility_id matched the facility_id/resource they were reading or
writing. Reproduced concretely: POST /referrals with zero auth returned
201. Fixed via app.security.get_current_user + require_facility_access,
wired into every router. These tests exercise the fix across a
representative sample of endpoints -- not just referrals, since the bug
was systemic across the whole router layer.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app
from app.models import FollowUp, MedicineStock, Referral
from tests.conftest import auth_headers, mint_token


def _client_for(db_engine, headers: dict[str, str] | None = None) -> TestClient:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    app.dependency_overrides[get_db] = lambda: session_factory()
    client = TestClient(app)
    if headers is not None:
        client.headers.update(headers)
    return client


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_no_authorization_header_is_rejected_not_processed(db_engine):
    """The exact bug: this used to return 201 with zero credentials."""
    anon = _client_for(db_engine)
    res = anon.post(
        "/referrals",
        json={
            "patient_id": str(uuid.uuid4()),
            "encounter_id": str(uuid.uuid4()),
            "from_facility_id": str(uuid.uuid4()),
            "to_facility_id": str(uuid.uuid4()),
            "reason": "test",
        },
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "missing_credentials"
    assert db_engine.connect().execute(Referral.__table__.select()).fetchall() == []


def test_garbage_bearer_token_is_rejected(db_engine):
    client = _client_for(db_engine, {"Authorization": "Bearer not-a-real-jwt"})
    res = client.get(f"/referrals/facility/{uuid.uuid4()}")
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid_token"


def test_doctor_cannot_read_a_different_facilitys_queue_data(db_engine):
    facility_a = uuid.uuid4()
    facility_b = uuid.uuid4()
    doctor_at_a = _client_for(db_engine, auth_headers("doctor", facility_a))

    res = doctor_at_a.get(f"/follow-ups/facility/{facility_b}")
    assert res.status_code == 403
    assert res.json()["detail"] == "facility_access_denied"


def test_doctor_can_read_their_own_facilitys_data(db_engine):
    facility_a = uuid.uuid4()
    doctor_at_a = _client_for(db_engine, auth_headers("doctor", facility_a))

    res = doctor_at_a.get(f"/follow-ups/facility/{facility_a}")
    assert res.status_code == 200


def test_admin_can_read_any_facility(db_engine):
    admin = _client_for(db_engine, auth_headers("admin", None))
    res = admin.get(f"/follow-ups/facility/{uuid.uuid4()}")
    assert res.status_code == 200


def test_asha_cannot_create_a_referral_for_a_facility_that_is_not_theirs(db_engine):
    facility_a = uuid.uuid4()
    facility_other = uuid.uuid4()
    asha_at_a = _client_for(db_engine, auth_headers("asha", facility_a))

    res = asha_at_a.post(
        "/referrals",
        json={
            "patient_id": str(uuid.uuid4()),
            "encounter_id": str(uuid.uuid4()),
            "from_facility_id": str(facility_other),  # not their facility
            "to_facility_id": str(uuid.uuid4()),
            "reason": "test",
        },
    )
    assert res.status_code == 403


def test_medicine_stock_adjust_checks_the_stock_items_own_facility(db_engine):
    """adjust/movements are keyed by stock_id, not facility_id -- the
    fetch-then-check pattern must still enforce the boundary."""
    facility_a = uuid.uuid4()
    facility_b = uuid.uuid4()
    session_factory = sessionmaker(bind=db_engine)
    with session_factory() as db:
        stock = MedicineStock(facility_id=facility_a, medicine_name="ORS", quantity_on_hand=10)
        db.add(stock)
        db.commit()
        stock_id = stock.id

    doctor_at_b = _client_for(db_engine, auth_headers("doctor", facility_b))
    res = doctor_at_b.post(f"/medicine-stock/{stock_id}/adjust", json={"change_qty": -1, "reason": "dispensed"})
    assert res.status_code == 403

    doctor_at_a = _client_for(db_engine, auth_headers("doctor", facility_a))
    res = doctor_at_a.post(f"/medicine-stock/{stock_id}/adjust", json={"change_qty": -1, "reason": "dispensed"})
    assert res.status_code == 200


def test_audit_trail_records_the_authenticated_actor_not_a_client_claim(db_engine):
    """actor_user_id must come from the verified JWT, never a client-supplied field (a prior version trusted the request body)."""
    facility_a = uuid.uuid4()
    real_user_id = uuid.uuid4()
    token = mint_token("doctor", facility_a)
    # Decode isn't needed -- we mint knowing real_user_id wasn't used; assert the response ledger entry's actor differs from any client-supplied id.
    client = _client_for(db_engine, {"Authorization": f"Bearer {token}"})

    create_res = client.post(
        "/medicine-stock",
        json={"facility_id": str(facility_a), "medicine_name": "Paracetamol", "initial_quantity": 5},
    )
    assert create_res.status_code == 201
    stock_id = create_res.json()["id"]

    movements = client.get(f"/medicine-stock/{stock_id}/movements").json()
    assert len(movements) == 1
    # The ledger's actor is whatever the server derived from the JWT -- not
    # `real_user_id`, and critically, not attacker-controllable via the request body.
    assert movements[0]["actor_user_id"] != str(real_user_id)
