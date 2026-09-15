"""Idempotent importer for licensed medicine reference data.

Only real, licensed source files are imported -- nothing here generates
medicines or prices. The supported format is the Indian Medicine Dataset CSV
(junioralive/Indian-Medicine-Dataset, MIT). Verified 2026-09-15:

    url     https://raw.githubusercontent.com/junioralive/Indian-Medicine-Dataset/main/DATA/indian_medicine_data.csv
    sha256  c9de0182474f652b7790a85bf534d0df9bd814575fcbda7109696d0fb3bec042
    bytes   31,807,827  (253,973 rows)
    commit  45c86f98e5216d6302a8ce98d80bdac28b959219 (2024-01-30, last change to the CSV)

The dataset README describes the price column only as "price ... in Indian
Rupees" -- it does not say MRP or selling price -- so the basis is recorded
as "unspecified" and shown that way.

Guarantees:
- checksum is verified BEFORE any row is read; mismatch aborts with nothing written;
- the header must match the expected schema exactly;
- rows are validated individually; invalid rows are rejected and counted, never guessed;
- duplicate record ids within one file are rejected (first occurrence wins);
- re-importing an identical file changes nothing (row fingerprints);
- medicine ids stay stable across re-imports (upsert by source + record id),
  so stock links and prescriptions keep pointing at the same identity;
- the whole import is one transaction.
"""
from __future__ import annotations

import csv
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app import salt_matching as sm
from app.models import Medicine, MedicineIngredient, MedicineSource

INDIAN_MEDICINE_DATASET = {
    "name": "junioralive/Indian-Medicine-Dataset",
    "source_url": "https://raw.githubusercontent.com/junioralive/Indian-Medicine-Dataset/main/DATA/indian_medicine_data.csv",
    "license": "MIT (Copyright (c) 2024 JuniorAlive)",
    "sha256": "c9de0182474f652b7790a85bf534d0df9bd814575fcbda7109696d0fb3bec042",
    "source_version": "git 45c86f98e5216d6302a8ce98d80bdac28b959219",
    "source_updated_on": date(2024, 1, 30),
    "price_basis": "unspecified",
    "currency": "INR",
}

EXPECTED_HEADER = [
    "id",
    "name",
    "price(₹)",
    "Is_discontinued",
    "manufacturer_name",
    "type",
    "pack_size_label",
    "short_composition1",
    "short_composition2",
]

_MAX_REJECT_SAMPLES = 50
_BATCH = 2000


class ImportAborted(Exception):
    """Raised before anything is written (checksum/schema problems)."""


@dataclass(frozen=True)
class ImportSpec:
    name: str
    source_url: str
    license: str
    sha256: str | None  # expected checksum; None only for explicitly unverified local files
    source_version: str | None
    source_updated_on: date | None
    price_basis: str
    currency: str


@dataclass
class ImportReport:
    source_id: uuid.UUID | None = None
    sha256: str = ""
    rows_read: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    matchable: int = 0
    reject_samples: list[tuple[int, str]] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_hash(row: dict[str, str]) -> str:
    joined = "\x1f".join(row.get(col, "") or "" for col in EXPECTED_HEADER)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _parse_price(raw: str) -> Decimal | None:
    text = (raw or "").strip()
    if not text:
        return None
    value = Decimal(text)  # raises InvalidOperation for garbage
    if value < 0:
        raise InvalidOperation("negative price")
    return value


def _parse_bool(raw: str) -> bool:
    text = (raw or "").strip().upper()
    if text == "TRUE":
        return True
    if text == "FALSE":
        return False
    raise ValueError("Is_discontinued must be TRUE or FALSE")


def _medicine_values(row: dict[str, str], source_id: uuid.UUID, row_hash: str) -> tuple[dict, list[dict]]:
    name = row["name"].strip()
    discontinued = _parse_bool(row["Is_discontinued"])
    price = _parse_price(row["price(₹)"])
    identity = sm.build_identity(
        name=name,
        pack_size_label=row["pack_size_label"],
        compositions=[row["short_composition1"], row["short_composition2"]],
        is_discontinued=discontinued,
    )
    unit_price = sm.comparable_unit_price(price, identity.pack)
    generic = " + ".join(i.name for i in identity.ingredients) or None
    values = {
        "source_id": source_id,
        "source_record_id": row["id"].strip(),
        "source_row_hash": row_hash,
        "brand_name": name,
        "name_normalized": " ".join(name.lower().split()),
        "generic_name": generic,
        "manufacturer": (row["manufacturer_name"] or "").strip() or None,
        "dosage_form": identity.dosage_form,
        "route": identity.route,
        "release_type": identity.release_type,
        "pack_label": (row["pack_size_label"] or "").strip() or None,
        "pack_quantity": identity.pack.quantity if identity.pack else None,
        "pack_unit": identity.pack.unit if identity.pack else None,
        "price": price,
        "unit_price": unit_price,
        "is_discontinued": discontinued,
        "match_status": identity.match_status,
        "match_key": identity.match_key,
        "insufficient_reasons": ",".join(identity.insufficient_reasons) or None,
    }
    ingredients = [
        {
            "position": pos,
            "name": ing.name,
            "strength_value": ing.strength.value if ing.strength else None,
            "strength_unit": ing.strength.unit if ing.strength else None,
            "raw_text": ing.raw,
        }
        for pos, ing in enumerate(identity.ingredients)
    ]
    return values, ingredients


