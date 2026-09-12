import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.fhir import build_encounter_resource
from app.models import Encounter, Facility, Patient, QueueToken
from app.schemas import EncounterCreateRequest, EncounterResponse

router = APIRouter(prefix="/encounters", tags=["encounters"])


@router.post("", response_model=EncounterResponse, status_code=status.HTTP_201_CREATED)
def create_encounter(payload: EncounterCreateRequest, db: Session = Depends(get_db)) -> EncounterResponse:
    patient = db.scalar(select(Patient).where(Patient.abha_number == payload.abha_number))
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient_not_found")

    facility = db.get(Facility, payload.facility_id)
    if facility is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="facility_not_found")

    encounter_id = uuid.uuid4()
    fhir = build_encounter_resource(
        encounter_id=encounter_id,
        patient_id=patient.id,
        facility_id=facility.id,
        facility_level=facility.level,
        chief_complaint=payload.chief_complaint,
    )
    encounter = Encounter(id=encounter_id, patient_id=patient.id, facility_id=facility.id, fhir=fhir)
    db.add(encounter)
    db.flush()

    next_token_number = (
        db.scalar(
            select(func.coalesce(func.max(QueueToken.token_number), 0)).where(
                QueueToken.facility_id == facility.id
            )
        )
        or 0
    ) + 1
    # Severity is unknown until /triage runs; GREEN is the safe, lowest-priority
    # placeholder -- /triage updates it in place, which is what re-sorts the queue.
    queue_token = QueueToken(
        encounter_id=encounter.id,
        facility_id=facility.id,
        token_number=next_token_number,
        severity="GREEN",
        status="waiting",
    )
    db.add(queue_token)
    db.commit()
    db.refresh(encounter)
    return EncounterResponse.model_validate(encounter, from_attributes=True)
