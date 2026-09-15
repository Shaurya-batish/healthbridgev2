"""Search + facility-scoped comparison with a real inventory join (SQLite,
SYNTHETIC fixture medicines)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import AuditLog, MedicineStock, MedicineStockMovement
from tests.conftest import auth_headers
from tests.medicine_helpers import import_synthetic, medicine_by_record


@pytest.fixture
def seeded(db_engine):
    session = sessionmaker(bind=db_engine)()
    import_synthetic(session)
    ids = {rid: medicine_by_record(session, rid).id for rid in ("1", "2", "3", "4", "5", "6", "7", "8", "11", "15")}
    session.close()
    return ids


def _stock(db_engine, facility_id, medicine_id, qty, counted_days_ago=0):
    session = sessionmaker(bind=db_engine)()
    row = MedicineStock(facility_id=facility_id, medicine_name=f"stock-{uuid.uuid4().hex[:6]}", medicine_id=medicine_id, quantity_on_hand=qty)
    session.add(row)
    session.flush()
    session.add(
        MedicineStockMovement(
            stock_id=row.id,
            change_qty=qty,
            reason="restock",
            created_at=datetime.now(timezone.utc) - timedelta(days=counted_days_ago),
        )
    )
    session.commit()
    session.close()


def test_search_matches_brand_and_ingredient_and_validates_paging(client, seeded):
    res = client.get("/medicines", params={"q": "coamox"})
    assert res.status_code == 200
    assert {i["brand_name"] for i in res.json()["items"]} == {"SYNTHETIC Coamox Tablet", "SYNTHETIC Coamox Rev Tablet"}

    res = client.get("/medicines", params={"q": "clavulanic", "limit": 1})
    body = res.json()
    assert body["total"] == 2 and len(body["items"]) == 1

    assert client.get("/medicines", params={"q": "p"}).status_code == 422
    assert client.get("/medicines", params={"q": "para", "limit": 51}).status_code == 422
    assert client.get("/medicines", params={"q": "para", "offset": -1}).status_code == 422
    # LIKE wildcards are matched literally, not as wildcards.
    assert client.get("/medicines", params={"q": "%%"}).json()["total"] == 0


def test_search_requires_authentication(client, seeded):
    client.headers.pop("Authorization")
    assert client.get("/medicines", params={"q": "para"}).status_code == 401


def test_substitutes_only_exact_matches_ranked_by_real_stock_then_price(client, db_engine, seeded):
    facility = uuid.uuid4()
    _stock(db_engine, facility, seeded["4"], qty=40)  # dearer, but physically available
    _stock(db_engine, facility, seeded["3"], qty=0)  # counted at zero
    _stock(db_engine, facility, seeded["2"], qty=100, counted_days_ago=90)  # stale count

    res = client.get(f"/medicines/{seeded['1']}/substitutes", params={"facility_id": str(facility)})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["comparable"] is True
    assert "does not authorise substitution" in body["notice"]
    assert body["reference"]["unit_price"] == "2"

    names = [c["medicine"]["brand_name"] for c in body["candidates"]]
    # 500mg, SR, suspension and the discontinued product are never candidates.
    assert names == [
        "SYNTHETIC Dearpara 650 Tablet",  # available
        "SYNTHETIC Cheapara 650 Tablet",  # stale
        "SYNTHETIC Zeropack 650 Tablet",  # unknown stock, no comparable price
        "SYNTHETIC Midpara 650 Tablet",  # unavailable (0 on hand)
    ]
    by_name = {c["medicine"]["brand_name"]: c for c in body["candidates"]}
    assert by_name["SYNTHETIC Dearpara 650 Tablet"]["stock"]["status"] == "available"
    assert by_name["SYNTHETIC Dearpara 650 Tablet"]["saving_percent"] is None  # dearer: never a saving
    assert by_name["SYNTHETIC Cheapara 650 Tablet"]["stock"]["status"] == "stale"
    assert by_name["SYNTHETIC Cheapara 650 Tablet"]["saving_percent"] == 83
    assert by_name["SYNTHETIC Midpara 650 Tablet"]["stock"]["status"] == "unavailable"
    assert by_name["SYNTHETIC Midpara 650 Tablet"]["saving_percent"] == 25
    assert by_name["SYNTHETIC Zeropack 650 Tablet"]["price_comparable"] is False
    assert by_name["SYNTHETIC Zeropack 650 Tablet"]["stock"]["status"] == "unknown"


def test_large_groups_are_ranked_before_truncation(client, db_engine, seeded, tmp_path, monkeypatch):
    """Regression: the candidate query used LIMIT before ranking, so in a real
    match group larger than the limit an in-stock product could vanish."""
    from app import medicine_comparison
    from app.medicine_import import import_medicine_csv
    from tests.medicine_helpers import FIXTURE_CSV, synthetic_spec

    monkeypatch.setattr(medicine_comparison, "MAX_CANDIDATES", 5)
    header = FIXTURE_CSV.read_text(encoding="utf-8").splitlines()[0]
    rows = [f"{900 + i},SYNTHETIC Bulk {i} 650 Tablet,{1 + i}.00,FALSE,Synthetic Test Pharma Z,allopathy,strip of 10 tablets,Paracetamol (650mg)," for i in range(12)]
    csv_path = tmp_path / "bulk.csv"
    csv_path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    session = sessionmaker(bind=db_engine)()
    import_medicine_csv(session, csv_path, synthetic_spec(csv_path, name="SYNTHETIC bulk fixture"))
    priciest = medicine_by_record(session, "911").id  # ₹12.00 / 10 -- still cheaper than the reference
    session.close()

    facility = uuid.uuid4()
    _stock(db_engine, facility, priciest, qty=7)
    body = client.get(f"/medicines/{seeded['1']}/substitutes", params={"facility_id": str(facility)}).json()
    assert body["total_candidates"] == 16  # 4 fixture matches (records 2, 3, 4, 15) + 12 bulk
    assert len(body["candidates"]) == 5
    assert body["candidates"][0]["medicine"]["id"] == str(priciest)
    assert body["candidates"][0]["stock"]["status"] == "available"
    prices = [float(c["medicine"]["unit_price"]) for c in body["candidates"][1:] if c["price_comparable"]]
    assert prices == sorted(prices)


def test_stock_at_another_facility_is_not_reported(client, db_engine, seeded):
    here, elsewhere = uuid.uuid4(), uuid.uuid4()
    _stock(db_engine, elsewhere, seeded["2"], qty=100)
    body = client.get(f"/medicines/{seeded['1']}/substitutes", params={"facility_id": str(here)}).json()
    assert {c["stock"]["status"] for c in body["candidates"]} == {"unknown"}


def test_non_matchable_reference_returns_honest_empty_comparison(client, seeded):
    body = client.get(f"/medicines/{seeded['11']}/substitutes", params={"facility_id": str(uuid.uuid4())}).json()
    assert body["comparable"] is False
    assert "route_not_stated" in body["not_comparable_reasons"]
    assert body["candidates"] == []


def test_substitutes_are_facility_scoped(db_engine, seeded):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    factory = sessionmaker(bind=db_engine)
    app.dependency_overrides[get_db] = lambda: factory()
    try:
        own, other = uuid.uuid4(), uuid.uuid4()
        asha = TestClient(app, headers=auth_headers("asha", own))
        assert asha.get(f"/medicines/{seeded['1']}/substitutes", params={"facility_id": str(other)}).status_code == 403
        assert asha.get(f"/medicines/{seeded['1']}/substitutes", params={"facility_id": str(own)}).status_code == 200
        assert asha.get(f"/medicines/{seeded['1']}/substitutes").status_code == 422  # facility_id required
        assert asha.get(f"/medicines/{uuid.uuid4()}/substitutes", params={"facility_id": str(own)}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_linking_stock_is_facility_scoped_and_audited(client, db_engine, seeded):
    facility = uuid.uuid4()
    created = client.post("/medicine-stock", json={"facility_id": str(facility), "medicine_name": "Paracetamol 650", "initial_quantity": 20}).json()
    assert created["medicine_id"] is None

    res = client.post(f"/medicine-stock/{created['id']}/link", json={"medicine_id": str(seeded["2"])})
    assert res.status_code == 200 and res.json()["medicine_id"] == str(seeded["2"])
    assert res.json()["quantity_on_hand"] == 20  # linking never changes quantity

    assert client.post(f"/medicine-stock/{created['id']}/link", json={"medicine_id": str(uuid.uuid4())}).status_code == 404

    session = sessionmaker(bind=db_engine)()
    audit = session.scalars(select(AuditLog).where(AuditLog.action == "medicine_stock_linked")).all()
    assert len(audit) == 1 and audit[0].details["medicine_id"] == str(seeded["2"])
    session.close()

    from fastapi.testclient import TestClient

    from app.main import app

    outsider = TestClient(app, headers=auth_headers("doctor", uuid.uuid4()))
    assert outsider.post(f"/medicine-stock/{created['id']}/link", json={"medicine_id": None}).status_code == 403
