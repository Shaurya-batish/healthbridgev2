import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Referral
from app.schemas import ReferralCreateRequest, ReferralResponse, ReferralStatusUpdateRequest
from app.security import CurrentUser, require_facility_access

router = APIRouter(prefix="/referrals", tags=["referrals"])


def _require_party_to_referral(current_user, referral: Referral) -> None:
    if current_user.role == "admin":
        return
    if current_user.facility_id is None or str(current_user.facility_id) not in (
        str(referral.from_facility_id),
        str(referral.to_facility_id),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="facility_access_denied")


@router.post("", response_model=ReferralResponse, status_code=status.HTTP_201_CREATED)
def create_referral(payload: ReferralCreateRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> ReferralResponse:
    require_facility_access(current_user, payload.from_facility_id)
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
def list_referrals_for_facility(facility_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> list[ReferralResponse]:
    """Both directions -- a facility needs to see referrals it sent and ones it received."""
    require_facility_access(current_user, facility_id)
    referrals = db.scalars(
        select(Referral)
        .where(or_(Referral.from_facility_id == facility_id, Referral.to_facility_id == facility_id))
        .order_by(Referral.created_at.desc())
    ).all()
    return [ReferralResponse.model_validate(r, from_attributes=True) for r in referrals]


@router.get("/patient/{patient_id}", response_model=list[ReferralResponse])
def list_referrals_for_patient(patient_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> list[ReferralResponse]:
    """Longitudinal referral history for one patient, across every facility -- same access principle as GET /patients/{abha}."""
    referrals = db.scalars(
        select(Referral).where(Referral.patient_id == patient_id).order_by(Referral.created_at.desc())
    ).all()
    return [ReferralResponse.model_validate(r, from_attributes=True) for r in referrals]


@router.post("/{referral_id}/status", response_model=ReferralResponse)
def update_referral_status(
    referral_id: uuid.UUID, payload: ReferralStatusUpdateRequest, current_user: CurrentUser, db: Session = Depends(get_db)
) -> ReferralResponse:
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="referral_not_found")
    _require_party_to_referral(current_user, referral)

    referral.status = payload.status
    db.commit()
    db.refresh(referral)
    return ReferralResponse.model_validate(referral, from_attributes=True)
