"""Importer behaviour against a real (SQLite) database using the SYNTHETIC
fixture -- see tests/fixtures/README.md. Real-dataset import evidence is
recorded separately in docs, not asserted here."""
import shutil

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import salt_matching as sm
from app.medicine_import import ImportAborted, import_medicine_csv
from app.models import Medicine, MedicineIngredient, MedicineSource
from tests.medicine_helpers import FIXTURE_CSV, import_synthetic, medicine_by_record, synthetic_spec


@pytest.fixture
def db(db_engine):
    session = sessionmaker(bind=db_engine)()
    yield session
    session.close()


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_import_validates_rows_and_records_provenance(db):
    report = import_synthetic(db)
    assert report.rows_read == 17
    assert report.rejected == 4  # missing name, invalid price, duplicate id, invalid flag
    assert sorted(r for _, r in report.reject_samples) == [
        "duplicate_record_id",
        "invalid_discontinued_flag",
        "invalid_price",
        "missing_name",
    ]
    assert report.inserted == 13
    assert _count(db, Medicine) == 13

    source = db.scalar(select(MedicineSource))
    assert source.sha256 == report.sha256
    assert source.price_basis == "unspecified" and source.currency == "INR"
    assert source.row_count == 13 and source.rejected_count == 4

    # The first occurrence of a duplicated id wins; the duplicate is not imported.
    assert medicine_by_record(db, "2").brand_name == "SYNTHETIC Cheapara 650 Tablet"


def test_structured_identity_is_persisted(db):
    import_synthetic(db)
    coamox = medicine_by_record(db, "9")
    assert coamox.match_status == sm.MATCHABLE
    assert coamox.dosage_form == "tablet" and coamox.route == "oral" and coamox.release_type == sm.RELEASE_NOT_STATED
    assert [(i.name, i.strength_unit) for i in coamox.ingredients] == [("amoxycillin", "mg"), ("clavulanic acid", "mg")]
    assert medicine_by_record(db, "10").match_key == coamox.match_key  # reversed columns, 0.5gm

    injection = medicine_by_record(db, "11")
    assert injection.match_status == sm.INSUFFICIENT and "route_not_stated" in injection.insufficient_reasons
    na = medicine_by_record(db, "12")
    assert na.match_status == sm.INSUFFICIENT and "ingredient_strength_unparseable" in na.insufficient_reasons

    zero_pack = medicine_by_record(db, "15")
    assert zero_pack.unit_price is None and zero_pack.pack_quantity is None


def test_reimporting_the_same_file_is_a_no_op(db):
    first = import_synthetic(db)
    ids = {m.source_record_id: m.id for m in db.scalars(select(Medicine))}
    ingredient_count = _count(db, MedicineIngredient)

    second = import_synthetic(db)
    assert second.inserted == 0 and second.updated == 0
    assert second.unchanged == first.inserted
    assert {m.source_record_id: m.id for m in db.scalars(select(Medicine))} == ids
    assert _count(db, MedicineIngredient) == ingredient_count
    assert _count(db, MedicineSource) == 1


def test_changed_rows_update_in_place_keeping_ids_stable(db, tmp_path):
    import_synthetic(db)
    original_id = medicine_by_record(db, "5").id

    changed = tmp_path / "medicines.csv"
    text = FIXTURE_CSV.read_text(encoding="utf-8").replace(
        "5,SYNTHETIC Para 500 Tablet,10.00", "5,SYNTHETIC Para 500 Tablet,12.00"
    )
    changed.write_text(text, encoding="utf-8")
    report = import_medicine_csv(db, changed, synthetic_spec(changed))

    assert report.updated == 1 and report.inserted == 0
    row = medicine_by_record(db, "5")
    assert row.id == original_id
    assert str(row.price) in {"12.00", "12"}
    assert len(row.ingredients) == 1


def test_checksum_mismatch_aborts_before_writing_anything(db, tmp_path):
    path = tmp_path / "medicines.csv"
    shutil.copy(FIXTURE_CSV, path)
    with pytest.raises(ImportAborted, match="checksum mismatch"):
        import_medicine_csv(db, path, synthetic_spec(path, sha256="0" * 64))
    db.rollback()
    assert _count(db, Medicine) == 0 and _count(db, MedicineSource) == 0


def test_unexpected_header_aborts(db, tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("id,name,price\n1,X,1\n", encoding="utf-8")
    with pytest.raises(ImportAborted, match="unexpected header"):
        import_medicine_csv(db, path, synthetic_spec(path))
    db.rollback()
    assert _count(db, Medicine) == 0
