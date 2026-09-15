"""Substitution review: request -> clinician decision, enforced here.

- Any authenticated user with access to the order's facility may REQUEST a
  review. A request changes nothing about the prescription and authorises
  nothing.
- Only a doctor at that facility may approve or reject. Admin is not a
  clinician and is refused.
- Approval re-validates, under row locks, that the request is still pending,
  the prescription is still the exact active version it was raised against,
  and the two medicines still match on the current imported data. If not, the
  request is marked `invalidated` and nothing is prescribed.
- The prescription only changes through medication_orders.supersede_order.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.medicine_comparison import load_medicine, medicine_summary, still_matches
from app.models import AuditLog, MedicationOrder, SubstitutionRequest
from app.routers.medication_orders import require_clinician, supersede_order
from app.schemas import SubstitutionDecisionRequest, SubstitutionRequestCreateRequest, SubstitutionRequestResponse
from app.security import CurrentUser, TokenPayload, require_facility_access

router = APIRouter(prefix="/substitution-requests", tags=["substitution-requests"])


def _response(db: Session, req: SubstitutionRequest) -> SubstitutionRequestResponse:
    original = load_medicine(db, req.original_medicine_id)
    proposed = load_medicine(db, req.proposed_medicine_id)
    assert original is not None and proposed is not None
    return SubstitutionRequestResponse(
        id=req.id,
        order_id=req.order_id,
        patient_id=req.patient_id,
        encounter_id=req.encounter_id,
        facility_id=req.facility_id,
        original_medicine=medicine_summary(*original),
        proposed_medicine=medicine_summary(*proposed),
        order_version=req.order_version,
        status=req.status,
        requested_by_user_id=req.requested_by_user_id,
        request_note=req.request_note,
        reviewed_by_user_id=req.reviewed_by_user_id,
        reviewed_at=req.reviewed_at,
        decision_note=req.decision_note,
        resulting_order_id=req.resulting_order_id,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


def _audit(db: Session, user: TokenPayload, action: str, req: SubstitutionRequest, **details) -> None:
    db.add(
        AuditLog(
            actor_user_id=uuid.UUID(user.user_id),
            action=action,
            entity_type="substitution_request",
            entity_id=req.id,
            details={
                "order_id": str(req.order_id),
                "original_medicine_id": str(req.original_medicine_id),
                "proposed_medicine_id": str(req.proposed_medicine_id),
                "order_version": req.order_version,
                **details,
            },
        )
    )


@router.post("", response_model=SubstitutionRequestResponse, status_code=status.HTTP_201_CREATED)
def create_substitution_request(
    payload: SubstitutionRequestCreateRequest, current_user: CurrentUser, db: Session = Depends(get_db)
) -> SubstitutionRequestResponse:
    order = db.get(MedicationOrder, payload.order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medication_order_not_found")
    require_facility_access(current_user, order.facility_id)
    if order.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="prescription_not_active")

    original = load_medicine(db, order.medicine_id)
    proposed = load_medicine(db, payload.proposed_medicine_id)
    if proposed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medicine_not_found")
    assert original is not None
    if not still_matches(original[0], proposed[0]):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="not_a_same_composition_match")

    existing = db.scalar(
        select(SubstitutionRequest).where(
            SubstitutionRequest.order_id == order.id,
            SubstitutionRequest.proposed_medicine_id == payload.proposed_medicine_id,
            SubstitutionRequest.status == "pending",
        )
    )
    if existing is not None:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "substitution_request_already_pending", "request_id": str(existing.id)},
        )

    req = SubstitutionRequest(
        order_id=order.id,
        patient_id=order.patient_id,
        encounter_id=order.encounter_id,
        facility_id=order.facility_id,
        original_medicine_id=order.medicine_id,
        proposed_medicine_id=payload.proposed_medicine_id,
        order_version=order.version,
        match_key_at_request=original[0].match_key,
        status="pending",
        requested_by_user_id=uuid.UUID(current_user.user_id),
        request_note=(payload.note or "").strip() or None,
    )
    db.add(req)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent identical request won the partial unique index.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="substitution_request_already_pending")
    _audit(db, current_user, "substitution_requested", req, requester_role=current_user.role)
    db.commit()
    db.refresh(req)
    return _response(db, req)


@router.get("/facility/{facility_id}", response_model=list[SubstitutionRequestResponse])
def list_substitution_requests(
    facility_id: uuid.UUID,
    current_user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status", pattern="^(pending|approved|rejected|invalidated)$"),
    db: Session = Depends(get_db),
) -> list[SubstitutionRequestResponse]:
    require_facility_access(current_user, facility_id)
    query = select(SubstitutionRequest).where(SubstitutionRequest.facility_id == facility_id)
    if status_filter:
        query = query.where(SubstitutionRequest.status == status_filter)
    rows = db.scalars(query.order_by(SubstitutionRequest.created_at.desc()).limit(200)).all()
    return [_response(db, r) for r in rows]


def _load_for_decision(db: Session, request_id: uuid.UUID, user: TokenPayload) -> SubstitutionRequest:
    require_clinician(user)
    req = db.execute(select(SubstitutionRequest).where(SubstitutionRequest.id == request_id).with_for_update()).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="substitution_request_not_found")
    require_facility_access(user, req.facility_id)
    if req.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="substitution_request_not_pending")
    return req


@router.post("/{request_id}/approve", response_model=SubstitutionRequestResponse)
def approve_substitution_request(
    request_id: uuid.UUID, payload: SubstitutionDecisionRequest, current_user: CurrentUser, db: Session = Depends(get_db)
) -> SubstitutionRequestResponse:
    req = _load_for_decision(db, request_id, current_user)
    order = db.execute(select(MedicationOrder).where(MedicationOrder.id == req.order_id).with_for_update()).scalar_one()
    original = load_medicine(db, req.original_medicine_id)
    proposed = load_medicine(db, req.proposed_medicine_id)
    assert original is not None and proposed is not None

    invalid_reason = None
    if order.status != "active" or order.version != req.order_version or order.medicine_id != req.original_medicine_id:
        invalid_reason = "prescription_changed_since_request"
    elif not still_matches(original[0], proposed[0]) or original[0].match_key != req.match_key_at_request:
        invalid_reason = "substitute_no_longer_matches"

    now = datetime.now(timezone.utc)
    if invalid_reason is not None:
        req.status = "invalidated"
        req.reviewed_by_user_id = uuid.UUID(current_user.user_id)
        req.reviewed_at = now
        req.decision_note = invalid_reason
        _audit(db, current_user, "substitution_invalidated", req, reason=invalid_reason)
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=invalid_reason)

    replacement = supersede_order(
        db, order, req.proposed_medicine_id, current_user, {"substitution_request_id": str(req.id)}
    )
    req.status = "approved"
    req.reviewed_by_user_id = uuid.UUID(current_user.user_id)
    req.reviewed_at = now
    req.decision_note = (payload.decision_note or "").strip() or None
    req.resulting_order_id = replacement.id
    _audit(db, current_user, "substitution_approved", req, resulting_order_id=str(replacement.id))
    db.commit()
    db.refresh(req)
    return _response(db, req)


@router.post("/{request_id}/reject", response_model=SubstitutionRequestResponse)
def reject_substitution_request(
    request_id: uuid.UUID, payload: SubstitutionDecisionRequest, current_user: CurrentUser, db: Session = Depends(get_db)
) -> SubstitutionRequestResponse:
    req = _load_for_decision(db, request_id, current_user)
    req.status = "rejected"
    req.reviewed_by_user_id = uuid.UUID(current_user.user_id)
    req.reviewed_at = datetime.now(timezone.utc)
    req.decision_note = (payload.decision_note or "").strip() or None
    _audit(db, current_user, "substitution_rejected", req)
    db.commit()
    db.refresh(req)
    return _response(db, req)
