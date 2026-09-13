import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Encounter, EscalationEvent, QueueToken, Teleconsult, TriageRecord
from app.schemas import DashboardResponse
from app.security import CurrentUser, require_facility_access

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/{facility_id}", response_model=DashboardResponse)
def get_dashboard(facility_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> DashboardResponse:
    require_facility_access(current_user, facility_id)
    severity_counts = dict(
        db.execute(
            select(TriageRecord.severity, func.count())
            .join(Encounter, TriageRecord.encounter_id == Encounter.id)
            .where(Encounter.facility_id == facility_id)
            .group_by(TriageRecord.severity)
        ).all()
    )
    triaged_by_severity = {
        "RED": severity_counts.get("RED", 0),
        "YELLOW": severity_counts.get("YELLOW", 0),
        "GREEN": severity_counts.get("GREEN", 0),
    }

    queue_length = db.scalar(
        select(func.count())
        .select_from(QueueToken)
        .where(QueueToken.facility_id == facility_id, QueueToken.status != "done")
    ) or 0

    red_cases_escalated = db.scalar(
        select(func.count()).select_from(EscalationEvent).where(EscalationEvent.facility_id == facility_id)
    ) or 0

    # Real count -- a teleconsult only counts as "done" once a doctor has
    # actually reviewed the real recorded media and left a real response.
    teleconsults_done = db.scalar(
        select(func.count())
        .select_from(Teleconsult)
        .where(Teleconsult.facility_id == facility_id, Teleconsult.status == "reviewed")
    ) or 0

    return DashboardResponse(
        triaged_by_severity=triaged_by_severity,
        queue_length=queue_length,
        teleconsults_done=teleconsults_done,
        red_cases_escalated=red_cases_escalated,
    )
