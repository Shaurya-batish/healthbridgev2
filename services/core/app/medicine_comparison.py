"""Builds API views of imported medicines and the facility-scoped,
same-composition comparison. All matching decisions come from
app/salt_matching.py (fail closed); this module only reads persisted
identities, joins real facility stock, and orders the result."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import salt_matching as sm
from app.config import get_settings
from app.models import Medicine, MedicineSource, MedicineStock, MedicineStockMovement
from app.schemas import (
    FacilityStockInfo,
    MedicineIngredientResponse,
    MedicineSourceInfo,
    MedicineSummary,
    SubstituteCandidate,
    SubstitutesResponse,
)

MAX_CANDIDATES = 100

NOTICE = (
    "Informational comparison only. Listed products share the same active ingredients, strengths, "
    "dosage form, route and release type as recorded by the source dataset. This does not establish "
    "clinical interchangeability and does not authorise substitution, prescribing or dispensing. "
    "A clinician must review any change."
)


def _s(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return sm._canon(Decimal(value))  # noqa: SLF001 - shared canonical formatting


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def medicine_summary(medicine: Medicine, source: MedicineSource) -> MedicineSummary:
    return MedicineSummary(
        id=medicine.id,
        brand_name=medicine.brand_name,
        generic_name=medicine.generic_name,
        manufacturer=medicine.manufacturer,
        dosage_form=medicine.dosage_form,
        route=medicine.route,
        release_type=medicine.release_type,
        pack_label=medicine.pack_label,
        pack_quantity=_s(medicine.pack_quantity),
        pack_unit=medicine.pack_unit,
        price=None if medicine.price is None else f"{Decimal(medicine.price):.2f}",
        price_basis=source.price_basis,
        currency=source.currency,
        unit_price=_s(medicine.unit_price),
        is_discontinued=medicine.is_discontinued,
        match_status=medicine.match_status,
        insufficient_reasons=[r for r in (medicine.insufficient_reasons or "").split(",") if r],
        ingredients=[
            MedicineIngredientResponse(
                name=i.name, strength_value=_s(i.strength_value), strength_unit=i.strength_unit, raw_text=i.raw_text
            )
            for i in medicine.ingredients
        ],
        source=MedicineSourceInfo(
            name=source.name,
            license=source.license,
            source_url=source.source_url,
            source_version=source.source_version,
            source_updated_on=source.source_updated_on,
            imported_at=_aware(source.imported_at),
        ),
    )


def load_medicine(db: Session, medicine_id: uuid.UUID) -> tuple[Medicine, MedicineSource] | None:
    medicine = db.scalar(select(Medicine).options(selectinload(Medicine.ingredients)).where(Medicine.id == medicine_id))
    if medicine is None:
        return None
    return medicine, db.get(MedicineSource, medicine.source_id)


def _stock_by_medicine(db: Session, facility_id: uuid.UUID, now: datetime, *conditions) -> dict[uuid.UUID, FacilityStockInfo]:
    """Real inventory join for every medicine matching `conditions`, in one
    query. Several stock rows at one facility may link to the same identity
    (e.g. two free-text names): quantities are summed and the OLDEST last
    count among them decides staleness (conservative)."""
    last_movement = func.max(MedicineStockMovement.created_at)
    rows = db.execute(
        select(MedicineStock.id, MedicineStock.medicine_id, MedicineStock.quantity_on_hand, MedicineStock.created_at, last_movement)
        .join(Medicine, Medicine.id == MedicineStock.medicine_id)
        .outerjoin(MedicineStockMovement, MedicineStockMovement.stock_id == MedicineStock.id)
        .where(MedicineStock.facility_id == facility_id, *conditions)
        .group_by(MedicineStock.id, MedicineStock.medicine_id, MedicineStock.quantity_on_hand, MedicineStock.created_at)
    ).all()

    grouped: dict[uuid.UUID, list] = {}
    for stock_id, medicine_id, quantity, created_at, moved_at in rows:
        grouped.setdefault(medicine_id, []).append((stock_id, quantity, _aware(moved_at) or _aware(created_at) or now))

    stale_after = timedelta(days=get_settings().stock_stale_after_days)
    result: dict[uuid.UUID, FacilityStockInfo] = {}
    for medicine_id, entries in grouped.items():
        quantity = sum(e[1] for e in entries)
        last_counted = min(e[2] for e in entries)
        if now - last_counted > stale_after:
            status = "stale"
        elif quantity > 0:
            status = "available"
        else:
            status = "unavailable"
        result[medicine_id] = FacilityStockInfo(
            status=status,
            stock_id=entries[0][0] if len(entries) == 1 else None,
            quantity_on_hand=quantity,
            last_counted_at=last_counted,
        )
    return result


def facility_stock(db: Session, medicine_id: uuid.UUID, facility_id: uuid.UUID, now: datetime | None = None) -> FacilityStockInfo:
    now = now or datetime.now(timezone.utc)
    return _stock_by_medicine(db, facility_id, now, Medicine.id == medicine_id).get(medicine_id, FacilityStockInfo(status="unknown"))


def still_matches(original: Medicine, proposed: Medicine) -> bool:
    return (
        original.id != proposed.id
        and original.match_status == sm.MATCHABLE
        and proposed.match_status == sm.MATCHABLE
        and not proposed.is_discontinued
        and original.match_key is not None
        and original.match_key == proposed.match_key
    )


def find_substitutes(db: Session, reference: Medicine, source: MedicineSource, facility_id: uuid.UUID) -> SubstitutesResponse:
    now = datetime.now(timezone.utc)
    reference_stock = facility_stock(db, reference.id, facility_id, now)
    summary = medicine_summary(reference, source)

    if reference.match_status != sm.MATCHABLE or reference.match_key is None:
        return SubstitutesResponse(
            reference=summary,
            reference_stock=reference_stock,
            facility_id=facility_id,
            comparable=False,
            not_comparable_reasons=summary.insufficient_reasons or ["insufficient_metadata"],
            candidates=[],
            total_candidates=0,
            notice=NOTICE,
            generated_at=now,
        )

    same_group = (
        Medicine.match_key == reference.match_key,
        Medicine.match_status == sm.MATCHABLE,
        Medicine.id != reference.id,
    )
    # Rank the WHOLE match group before truncating: a real group can hold
    # hundreds of products, and cutting first would silently drop the one the
    # facility actually has in stock, or the cheapest.
    light = db.execute(select(Medicine.id, Medicine.unit_price, Medicine.pack_unit).where(*same_group)).all()
    stock_by_id = _stock_by_medicine(db, facility_id, now, *same_group)
    unknown = FacilityStockInfo(status="unknown")
    ranked = sm.rank_candidates(
        [sm.RankedCandidate(row.id, stock_by_id.get(row.id, unknown).status, row.unit_price, row.pack_unit) for row in light],
        reference.pack_unit if reference.unit_price is not None else None,
    )
    top_ids = [r.medicine_id for r in ranked[:MAX_CANDIDATES]]

    rows = db.scalars(select(Medicine).options(selectinload(Medicine.ingredients)).where(Medicine.id.in_(top_ids))).all() if top_ids else []
    by_id = {m.id: m for m in rows}
    sources = {source.id: source}
    candidates = []
    for medicine_id in top_ids:
        med = by_id[medicine_id]
        if med.source_id not in sources:
            sources[med.source_id] = db.get(MedicineSource, med.source_id)
        comparable = (
            reference.unit_price is not None
            and med.unit_price is not None
            and med.pack_unit == reference.pack_unit
            and sources[med.source_id].currency == source.currency
            and sources[med.source_id].price_basis == source.price_basis
        )
        candidates.append(
            SubstituteCandidate(
                medicine=medicine_summary(med, sources[med.source_id]),
                stock=stock_by_id.get(med.id, unknown),
                price_comparable=comparable,
                saving_percent=sm.saving_percent(reference.unit_price, med.unit_price) if comparable else None,
            )
        )

    return SubstitutesResponse(
        reference=summary,
        reference_stock=reference_stock,
        facility_id=facility_id,
        comparable=True,
        not_comparable_reasons=[],
        candidates=candidates,
        total_candidates=len(ranked),
        notice=NOTICE,
        generated_at=now,
    )
