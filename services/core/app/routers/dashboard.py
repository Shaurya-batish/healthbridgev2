import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Encounter, EscalationEvent, QueueToken, TriageRecord
from app.schemas import DashboardResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Teleconsult is a store-and-forward mock per CLAUDE.md -- no live infra, no
# table of its own yet. Exposed as a static 0 here so the tile is honest
# about being unwired rather than silently fabricating a number.
TELECONSULTS_DONE_MOCK = 0


@router.get("/{facility_id}", response_model=DashboardResponse)
def get_dashboard(facility_id: uuid.UUID, db: Session = Depends(get_db)) -> DashboardResponse:
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

    return DashboardResponse(
        triaged_by_severity=triaged_by_severity,
        queue_length=queue_length,
        teleconsults_done=TELECONSULTS_DONE_MOCK,
        red_cases_escalated=red_cases_escalated,
    )
