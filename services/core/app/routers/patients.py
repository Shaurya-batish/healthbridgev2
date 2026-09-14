import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.scheme_verification_client import (
    NhaBeneficiaryClient,
    SchemeVerificationClient,
    SchemeVerificationNotConfiguredError,
    SchemeVerificationUnavailableError,
)
from app.db import get_db
from app.fhir import build_patient_resource
from app.idempotency import check_idempotency, record_idempotency
from app.models import Encounter, Patient
from app.schemas import (
    EncounterResponse,
    PatientCreateRequest,
    PatientDetailResponse,
    PatientResponse,
    SchemeVerificationResponse,
)
from app.security import CurrentUser

router = APIRouter(prefix="/patients", tags=["patients"])

# Real client, no mock fallback -- see docs/REAL-INTEGRATION-AUDIT.md for why
# this is not yet actually connected to the live NHA BIS service.
_scheme_client: SchemeVerificationClient = NhaBeneficiaryClient()


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PatientResponse:
    cached = check_idempotency(db, idempotency_key, "create_patient")
    if cached is not None:
        return cached

    existing = db.scalar(select(Patient).where(Patient.abha_number == payload.abha_number))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="abha_number_already_registered")

    patient_id = uuid.uuid4()
    fhir = build_patient_resource(
        patient_id=patient_id,
        abha_number=payload.abha_number,
        name=payload.name,
        dob=payload.dob,
        gender=payload.gender,
    )
    patient = Patient(
        id=patient_id,
        abha_number=payload.abha_number,
        scheme_status=payload.scheme_status,
        fhir=fhir,
    )
    db.add(patient)
    try:
        db.flush()
    except IntegrityError as exc:
        # The pre-check above is a TOCTOU race, not a guarantee: two
        # concurrent registrations for the same ABHA number can both pass
        # it before either commits. The unique constraint on abha_number
        # is what actually prevents the duplicate write; this turns that
        # into the same clean 409 the pre-check gives, instead of an
        # unhandled 500 with a raw DB error leaking to the client.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="abha_number_already_registered") from exc
    db.refresh(patient)

    response = PatientResponse.model_validate(patient, from_attributes=True)
    # Staged in the same transaction as the patient row itself (flushed
    # above, committed below) -- the write and its replay cache entry can
    # never land separately.
    record_idempotency(db, idempotency_key, "create_patient", status.HTTP_201_CREATED, response.model_dump(mode="json"))
    db.commit()
    return response


@router.get("/{abha_number}", response_model=PatientDetailResponse)
def get_patient(abha_number: str, current_user: CurrentUser, db: Session = Depends(get_db)) -> PatientDetailResponse:
    patient = db.scalar(select(Patient).where(Patient.abha_number == abha_number))
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient_not_found")

    encounters = db.scalars(
        select(Encounter).where(Encounter.patient_id == patient.id).order_by(Encounter.created_at.desc())
    ).all()

    return PatientDetailResponse(
        patient=PatientResponse.model_validate(patient, from_attributes=True),
        # Each Encounter must be validated out of the ORM object explicitly.
        # PatientDetailResponse is constructed in Python (not handed to
        # FastAPI's response_model serializer as raw rows), so Pydantic v2
        # applies strict model validation to this list and rejects ORM
        # instances -- which made GET /patients/{abha} a hard 500 for every
        # patient that had at least one encounter.
        encounters=[EncounterResponse.model_validate(e, from_attributes=True) for e in encounters],
    )


@router.post("/{abha_number}/verify-scheme", response_model=SchemeVerificationResponse)
def verify_scheme(abha_number: str, current_user: CurrentUser, db: Session = Depends(get_db)) -> SchemeVerificationResponse:
    """Attempts a REAL PM-JAY/state-scheme verification call. Never fabricates
    a "verified" result -- if NHA operator credentials aren't configured,
    this honestly reports 501 rather than flipping the status."""
    patient = db.scalar(select(Patient).where(Patient.abha_number == abha_number))
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient_not_found")

    if patient.scheme_status == "none":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_scheme_claimed")

    try:
        result = _scheme_client.verify_beneficiary(patient.abha_number, patient.scheme_status)
    except SchemeVerificationNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="scheme_verification_not_configured") from exc
    except SchemeVerificationUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="scheme_verification_unavailable") from exc

    patient.scheme_verification_status = result
    db.commit()
    db.refresh(patient)

    return SchemeVerificationResponse(
        abha_number=patient.abha_number,
        scheme_status=patient.scheme_status,
        scheme_verification_status=patient.scheme_verification_status,
    )
