import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DiagnosticOrder, Encounter
from app.schemas import (
    DiagnosticOrderCreateRequest,
    DiagnosticOrderResponse,
    DiagnosticResultRequest,
    DiagnosticStatusUpdateRequest,
)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.post("", response_model=DiagnosticOrderResponse, status_code=status.HTTP_201_CREATED)
def create_diagnostic_order(payload: DiagnosticOrderCreateRequest, db: Session = Depends(get_db)) -> DiagnosticOrderResponse:
    if db.get(Encounter, payload.encounter_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="encounter_not_found")

    order = DiagnosticOrder(
        encounter_id=payload.encounter_id,
        facility_id=payload.facility_id,
        test_name=payload.test_name,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return DiagnosticOrderResponse.model_validate(order, from_attributes=True)


@router.get("/facility/{facility_id}", response_model=list[DiagnosticOrderResponse])
def list_diagnostic_orders(facility_id: uuid.UUID, db: Session = Depends(get_db)) -> list[DiagnosticOrderResponse]:
    orders = db.scalars(
        select(DiagnosticOrder)
        .where(DiagnosticOrder.facility_id == facility_id)
        .order_by(DiagnosticOrder.created_at.desc())
    ).all()
    return [DiagnosticOrderResponse.model_validate(o, from_attributes=True) for o in orders]


@router.post("/{order_id}/status", response_model=DiagnosticOrderResponse)
def update_diagnostic_status(
    order_id: uuid.UUID, payload: DiagnosticStatusUpdateRequest, db: Session = Depends(get_db)
) -> DiagnosticOrderResponse:
    order = db.get(DiagnosticOrder, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="diagnostic_order_not_found")

    order.status = payload.status
    db.commit()
    db.refresh(order)
    return DiagnosticOrderResponse.model_validate(order, from_attributes=True)


@router.post("/{order_id}/result", response_model=DiagnosticOrderResponse)
def record_diagnostic_result(
    order_id: uuid.UUID, payload: DiagnosticResultRequest, db: Session = Depends(get_db)
) -> DiagnosticOrderResponse:
    order = db.get(DiagnosticOrder, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="diagnostic_order_not_found")

    order.result_text = payload.result_text
    order.result_recorded_at = datetime.now(timezone.utc)
    order.status = "completed"
    db.commit()
    db.refresh(order)
    return DiagnosticOrderResponse.model_validate(order, from_attributes=True)
