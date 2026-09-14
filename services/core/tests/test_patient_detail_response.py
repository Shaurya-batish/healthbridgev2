"""Regression test for the GET /patients/{abha} 500.

PatientDetailResponse is constructed in Python rather than handed to
FastAPI's response_model serializer, so Pydantic v2 applies strict model
validation to the nested `encounters` list. Passing SQLAlchemy Encounter
instances straight in raised
    ValidationError: Input should be a valid dictionary or instance of
    EncounterResponse
which made the endpoint a hard 500 for every patient with at least one
encounter -- the longitudinal patient view, unreachable in both client
surfaces. The fix validates each row out of the ORM object explicitly; this
test pins that contract without needing the JSONB tables.
"""
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import EncounterResponse, PatientDetailResponse, PatientResponse


class _Row:
    """Stands in for a SQLAlchemy row: attributes, not a dict."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _encounter_row():
    return _Row(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        facility_id=uuid.uuid4(),
        fhir={"resourceType": "Encounter"},
        created_at=datetime.now(timezone.utc),
    )


def _patient_row():
    now = datetime.now(timezone.utc)
    return _Row(
        id=uuid.uuid4(),
        abha_number="12-3456-7890-1234",
        scheme_status="PMJAY",
        scheme_verification_status="unverified",
        fhir={"resourceType": "Patient"},
        created_at=now,
        updated_at=now,
    )


def test_orm_rows_must_be_validated_before_going_into_the_envelope():
    """The shape the router must NOT use -- kept as a test so the 500 cannot
    come back unnoticed."""
    with pytest.raises(ValidationError):
        PatientDetailResponse(
            patient=PatientResponse.model_validate(_patient_row(), from_attributes=True),
            encounters=[_encounter_row()],
        )


def test_validated_rows_build_the_envelope_and_keep_every_field():
    rows = [_encounter_row(), _encounter_row()]
    detail = PatientDetailResponse(
        patient=PatientResponse.model_validate(_patient_row(), from_attributes=True),
        encounters=[EncounterResponse.model_validate(r, from_attributes=True) for r in rows],
    )
    assert detail.patient.abha_number == "12-3456-7890-1234"
    assert [e.id for e in detail.encounters] == [r.id for r in rows]
    # The web client reads detail.patient.* and detail.encounters[*].*; both
    # patient detail pages crashed by reading .fhir off the envelope instead.
    dumped = detail.model_dump(mode="json")
    assert set(dumped) == {"patient", "encounters"}
    assert "fhir" in dumped["patient"]
