import uuid


def _create_referral(client, **overrides):
    payload = {
        "patient_id": str(uuid.uuid4()),
        "encounter_id": str(uuid.uuid4()),
        "from_facility_id": str(uuid.uuid4()),
        "to_facility_id": str(uuid.uuid4()),
        "reason": "needs specialist evaluation",
        **overrides,
    }
    res = client.post("/referrals", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_referral_defaults_to_pending(client):
    body = _create_referral(client)
    assert body["status"] == "pending"


def test_referral_visible_from_both_facilities(client):
    from_facility = str(uuid.uuid4())
    to_facility = str(uuid.uuid4())
    _create_referral(client, from_facility_id=from_facility, to_facility_id=to_facility)

    sent = client.get(f"/referrals/facility/{from_facility}").json()
    received = client.get(f"/referrals/facility/{to_facility}").json()
    assert len(sent) == 1
    assert len(received) == 1
    assert sent[0]["id"] == received[0]["id"]


def test_referral_status_transition(client):
    referral = _create_referral(client)
    res = client.post(f"/referrals/{referral['id']}/status", json={"status": "accepted"})
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"


def test_unknown_referral_status_update_404s(client):
    res = client.post(f"/referrals/{uuid.uuid4()}/status", json={"status": "accepted"})
    assert res.status_code == 404


def test_patient_referral_history(client):
    patient_id = str(uuid.uuid4())
    _create_referral(client, patient_id=patient_id)
    _create_referral(client, patient_id=patient_id)
    history = client.get(f"/referrals/patient/{patient_id}").json()
    assert len(history) == 2
