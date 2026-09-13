import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import MedicineStock, MedicineStockMovement
from app.schemas import (
    MedicineStockAdjustRequest,
    MedicineStockCreateRequest,
    MedicineStockMovementResponse,
    MedicineStockResponse,
)

router = APIRouter(prefix="/medicine-stock", tags=["medicine-stock"])


@router.post("", response_model=MedicineStockResponse, status_code=status.HTTP_201_CREATED)
def create_medicine_stock(payload: MedicineStockCreateRequest, db: Session = Depends(get_db)) -> MedicineStockResponse:
    if payload.initial_quantity < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="initial_quantity_cannot_be_negative")

    stock = MedicineStock(
        facility_id=payload.facility_id,
        medicine_name=payload.medicine_name,
        unit=payload.unit,
        reorder_threshold=payload.reorder_threshold,
        quantity_on_hand=payload.initial_quantity,
    )
    db.add(stock)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="medicine_already_stocked_at_facility") from exc

    if payload.initial_quantity > 0:
        db.add(MedicineStockMovement(stock_id=stock.id, change_qty=payload.initial_quantity, reason="restock"))

    db.commit()
    db.refresh(stock)
    return MedicineStockResponse.model_validate(stock, from_attributes=True)


@router.get("/facility/{facility_id}", response_model=list[MedicineStockResponse])
def list_medicine_stock(facility_id: uuid.UUID, db: Session = Depends(get_db)) -> list[MedicineStockResponse]:
    items = db.scalars(
        select(MedicineStock).where(MedicineStock.facility_id == facility_id).order_by(MedicineStock.medicine_name)
    ).all()
    return [MedicineStockResponse.model_validate(i, from_attributes=True) for i in items]


@router.post("/{stock_id}/adjust", response_model=MedicineStockResponse)
def adjust_medicine_stock(
    stock_id: uuid.UUID, payload: MedicineStockAdjustRequest, db: Session = Depends(get_db)
) -> MedicineStockResponse:
    """Real inventory movement -- quantity_on_hand only ever changes together
    with an append-only ledger row recording why, so the balance is always
    reconstructable and auditable, never a bare number that can drift."""
    stock = db.get(MedicineStock, stock_id)
    if stock is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medicine_stock_not_found")

    new_quantity = stock.quantity_on_hand + payload.change_qty
    if new_quantity < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="insufficient_stock")

    stock.quantity_on_hand = new_quantity
    db.add(
        MedicineStockMovement(
            stock_id=stock.id,
            change_qty=payload.change_qty,
            reason=payload.reason,
            actor_user_id=payload.actor_user_id,
        )
    )
    db.commit()
    db.refresh(stock)
    return MedicineStockResponse.model_validate(stock, from_attributes=True)


@router.get("/{stock_id}/movements", response_model=list[MedicineStockMovementResponse])
def list_stock_movements(stock_id: uuid.UUID, db: Session = Depends(get_db)) -> list[MedicineStockMovementResponse]:
    movements = db.scalars(
        select(MedicineStockMovement)
        .where(MedicineStockMovement.stock_id == stock_id)
        .order_by(MedicineStockMovement.created_at.desc())
    ).all()
    return [MedicineStockMovementResponse.model_validate(m, from_attributes=True) for m in movements]
