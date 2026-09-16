"""Real-Postgres tests for prescribing and doctor-authorised substitution:
role and facility enforcement, state transitions, stale-prescription
invalidation, duplicate requests, audit persistence, and concurrent approval
under real row locks. Medicines come from the SYNTHETIC fixture."""
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import AuditLog, MedicationOrder, SubstitutionRequest
from tests.medicine_helpers import import_synthetic, medicine_by_record
from tests.pg_seed import seed_world


@pytest.fixture
def world(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    w = seed_world(session)
    import_synthetic(session)
    w.med = {rid: medicine_by_record(session, rid).id for rid in ("1", "2", "3", "4", "5", "8")}
    session.close()
    return w


def _order(client, w, medicine_record="1", user="doctor_a"):
    return client.post(
        "/medication-orders",
        json={"encounter_id": str(w.encounter), "medicine_id": str(w.med[medicine_record]), "instructions": "1 tablet three times a day for 3 days"},
        headers=w.headers(user),
    )


def _request(client, w, order_id, proposed="2", user="asha_a"):
    return client.post(
        "/substitution-requests",
        json={"order_id": order_id, "proposed_medicine_id": str(w.med[proposed]), "note": "cheaper option in stock"},
        headers=w.headers(user),
    )


def test_only_doctors_at_the_encounter_facility_can_prescribe(pg_client, world):
    assert _order(pg_client, world, user="asha_a").status_code == 403
    assert _order(pg_client, world, user="admin").json()["detail"] == "clinician_role_required"
    assert _order(pg_client, world, user="doctor_b").json()["detail"] == "facility_access_denied"
    assert _order(pg_client, world, medicine_record="8").json()["detail"] == "medicine_discontinued"
    res = _order(pg_client, world)
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "active" and res.json()["version"] == 1


def test_request_does_not_change_the_prescription(pg_client, pg_engine, world):
    order = _order(pg_client, world).json()
    req = _request(pg_client, world, order["id"])
    assert req.status_code == 201, req.text
    assert req.json()["status"] == "pending"

    current = pg_client.get(f"/medication-orders/{order['id']}", headers=world.headers("asha_a")).json()
    assert current["status"] == "active" and current["medicine"]["id"] == str(world.med["1"])

    dup = _request(pg_client, world, order["id"])
    assert dup.status_code == 409 and dup.json()["request_id"] == req.json()["id"]

    assert _request(pg_client, world, order["id"], proposed="5").json()["detail"] == "not_a_same_composition_match"  # 500mg
    assert _request(pg_client, world, order["id"], user="doctor_b").status_code == 403


def test_asha_and_admin_cannot_approve_and_other_facility_doctor_cannot_either(pg_client, world):
    order = _order(pg_client, world).json()
    req_id = _request(pg_client, world, order["id"]).json()["id"]
    for user, detail in (("asha_a", "clinician_role_required"), ("admin", "clinician_role_required"), ("doctor_b", "facility_access_denied")):
        res = pg_client.post(f"/substitution-requests/{req_id}/approve", json={}, headers=world.headers(user))
        assert res.status_code == 403 and res.json()["detail"] == detail
    pending = pg_client.get(f"/substitution-requests/facility/{world.facility_a}?status=pending", headers=world.headers("doctor_a")).json()
    assert [r["id"] for r in pending] == [req_id]


def test_doctor_approval_supersedes_the_order_through_the_prescribing_path_and_is_audited(pg_client, pg_engine, world):
    order = _order(pg_client, world).json()
    req_id = _request(pg_client, world, order["id"]).json()["id"]

    res = pg_client.post(f"/substitution-requests/{req_id}/approve", json={"decision_note": "ok, same composition"}, headers=world.headers("doctor_a"))
    assert res.status_code == 200, res.text
    approved = res.json()
    assert approved["status"] == "approved" and approved["reviewed_by_user_id"] == str(world.doctor_a)

    new_order = pg_client.get(f"/medication-orders/{approved['resulting_order_id']}", headers=world.headers("doctor_a")).json()
    assert new_order["medicine"]["id"] == str(world.med["2"])
    assert new_order["version"] == 2 and new_order["supersedes_order_id"] == order["id"]
    assert new_order["instructions"] == order["instructions"]  # no dose conversion
    old = pg_client.get(f"/medication-orders/{order['id']}", headers=world.headers("doctor_a")).json()
    assert old["status"] == "superseded"

    again = pg_client.post(f"/substitution-requests/{req_id}/approve", json={}, headers=world.headers("doctor_a"))
    assert again.status_code == 409 and again.json()["detail"] == "substitution_request_not_pending"

    s = sessionmaker(bind=pg_engine)()
    actions = sorted(a for (a,) in s.execute(select(AuditLog.action).where(AuditLog.entity_type.in_(["substitution_request", "medication_order"]))))
    assert actions == ["medication_order_created", "medication_order_superseded", "substitution_approved", "substitution_requested"]
    s.close()


def test_rejection_leaves_the_prescription_untouched(pg_client, world):
    order = _order(pg_client, world).json()
    req_id = _request(pg_client, world, order["id"]).json()["id"]
    res = pg_client.post(f"/substitution-requests/{req_id}/reject", json={"decision_note": "patient tolerates current brand"}, headers=world.headers("doctor_a"))
    assert res.status_code == 200 and res.json()["status"] == "rejected"
    current = pg_client.get(f"/medication-orders/{order['id']}", headers=world.headers("doctor_a")).json()
    assert current["status"] == "active" and current["version"] == 1
    assert pg_client.post(f"/substitution-requests/{req_id}/reject", json={}, headers=world.headers("doctor_a")).status_code == 409


def test_stale_prescription_invalidates_other_pending_requests(pg_client, pg_engine, world):
    order = _order(pg_client, world).json()
    first = _request(pg_client, world, order["id"], proposed="2").json()["id"]
    second = _request(pg_client, world, order["id"], proposed="3").json()["id"]

    assert pg_client.post(f"/substitution-requests/{first}/approve", json={}, headers=world.headers("doctor_a")).status_code == 200
    stale = pg_client.post(f"/substitution-requests/{second}/approve", json={}, headers=world.headers("doctor_a"))
    assert stale.status_code == 409 and stale.json()["detail"] == "prescription_changed_since_request"

    s = sessionmaker(bind=pg_engine)()
    row = s.get(SubstitutionRequest, uuid.UUID(second))
    assert row.status == "invalidated"
    assert s.scalar(select(func.count()).select_from(MedicationOrder).where(MedicationOrder.status == "active")) == 1
    s.close()


def test_concurrent_approvals_produce_exactly_one_prescription_change(pg_engine, world):
    from app.db import get_db

    factory = sessionmaker(bind=pg_engine, autoflush=False)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        order = _order(client, world).json()
        req_id = _request(client, world, order["id"]).json()["id"]

        results = []
        barrier = threading.Barrier(2)

        def approve():
            c = TestClient(app)
            barrier.wait()
            results.append(c.post(f"/substitution-requests/{req_id}/approve", json={}, headers=world.headers("doctor_a")).status_code)

        threads = [threading.Thread(target=approve) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(results) == [200, 409]

        s = factory()
        assert s.scalar(select(func.count()).select_from(MedicationOrder)) == 2  # original + exactly one replacement
        assert s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "substitution_approved")) == 1
        s.close()
    finally:
        app.dependency_overrides.clear()
