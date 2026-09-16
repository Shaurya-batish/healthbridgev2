import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog, Medicine, MedicineStock, MedicineStockMovement
from app.schemas import (
    MedicineStockAdjustRequest,
    MedicineStockCreateRequest,
    MedicineStockLinkRequest,
    MedicineStockMovementResponse,
    MedicineStockResponse,
)
from app.security import CurrentUser, require_facility_access

router = APIRouter(prefix="/medicine-stock", tags=["medicine-stock"])


@router.post("", response_model=MedicineStockResponse, status_code=status.HTTP_201_CREATED)
def create_medicine_stock(payload: MedicineStockCreateRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> MedicineStockResponse:
    require_facility_access(current_user, payload.facility_id)
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
        db.add(MedicineStockMovement(stock_id=stock.id, change_qty=payload.initial_quantity, reason="restock", actor_user_id=uuid.UUID(current_user.user_id)))

    db.commit()
    db.refresh(stock)
    return MedicineStockResponse.model_validate(stock, from_attributes=True)


@router.get("/facility/{facility_id}", response_model=list[MedicineStockResponse])
def list_medicine_stock(facility_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> list[MedicineStockResponse]:
    require_facility_access(current_user, facility_id)
    items = db.scalars(
        select(MedicineStock).where(MedicineStock.facility_id == facility_id).order_by(MedicineStock.medicine_name)
    ).all()
    return [MedicineStockResponse.model_validate(i, from_attributes=True) for i in items]


@router.post("/{stock_id}/adjust", response_model=MedicineStockResponse)
def adjust_medicine_stock(
    stock_id: uuid.UUID, payload: MedicineStockAdjustRequest, current_user: CurrentUser, db: Session = Depends(get_db)
) -> MedicineStockResponse:
    """Real inventory movement -- quantity_on_hand only ever changes together
    with an append-only ledger row recording why, so the balance is always
    reconstructable and auditable, never a bare number that can drift."""
    stock = db.get(MedicineStock, stock_id)
    if stock is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medicine_stock_not_found")
    require_facility_access(current_user, stock.facility_id)

    new_quantity = stock.quantity_on_hand + payload.change_qty
    if new_quantity < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="insufficient_stock")

    stock.quantity_on_hand = new_quantity
    db.add(
        MedicineStockMovement(
            stock_id=stock.id,
            change_qty=payload.change_qty,
            reason=payload.reason,
            actor_user_id=uuid.UUID(current_user.user_id),
        )
    )
    db.commit()
    db.refresh(stock)
    return MedicineStockResponse.model_validate(stock, from_attributes=True)


@router.post("/{stock_id}/link", response_model=MedicineStockResponse)
def link_medicine_stock(
    stock_id: uuid.UUID, payload: MedicineStockLinkRequest, current_user: CurrentUser, db: Session = Depends(get_db)
) -> MedicineStockResponse:
    """Associates this facility's existing inventory row with an imported
    medicine identity (or clears it). Quantity is untouched -- linking is not
    a stock count, so it writes no ledger movement and does not refresh
    staleness; it is audited instead."""
    stock = db.get(MedicineStock, stock_id)
    if stock is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medicine_stock_not_found")
    require_facility_access(current_user, stock.facility_id)
    if payload.medicine_id is not None and db.get(Medicine, payload.medicine_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medicine_not_found")

    previous = stock.medicine_id
    stock.medicine_id = payload.medicine_id
    db.add(
        AuditLog(
            actor_user_id=uuid.UUID(current_user.user_id),
            action="medicine_stock_linked",
            entity_type="medicine_stock",
            entity_id=stock.id,
            details={
                "previous_medicine_id": str(previous) if previous else None,
                "medicine_id": str(payload.medicine_id) if payload.medicine_id else None,
            },
        )
    )
    db.commit()
    db.refresh(stock)
    return MedicineStockResponse.model_validate(stock, from_attributes=True)


@router.get("/{stock_id}/movements", response_model=list[MedicineStockMovementResponse])
def list_stock_movements(stock_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> list[MedicineStockMovementResponse]:
    stock = db.get(MedicineStock, stock_id)
    if stock is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medicine_stock_not_found")
    require_facility_access(current_user, stock.facility_id)

    movements = db.scalars(
        select(MedicineStockMovement)
        .where(MedicineStockMovement.stock_id == stock_id)
        .order_by(MedicineStockMovement.created_at.desc())
    ).all()
    return [MedicineStockMovementResponse.model_validate(m, from_attributes=True) for m in movements]
