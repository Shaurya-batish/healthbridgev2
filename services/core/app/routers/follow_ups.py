import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FollowUp
from app.schemas import FollowUpCreateRequest, FollowUpResponse, FollowUpStatusUpdateRequest
from app.security import CurrentUser, require_facility_access

router = APIRouter(prefix="/follow-ups", tags=["follow-ups"])


@router.post("", response_model=FollowUpResponse, status_code=status.HTTP_201_CREATED)
def create_follow_up(payload: FollowUpCreateRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> FollowUpResponse:
    require_facility_access(current_user, payload.facility_id)
    follow_up = FollowUp(
        patient_id=payload.patient_id,
        encounter_id=payload.encounter_id,
        facility_id=payload.facility_id,
        scheduled_date=payload.scheduled_date,
        reason=payload.reason,
    )
    db.add(follow_up)
    db.commit()
    db.refresh(follow_up)
    return FollowUpResponse.model_validate(follow_up, from_attributes=True)


@router.get("/facility/{facility_id}", response_model=list[FollowUpResponse])
def list_follow_ups(
    facility_id: uuid.UUID, current_user: CurrentUser, due_by: date | None = None, db: Session = Depends(get_db)
) -> list[FollowUpResponse]:
    """`due_by` lets the facility screen ask for "what's due today/this week" rather than every follow-up ever scheduled."""
    require_facility_access(current_user, facility_id)
    query = select(FollowUp).where(FollowUp.facility_id == facility_id, FollowUp.status == "scheduled")
    if due_by is not None:
        query = query.where(FollowUp.scheduled_date <= due_by)
    follow_ups = db.scalars(query.order_by(FollowUp.scheduled_date.asc())).all()
    return [FollowUpResponse.model_validate(f, from_attributes=True) for f in follow_ups]


@router.get("/patient/{patient_id}", response_model=list[FollowUpResponse])
def list_follow_ups_for_patient(patient_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> list[FollowUpResponse]:
    follow_ups = db.scalars(
        select(FollowUp).where(FollowUp.patient_id == patient_id).order_by(FollowUp.scheduled_date.desc())
    ).all()
    return [FollowUpResponse.model_validate(f, from_attributes=True) for f in follow_ups]


@router.post("/{follow_up_id}/status", response_model=FollowUpResponse)
def update_follow_up_status(
    follow_up_id: uuid.UUID, payload: FollowUpStatusUpdateRequest, current_user: CurrentUser, db: Session = Depends(get_db)
) -> FollowUpResponse:
    follow_up = db.get(FollowUp, follow_up_id)
    if follow_up is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="follow_up_not_found")
    require_facility_access(current_user, follow_up.facility_id)

    follow_up.status = payload.status
    db.commit()
    db.refresh(follow_up)
    return FollowUpResponse.model_validate(follow_up, from_attributes=True)
