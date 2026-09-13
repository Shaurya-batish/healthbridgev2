import uuid


def _create_stock(client, **overrides):
    payload = {
        "facility_id": str(uuid.uuid4()),
        "medicine_name": "Paracetamol 500mg",
        "unit": "tablets",
        "reorder_threshold": 20,
        "initial_quantity": 100,
        **overrides,
    }
    res = client.post("/medicine-stock", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_records_initial_quantity_as_a_real_movement(client):
    stock = _create_stock(client)
    assert stock["quantity_on_hand"] == 100

    movements = client.get(f"/medicine-stock/{stock['id']}/movements").json()
    assert len(movements) == 1
    assert movements[0]["change_qty"] == 100
    assert movements[0]["reason"] == "restock"


def test_dispense_reduces_quantity_and_records_movement(client):
    stock = _create_stock(client)
    res = client.post(f"/medicine-stock/{stock['id']}/adjust", json={"change_qty": -30, "reason": "dispensed"})
    assert res.status_code == 200
    assert res.json()["quantity_on_hand"] == 70

    movements = client.get(f"/medicine-stock/{stock['id']}/movements").json()
    assert len(movements) == 2  # initial restock + this dispense


def test_cannot_dispense_more_than_on_hand(client):
    stock = _create_stock(client, initial_quantity=10)
    res = client.post(f"/medicine-stock/{stock['id']}/adjust", json={"change_qty": -50, "reason": "dispensed"})
    assert res.status_code == 400

    # Quantity must be unchanged -- the rejected adjustment must not have partially applied.
    refreshed = client.get(f"/medicine-stock/facility/{stock['facility_id']}").json()
    assert refreshed[0]["quantity_on_hand"] == 10


def test_restock_increases_quantity(client):
    stock = _create_stock(client, initial_quantity=5)
    res = client.post(f"/medicine-stock/{stock['id']}/adjust", json={"change_qty": 45, "reason": "restock"})
    assert res.status_code == 200
    assert res.json()["quantity_on_hand"] == 50


def test_negative_initial_quantity_rejected(client):
    res = client.post(
        "/medicine-stock",
        json={
            "facility_id": str(uuid.uuid4()),
            "medicine_name": "ORS sachets",
            "initial_quantity": -5,
        },
    )
    assert res.status_code == 400


def test_list_by_facility(client):
    facility_id = str(uuid.uuid4())
    _create_stock(client, facility_id=facility_id, medicine_name="ORS")
    _create_stock(client, facility_id=facility_id, medicine_name="Zinc tablets")
    items = client.get(f"/medicine-stock/facility/{facility_id}").json()
    assert {i["medicine_name"] for i in items} == {"ORS", "Zinc tablets"}
