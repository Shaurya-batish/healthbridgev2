"""Regression tests for input validation that was absent until the
2026-09-13 QA pass.

Every case below was accepted by the API before that pass. They are asserted
at the schema level (422 from Pydantic, raised before the router touches the
database), so they run against the shared in-memory SQLite fixture without
needing the JSONB-backed tables.
"""
import uuid

import pytest


def _patient_body(**overrides):
    body = {
        "abha_number": "12-3456-7890-1234",
        "name": "Test Patient",
        "dob": "2020-01-01",
        "gender": "female",
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"abha_number": ""}, "empty ABHA number"),
        ({"abha_number": "   "}, "whitespace-only ABHA number"),
        ({"name": ""}, "empty name"),
        ({"name": "   "}, "whitespace-only name"),
        ({"name": "N" * 500}, "overlong name"),
        ({"dob": ""}, "empty date of birth"),
        ({"dob": "not-a-date"}, "unparseable date of birth"),
        ({"dob": "2020-13-45"}, "impossible calendar date"),
        ({"gender": "banana"}, "gender outside the FHIR value set"),
        ({"abha_number": "1" * 100}, "overlong ABHA number"),
    ],
)
def test_patient_create_rejects_garbage_identity(client, overrides, reason):
    """The ABHA number is the longitudinal key the whole data model hangs off
    (CLAUDE.md §Data model); a blank or unparseable identity must never be
    storable."""
    res = client.post("/patients", json=_patient_body(**overrides))
    assert res.status_code == 422, f"{reason} was accepted: {res.status_code} {res.text[:200]}"


def test_patient_create_accepts_a_valid_identity_shape():
    """Guards against over-tightening: the canonical body must still pass
    schema validation. Asserted directly on the model rather than through the
    route, because patients/ uses JSONB tables the SQLite fixture cannot
    create."""
    from app.schemas import PatientCreateRequest

    parsed = PatientCreateRequest(**_patient_body())
    assert parsed.abha_number == "12-3456-7890-1234"
    assert parsed.gender == "female"


@pytest.mark.parametrize(
    "test_name,reason",
    [("", "empty test name"), ("   ", "whitespace-only test name"), ("Z" * 500, "overlong test name")],
)
def test_diagnostic_order_rejects_bad_test_name(client, test_name, reason):
    res = client.post(
        "/diagnostics",
        json={"encounter_id": str(uuid.uuid4()), "facility_id": str(uuid.uuid4()), "test_name": test_name},
    )
    assert res.status_code == 422, f"{reason} was accepted"


def test_stock_adjustment_out_of_integer_range_is_rejected_not_a_500(client):
    """A change_qty beyond Postgres's INTEGER range used to reach the database
    and surface as NumericValueOutOfRange -> HTTP 500."""
    res = client.post(
        f"/medicine-stock/{uuid.uuid4()}/adjust",
        json={"change_qty": 999999999999999999999, "reason": "restock"},
    )
    assert res.status_code == 422


def test_negative_reorder_threshold_is_rejected(client):
    """A negative threshold permanently disables the low-stock warning."""
    res = client.post(
        "/medicine-stock",
        json={"facility_id": str(uuid.uuid4()), "medicine_name": "ORS sachets", "reorder_threshold": -1},
    )
    assert res.status_code == 422


def test_login_rejects_blank_and_absurd_credentials(client):
    assert client.post("/auth/login", json={"username": "", "password": ""}).status_code == 422
    assert client.post("/auth/login", json={"username": "a" * 5000, "password": "b" * 5000}).status_code == 422
