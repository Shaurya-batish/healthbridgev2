"""Diagnostics router tests.

`create_diagnostic_order` checks that the referenced Encounter exists,
which normally lives in a JSONB column -- not creatable on SQLite (see
conftest.py's module docstring). For the "encounter not found" 404 path we
only need the `encounters` table to exist and be empty, which a plain
CREATE TABLE gives us without touching the JSONB-typed ORM model. The
happy-path "encounter exists" branch of create_diagnostic_order is
therefore not covered here -- see docs/REAL-INTEGRATION-AUDIT.md. Every
other diagnostics endpoint (list/status/result) is tested against a
directly-inserted DiagnosticOrder row and is fully covered.
"""

import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import DiagnosticOrder


@pytest.fixture
def db_engine():
    engine = sa.create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    DiagnosticOrder.__table__.create(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE encounters (id TEXT PRIMARY KEY, patient_id TEXT, facility_id TEXT, fhir TEXT, created_at TIMESTAMP)"
        )
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
    yield TestClient(app), session_factory
    app.dependency_overrides.clear()


def test_create_diagnostic_order_404s_on_missing_encounter(client):
    http, _ = client
    res = http.post(
        "/diagnostics",
        json={"encounter_id": str(uuid.uuid4()), "facility_id": str(uuid.uuid4()), "test_name": "Malaria RDT"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "encounter_not_found"


def test_list_by_facility(client):
    http, session_factory = client
    facility_id = uuid.uuid4()
    with session_factory() as db:
        db.add(DiagnosticOrder(encounter_id=uuid.uuid4(), facility_id=facility_id, test_name="Hemoglobin"))
        db.commit()

    orders = http.get(f"/diagnostics/facility/{facility_id}").json()
    assert len(orders) == 1
    assert orders[0]["status"] == "ordered"


def test_status_update(client):
    http, session_factory = client
    with session_factory() as db:
        order = DiagnosticOrder(encounter_id=uuid.uuid4(), facility_id=uuid.uuid4(), test_name="Blood glucose")
        db.add(order)
        db.commit()
        order_id = order.id

    res = http.post(f"/diagnostics/{order_id}/status", json={"status": "in_progress"})
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress"


def test_recording_a_result_marks_completed(client):
    http, session_factory = client
    with session_factory() as db:
        order = DiagnosticOrder(encounter_id=uuid.uuid4(), facility_id=uuid.uuid4(), test_name="Malaria RDT")
        db.add(order)
        db.commit()
        order_id = order.id

    res = http.post(f"/diagnostics/{order_id}/result", json={"result_text": "Negative"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["result_text"] == "Negative"
    assert body["result_recorded_at"] is not None


def test_unknown_order_404s(client):
    http, _ = client
    res = http.post(f"/diagnostics/{uuid.uuid4()}/status", json={"status": "in_progress"})
    assert res.status_code == 404
