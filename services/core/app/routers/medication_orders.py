"""Doctor-authored medication orders -- the only authorised prescribing path.

Orders are never edited in place. `supersede_order` is the single function
that changes what a patient is prescribed; substitution approval
(routers/substitution_requests.py) goes through it too, so there is exactly
one audited place where a prescription changes.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.medicine_comparison import load_medicine, medicine_summary
from app.models import AuditLog, Encounter, MedicationOrder
from app.schemas import MedicationOrderCreateRequest, MedicationOrderResponse
from app.security import CurrentUser, TokenPayload, require_facility_access

router = APIRouter(prefix="/medication-orders", tags=["medication-orders"])

CLINICIAN_ROLES = ("doctor",)


def require_clinician(user: TokenPayload) -> None:
    if user.role not in CLINICIAN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="clinician_role_required")


def order_response(db: Session, order: MedicationOrder) -> MedicationOrderResponse:
    loaded = load_medicine(db, order.medicine_id)
    assert loaded is not None  # FK guarantees the medicine exists
    return MedicationOrderResponse(
        id=order.id,
        patient_id=order.patient_id,
        encounter_id=order.encounter_id,
        facility_id=order.facility_id,
        medicine=medicine_summary(*loaded),
        instructions=order.instructions,
        status=order.status,
        version=order.version,
        supersedes_order_id=order.supersedes_order_id,
        prescribed_by_user_id=order.prescribed_by_user_id,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def supersede_order(db: Session, order: MedicationOrder, new_medicine_id: uuid.UUID, clinician: TokenPayload, reason: dict) -> MedicationOrder:
    """Replaces an ACTIVE order with a new version prescribing a different
    medicine. Caller must hold a row lock on `order`, have verified the
    clinician role and facility scope, and commit."""
    require_clinician(clinician)
    if order.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="prescription_not_active")
    order.status = "superseded"
    replacement = MedicationOrder(
        patient_id=order.patient_id,
        encounter_id=order.encounter_id,
        facility_id=order.facility_id,
        medicine_id=new_medicine_id,
        # Identical composition/strength/form/route/release is required before
        # this is reachable, so the instructions carry over unchanged. No dose
        # conversion is ever performed.
        instructions=order.instructions,
        status="active",
        version=order.version + 1,
        supersedes_order_id=order.id,
        prescribed_by_user_id=uuid.UUID(clinician.user_id),
    )
    db.add(replacement)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=uuid.UUID(clinician.user_id),
            action="medication_order_superseded",
            entity_type="medication_order",
            entity_id=replacement.id,
            details={
                "superseded_order_id": str(order.id),
                "previous_medicine_id": str(order.medicine_id),
                "new_medicine_id": str(new_medicine_id),
                "version": replacement.version,
                **reason,
            },
        )
    )
    return replacement


@router.post("", response_model=MedicationOrderResponse, status_code=status.HTTP_201_CREATED)
def create_medication_order(payload: MedicationOrderCreateRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> MedicationOrderResponse:
    require_clinician(current_user)
    encounter = db.get(Encounter, payload.encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="encounter_not_found")
    require_facility_access(current_user, encounter.facility_id)
    loaded = load_medicine(db, payload.medicine_id)
    if loaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medicine_not_found")
    if loaded[0].is_discontinued:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="medicine_discontinued")

    order = MedicationOrder(
        patient_id=encounter.patient_id,
        encounter_id=encounter.id,
        facility_id=encounter.facility_id,
        medicine_id=payload.medicine_id,
        instructions=payload.instructions.strip(),
        status="active",
        version=1,
        prescribed_by_user_id=uuid.UUID(current_user.user_id),
    )
    db.add(order)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=uuid.UUID(current_user.user_id),
            action="medication_order_created",
            entity_type="medication_order",
            entity_id=order.id,
            details={"encounter_id": str(encounter.id), "medicine_id": str(payload.medicine_id)},
        )
    )
    db.commit()
    db.refresh(order)
    return order_response(db, order)


@router.get("/patient/{patient_id}", response_model=list[MedicationOrderResponse])
def list_patient_orders(
    patient_id: uuid.UUID, current_user: CurrentUser, facility_id: uuid.UUID = Query(), db: Session = Depends(get_db)
) -> list[MedicationOrderResponse]:
    require_facility_access(current_user, facility_id)
    orders = db.scalars(
        select(MedicationOrder)
        .where(MedicationOrder.patient_id == patient_id, MedicationOrder.facility_id == facility_id)
        .order_by(MedicationOrder.created_at.desc())
    ).all()
    return [order_response(db, o) for o in orders]


@router.get("/{order_id}", response_model=MedicationOrderResponse)
def get_medication_order(order_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> MedicationOrderResponse:
    order = db.get(MedicationOrder, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medication_order_not_found")
    require_facility_access(current_user, order.facility_id)
    return order_response(db, order)
