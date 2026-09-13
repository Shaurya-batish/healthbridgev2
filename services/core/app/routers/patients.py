import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.scheme_verification_client import (
    NhaBeneficiaryClient,
    SchemeVerificationClient,
    SchemeVerificationNotConfiguredError,
    SchemeVerificationUnavailableError,
)
from app.db import get_db
from app.fhir import build_patient_resource
from app.models import Encounter, Patient
from app.schemas import PatientCreateRequest, PatientDetailResponse, PatientResponse, SchemeVerificationResponse

router = APIRouter(prefix="/patients", tags=["patients"])

# Real client, no mock fallback -- see docs/REAL-INTEGRATION-AUDIT.md for why
# this is not yet actually connected to the live NHA BIS service.
_scheme_client: SchemeVerificationClient = NhaBeneficiaryClient()


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreateRequest, db: Session = Depends(get_db)) -> PatientResponse:
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
    db.commit()
    db.refresh(patient)
    return PatientResponse.model_validate(patient, from_attributes=True)


@router.get("/{abha_number}", response_model=PatientDetailResponse)
def get_patient(abha_number: str, db: Session = Depends(get_db)) -> PatientDetailResponse:
    patient = db.scalar(select(Patient).where(Patient.abha_number == abha_number))
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient_not_found")

    encounters = db.scalars(
        select(Encounter).where(Encounter.patient_id == patient.id).order_by(Encounter.created_at.desc())
    ).all()

    return PatientDetailResponse(
        patient=PatientResponse.model_validate(patient, from_attributes=True),
        encounters=[e for e in encounters],
    )


@router.post("/{abha_number}/verify-scheme", response_model=SchemeVerificationResponse)
def verify_scheme(abha_number: str, db: Session = Depends(get_db)) -> SchemeVerificationResponse:
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