def import_medicine_csv(db: Session, path: Path, spec: ImportSpec) -> ImportReport:
    report = ImportReport()
    actual = sha256_file(path)
    report.sha256 = actual
    if spec.sha256 is not None and actual != spec.sha256.lower():
        raise ImportAborted(f"checksum mismatch: expected {spec.sha256}, got {actual}")

    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != EXPECTED_HEADER:
            raise ImportAborted(f"unexpected header {reader.fieldnames!r}; expected {EXPECTED_HEADER!r}")

        source = db.scalar(select(MedicineSource).where(MedicineSource.name == spec.name))
        if source is None:
            source = MedicineSource(name=spec.name, source_url=spec.source_url, license=spec.license, sha256=actual,
                                    price_basis=spec.price_basis, currency=spec.currency)
            db.add(source)
        source.source_url = spec.source_url
        source.license = spec.license
        source.sha256 = actual
        source.source_version = spec.source_version
        source.source_updated_on = spec.source_updated_on
        source.price_basis = spec.price_basis
        source.currency = spec.currency
        db.flush()
        report.source_id = source.id

        existing = {
            record_id: (medicine_id, row_hash)
            for record_id, medicine_id, row_hash in db.execute(
                select(Medicine.source_record_id, Medicine.id, Medicine.source_row_hash).where(Medicine.source_id == source.id)
            )
        }
        seen: set[str] = set()
        pending_inserts: list[dict] = []
        pending_ingredients: list[dict] = []

        def flush_batch() -> None:
            if pending_inserts:
                db.execute(insert(Medicine), pending_inserts)
                pending_inserts.clear()
            if pending_ingredients:
                db.execute(insert(MedicineIngredient), pending_ingredients)
                pending_ingredients.clear()

        for line_no, row in enumerate(reader, start=2):
            report.rows_read += 1
            record_id = (row.get("id") or "").strip()
            reason = None
            if not record_id:
                reason = "missing_record_id"
            elif record_id in seen:
                reason = "duplicate_record_id"
            elif not (row.get("name") or "").strip():
                reason = "missing_name"
            if reason is None:
                row_hash = _row_hash(row)
                try:
                    values, ingredients = _medicine_values(row, source.id, row_hash)
                except (InvalidOperation, ValueError) as exc:
                    reason = "invalid_price" if isinstance(exc, InvalidOperation) else "invalid_discontinued_flag"
            if reason is not None:
                report.rejected += 1
                if len(report.reject_samples) < _MAX_REJECT_SAMPLES:
                    report.reject_samples.append((line_no, reason))
                continue

            seen.add(record_id)
            if values["match_status"] == sm.MATCHABLE:
                report.matchable += 1

            prior = existing.get(record_id)
            if prior is None:
                medicine_id = uuid.uuid4()
                pending_inserts.append({"id": medicine_id, **values})
                pending_ingredients.extend({"id": uuid.uuid4(), "medicine_id": medicine_id, **ing} for ing in ingredients)
                report.inserted += 1
            elif prior[1] == row_hash:
                report.unchanged += 1
            else:
                medicine_id = prior[0]
                db.execute(update(Medicine).where(Medicine.id == medicine_id).values(**values))
                db.execute(delete(MedicineIngredient).where(MedicineIngredient.medicine_id == medicine_id))
                pending_ingredients.extend({"id": uuid.uuid4(), "medicine_id": medicine_id, **ing} for ing in ingredients)
                report.updated += 1

            if len(pending_inserts) >= _BATCH or len(pending_ingredients) >= _BATCH * 2:
                flush_batch()

        flush_batch()

    source.row_count = report.rows_read - report.rejected
    source.matchable_count = report.matchable
    source.rejected_count = report.rejected
    db.commit()
    return report
