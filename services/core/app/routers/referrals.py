import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Referral
from app.schemas import ReferralCreateRequest, ReferralResponse, ReferralStatusUpdateRequest

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.post("", response_model=ReferralResponse, status_code=status.HTTP_201_CREATED)
def create_referral(payload: ReferralCreateRequest, db: Session = Depends(get_db)) -> ReferralResponse:
    referral = Referral(
        patient_id=payload.patient_id,
        encounter_id=payload.encounter_id,
        from_facility_id=payload.from_facility_id,
        to_facility_id=payload.to_facility_id,
        reason=payload.reason,
    )
    db.add(referral)
    db.commit()
    db.refresh(referral)
    return ReferralResponse.model_validate(referral, from_attributes=True)


@router.get("/facility/{facility_id}", response_model=list[ReferralResponse])
def list_referrals_for_facility(facility_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ReferralResponse]:
    """Both directions -- a facility needs to see referrals it sent and ones it received."""
    referrals = db.scalars(
        select(Referral)
        .where(or_(Referral.from_facility_id == facility_id, Referral.to_facility_id == facility_id))
        .order_by(Referral.created_at.desc())
    ).all()
    return [ReferralResponse.model_validate(r, from_attributes=True) for r in referrals]


@router.get("/patient/{patient_id}", response_model=list[ReferralResponse])
def list_referrals_for_patient(patient_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ReferralResponse]:
    """Longitudinal referral history for one patient, across every facility."""
    referrals = db.scalars(
        select(Referral).where(Referral.patient_id == patient_id).order_by(Referral.created_at.desc())
    ).all()
    return [ReferralResponse.model_validate(r, from_attributes=True) for r in referrals]


@router.post("/{referral_id}/status", response_model=ReferralResponse)
def update_referral_status(
    referral_id: uuid.UUID, payload: ReferralStatusUpdateRequest, db: Session = Depends(get_db)
) -> ReferralResponse:
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="referral_not_found")

    referral.status = payload.status
    db.commit()
    db.refresh(referral)
    return ReferralResponse.model_validate(referral, from_attributes=True)
