import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.medicine_comparison import find_substitutes, load_medicine, medicine_summary
from app.models import Medicine, MedicineSource
from app.schemas import MedicineListResponse, MedicineSummary, SubstitutesResponse
from app.security import CurrentUser, require_facility_access

router = APIRouter(prefix="/medicines", tags=["medicines"])


@router.get("", response_model=MedicineListResponse)
def search_medicines(
    current_user: CurrentUser,
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
    db: Session = Depends(get_db),
) -> MedicineListResponse:
    """Search imported reference medicines by brand name or active ingredient.
    Reference data is not facility-scoped; stock is, and is only returned by
    the facility-scoped /substitutes endpoint."""
    term = " ".join(q.lower().split())
    if len(term) < 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="query_too_short")
    # Escape LIKE wildcards so user input is matched literally.
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    condition = Medicine.name_normalized.like(pattern, escape="\\") | func.lower(func.coalesce(Medicine.generic_name, "")).like(
        pattern, escape="\\"
    )

    total = db.scalar(select(func.count()).select_from(Medicine).where(condition)) or 0
    rows = db.scalars(
        select(Medicine)
        .options(selectinload(Medicine.ingredients))
        .where(condition)
        .order_by(Medicine.is_discontinued.asc(), Medicine.name_normalized.asc(), Medicine.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    sources = {s.id: s for s in db.scalars(select(MedicineSource)).all()}
    return MedicineListResponse(
        items=[medicine_summary(m, sources[m.source_id]) for m in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{medicine_id}", response_model=MedicineSummary)
def get_medicine(medicine_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> MedicineSummary:
    loaded = load_medicine(db, medicine_id)
    if loaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medicine_not_found")
    return medicine_summary(*loaded)


@router.get("/{medicine_id}/substitutes", response_model=SubstitutesResponse)
def get_substitutes(
    medicine_id: uuid.UUID,
    current_user: CurrentUser,
    facility_id: uuid.UUID = Query(),
    db: Session = Depends(get_db),
) -> SubstitutesResponse:
    require_facility_access(current_user, facility_id)
    loaded = load_medicine(db, medicine_id)
    if loaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medicine_not_found")
    return find_substitutes(db, loaded[0], loaded[1], facility_id)
