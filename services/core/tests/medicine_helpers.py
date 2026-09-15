"""Shared helpers for tests that need imported (synthetic) medicines."""
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.medicine_import import ImportSpec, import_medicine_csv, sha256_file
from app.models import Medicine

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "medicines_synthetic.csv"


def synthetic_spec(path: Path = FIXTURE_CSV, **overrides) -> ImportSpec:
    values = dict(
        name="SYNTHETIC test fixture (not real data)",
        source_url="file://tests/fixtures/medicines_synthetic.csv",
        license="test-only",
        sha256=sha256_file(path),
        source_version="fixture",
        source_updated_on=None,
        price_basis="unspecified",
        currency="INR",
    )
    values.update(overrides)
    return ImportSpec(**values)


def import_synthetic(db: Session, tmp_path: Path | None = None):
    path = FIXTURE_CSV
    if tmp_path is not None:
        path = tmp_path / "medicines.csv"
        shutil.copy(FIXTURE_CSV, path)
    return import_medicine_csv(db, path, synthetic_spec(path))


def medicine_by_record(db: Session, record_id: str) -> Medicine:
    return db.scalar(select(Medicine).where(Medicine.source_record_id == record_id))
