import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SEVERITY_RANK, QueueToken
from app.schemas import QueueTokenResponse

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/{facility_id}", response_model=list[QueueTokenResponse])
def get_queue(facility_id: uuid.UUID, db: Session = Depends(get_db)) -> list[QueueTokenResponse]:
    severity_rank = case(SEVERITY_RANK, value=QueueToken.severity, else_=99)
    tokens = db.scalars(
        select(QueueToken)
        .where(QueueToken.facility_id == facility_id, QueueToken.status != "done")
        .order_by(severity_rank, QueueToken.created_at.asc())
    ).all()
    return [QueueTokenResponse.model_validate(t, from_attributes=True) for t in tokens]
