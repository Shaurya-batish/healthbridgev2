import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.fhir import build_observation_resource
from app.models import (
    SEVERITY_RANK,
    AuditLog,
    Encounter,
    EscalationEvent,
    Observation,
    QueueToken,
    TriageRecord,
)
from app.redis_client import publish_escalation
from app.schemas import TriageRecordResponse, TriageRequest, TriageResponse
from app.security import CurrentUser, require_facility_access

router = APIRouter(prefix="/triage", tags=["triage"])


def _severity_rank_case():
    return case(SEVERITY_RANK, value=QueueToken.severity, else_=99)


def _queue_position(db: Session, facility_id: uuid.UUID, token: QueueToken) -> int:
    """1-based position within RED > YELLOW > GREEN, then FIFO by creation time."""
    tokens = db.scalars(
        select(QueueToken)
        .where(QueueToken.facility_id == facility_id, QueueToken.status != "done")
        .order_by(_severity_rank_case(), QueueToken.created_at.asc())
    ).all()
    for idx, t in enumerate(tokens, start=1):
        if t.id == token.id:
            return idx
    return len(tokens)


@router.post("", response_model=TriageResponse, status_code=status.HTTP_201_CREATED)
def submit_triage(payload: TriageRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> TriageResponse:
    """The audit-critical write path.

    Every call -- regardless of severity, regardless of source (LLM or
    offline checklist) -- writes an Observation, a TriageRecord, and an
    AuditLog row naming exactly which rule fired. This is what makes the
    triage decision defensible to a clinician later: nothing here is
    optional or best-effort.
    """
    encounter = db.get(Encounter, payload.encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="encounter_not_found")
    require_facility_access(current_user, encounter.facility_id)

    observation = Observation(
        encounter_id=encounter.id,
        fhir=build_observation_resource(
            observation_id=uuid.uuid4(),
            encounter_id=encounter.id,
            extracted_facts=payload.extracted_facts,
            complaint_text=payload.complaint_text,
        ),
    )
    db.add(observation)

    triage_record = TriageRecord(
        encounter_id=encounter.id,
        complaint_text=payload.complaint_text,
        extracted_facts=payload.extracted_facts,
        rule_id=payload.rule_id,
        rule_version=payload.rule_version,
        severity=payload.severity,
        source=payload.source,
    )
    db.add(triage_record)
    db.flush()

    # Update (not replace) the encounter's queue token -- this is the "queue
    # reorder": GET /queue/{facility_id} sorts by severity at read time, so
    # changing this field is what moves the patient in the queue.
    queue_token = db.scalar(select(QueueToken).where(QueueToken.encounter_id == encounter.id))
    if queue_token is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="queue_token_missing_for_encounter")
    queue_token.severity = payload.severity
    db.flush()

    escalation_created = False
    if payload.severity == "RED":
        escalation = EscalationEvent(
            triage_record_id=triage_record.id,
            patient_id=encounter.patient_id,
            facility_id=encounter.facility_id,
            status="open",
        )
        db.add(escalation)
        db.flush()
        escalation_created = True
        publish_escalation(
            str(encounter.facility_id),
            {
                "escalation_id": str(escalation.id),
                "encounter_id": str(encounter.id),
                "patient_id": str(encounter.patient_id),
                "rule_id": payload.rule_id,
            },
        )

    db.add(
        AuditLog(
            actor_user_id=uuid.UUID(current_user.user_id),
            action="triage_decision",
            entity_type="triage_record",
            entity_id=triage_record.id,
            details={
                "encounter_id": str(encounter.id),
                "complaint_text": payload.complaint_text,
                "extracted_facts": payload.extracted_facts,
                "rule_id": payload.rule_id,
                "rule_version": payload.rule_version,
                "severity": payload.severity,
                "source": payload.source,
                "escalation_created": escalation_created,
            },
        )
    )

    db.commit()
    db.refresh(triage_record)
    db.refresh(queue_token)

    position = _queue_position(db, encounter.facility_id, queue_token)

    return TriageResponse(
        triage_record=TriageRecordResponse.model_validate(triage_record, from_attributes=True),
        queue_position=position,
        escalation_created=escalation_created,
    )
