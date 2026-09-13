import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EscalationEvent
from app.schemas import EscalationResponse
from app.security import CurrentUser, require_facility_access

router = APIRouter(prefix="/escalations", tags=["escalations"])


@router.get("/{facility_id}", response_model=list[EscalationResponse])
def list_escalations(facility_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> list[EscalationResponse]:
    require_facility_access(current_user, facility_id)
    escalations = db.scalars(
        select(EscalationEvent)
        .where(EscalationEvent.facility_id == facility_id, EscalationEvent.status == "open")
        .order_by(EscalationEvent.created_at.asc())
    ).all()
    return [EscalationResponse.model_validate(e, from_attributes=True) for e in escalations]


@router.post("/{escalation_id}/acknowledge", response_model=EscalationResponse)
def acknowledge_escalation(escalation_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> EscalationResponse:
    escalation = db.get(EscalationEvent, escalation_id)
    if escalation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="escalation_not_found")
    require_facility_access(current_user, escalation.facility_id)
    escalation.status = "acknowledged"
    db.commit()
    db.refresh(escalation)
    return EscalationResponse.model_validate(escalation, from_attributes=True)
