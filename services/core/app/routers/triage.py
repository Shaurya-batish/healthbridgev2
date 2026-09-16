import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.fhir import build_observation_resource
from app.idempotency import check_idempotency, record_idempotency
from app.models import (
    SEVERITY_RANK,
    AuditLog,
    ComplaintCapture,
    Encounter,
    EscalationEvent,
    Observation,
    QueueToken,
    TriageRecord,
)
from app.redis_client import publish_escalation
from app.schemas import ComplaintCaptureResponse, TriageRecordResponse, TriageRequest, TriageResponse
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
def submit_triage(
    payload: TriageRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TriageResponse:
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

    cached = check_idempotency(db, idempotency_key, "submit_triage")
    if cached is not None:
        return cached
    # A retry that hits this cache never reaches publish_escalation below
    # either -- a duplicate RED submission no longer means a duplicate
    # doctor notification.

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

    capture_row: ComplaintCapture | None = None
    if payload.complaint_capture is not None:
        cap = payload.complaint_capture
        if db.scalar(select(ComplaintCapture.id).where(ComplaintCapture.client_capture_id == cap.client_capture_id)):
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="complaint_capture_already_recorded")
        english_status = "not_required" if cap.language == "en" else cap.translation_status
        capture_row = ComplaintCapture(
            triage_record_id=triage_record.id,
            encounter_id=encounter.id,
            captured_by_user_id=uuid.UUID(current_user.user_id),
            client_capture_id=cap.client_capture_id,
            input_source=cap.input_source,
            language=cap.language,
            original_text=cap.original_text,
            initial_machine_translation_en=cap.initial_machine_translation_en,
            initial_translation_engine=cap.initial_translation_engine,
            machine_translation_en=cap.machine_translation_en,
            translation_engine=cap.translation_engine,
            translation_status=english_status,
            confirmed_original_text=cap.confirmed_original_text,
            confirmed_text_en=cap.confirmed_text_en,
            # Derived server-side from the texts themselves, never trusted from the client.
            original_edited=cap.confirmed_original_text.strip() != cap.original_text.strip(),
            english_edited=cap.language != "en"
            and (cap.machine_translation_en or "").strip() != cap.confirmed_text_en.strip(),
            captured_at=cap.captured_at,
            confirmed_at=cap.confirmed_at,
            consent_confirmed_at=cap.consent_confirmed_at,
            audio_sha256=cap.audio_sha256,
            audio_duration_seconds=cap.audio_duration_seconds,
            audio_mime_type=cap.audio_mime_type,
        )
        db.add(capture_row)
        try:
            db.flush()
        except IntegrityError as exc:
            # Concurrent replay of the same offline capture past the pre-check.
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="complaint_capture_already_recorded") from exc

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
                # Clinical provenance lives in the protected audit trail and
                # complaint_captures only -- never in application logs.
                "complaint_capture": (
                    {
                        "id": str(capture_row.id),
                        "input_source": capture_row.input_source,
                        "language": capture_row.language,
                        "original_text": capture_row.original_text,
                        "initial_machine_translation_en": capture_row.initial_machine_translation_en,
                        "initial_translation_engine": capture_row.initial_translation_engine,
                        "machine_translation_en": capture_row.machine_translation_en,
                        "translation_engine": capture_row.translation_engine,
                        "translation_status": capture_row.translation_status,
                        "confirmed_original_text": capture_row.confirmed_original_text,
                        "confirmed_text_en": capture_row.confirmed_text_en,
                        "original_edited": capture_row.original_edited,
                        "english_edited": capture_row.english_edited,
                        "captured_at": capture_row.captured_at.isoformat(),
                        "confirmed_at": capture_row.confirmed_at.isoformat(),
                        "audio_sha256": capture_row.audio_sha256,
                        "audio_duration_seconds": capture_row.audio_duration_seconds,
                    }
                    if capture_row is not None
                    else None
                ),
            },
        )
    )

    db.flush()
    db.refresh(triage_record)
    db.refresh(queue_token)

    position = _queue_position(db, encounter.facility_id, queue_token)

    record_response = TriageRecordResponse.model_validate(triage_record, from_attributes=True)
    if capture_row is not None:
        db.refresh(capture_row)
        record_response.complaint_capture = ComplaintCaptureResponse.model_validate(capture_row, from_attributes=True)

    response = TriageResponse(
        triage_record=record_response,
        queue_position=position,
        escalation_created=escalation_created,
    )
    record_idempotency(db, idempotency_key, "submit_triage", status.HTTP_201_CREATED, response.model_dump(mode="json"))
    db.commit()
    return response
