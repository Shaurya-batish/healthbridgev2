import uuid
from datetime import date, timedelta


def _create_follow_up(client, **overrides):
    payload = {
        "patient_id": str(uuid.uuid4()),
        "encounter_id": str(uuid.uuid4()),
        "facility_id": str(uuid.uuid4()),
        "scheduled_date": str(date.today()),
        "reason": "check nutrition recovery",
        **overrides,
    }
    res = client.post("/follow-ups", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_defaults_to_scheduled(client):
    follow_up = _create_follow_up(client)
    assert follow_up["status"] == "scheduled"


def test_due_by_filters_out_future_follow_ups(client):
    facility_id = str(uuid.uuid4())
    _create_follow_up(client, facility_id=facility_id, scheduled_date=str(date.today()))
    _create_follow_up(client, facility_id=facility_id, scheduled_date=str(date.today() + timedelta(days=30)))

    due_today = client.get(f"/follow-ups/facility/{facility_id}", params={"due_by": str(date.today())}).json()
    assert len(due_today) == 1

    all_scheduled = client.get(f"/follow-ups/facility/{facility_id}").json()
    assert len(all_scheduled) == 2


def test_completed_follow_ups_excluded_from_due_list(client):
    facility_id = str(uuid.uuid4())
    follow_up = _create_follow_up(client, facility_id=facility_id)
    client.post(f"/follow-ups/{follow_up['id']}/status", json={"status": "completed"})

    due = client.get(f"/follow-ups/facility/{facility_id}").json()
    assert due == []


def test_patient_follow_up_history(client):
    patient_id = str(uuid.uuid4())
    _create_follow_up(client, patient_id=patient_id)
    _create_follow_up(client, patient_id=patient_id)
    history = client.get(f"/follow-ups/patient/{patient_id}").json()
    assert len(history) == 2
