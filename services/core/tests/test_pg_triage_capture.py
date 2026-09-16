"""Real-Postgres tests: multilingual complaint provenance is persisted with the
triage decision, inconsistent captures are refused with nothing written, and
the existing triage behaviour (checklist path, queue order, RED escalation,
facility scoping) is unchanged."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import AuditLog, ComplaintCapture, EscalationEvent, TriageRecord
from tests.pg_seed import new_encounter, seed_world


@pytest.fixture
def world(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    w = seed_world(session)
    session.close()
    return w


def _now():
    return datetime.now(timezone.utc)


def typed_hindi_capture(**overrides):
    captured = _now() - timedelta(minutes=2)
    capture = {
        "client_capture_id": str(uuid.uuid4()),
        "input_source": "typed",
        "language": "hi",
        "original_text": "बच्चे को तीन दिन से बुखार है",
        "machine_translation_en": "The child has had fever for three days",
        "translation_engine": "argostranslate 1.11.0",
        "translation_status": "manual",
        "confirmed_original_text": "बच्चे को सात दिन से बुखार है",
        "confirmed_text_en": "The child has had fever for seven days",
        "captured_at": captured.isoformat(),
        "confirmed_at": _now().isoformat(),
    }
    capture.update(overrides)
    return capture


def triage_payload(encounter_id, capture=None, **overrides):
    payload = {
        "encounter_id": str(encounter_id),
        "complaint_text": capture["confirmed_text_en"] if capture else None,
        "source": "llm" if capture else "checklist",
        "extracted_facts": {"fever_present": True, "fever_duration_days": 7},
        "severity": "YELLOW",
        "rule_id": "FEV-02",
        "rule_version": "1.0.0",
        "complaint_capture": capture,
    }
    payload.update(overrides)
    return payload


def _counts(pg_engine):
    s = sessionmaker(bind=pg_engine)()
    try:
        return (s.scalar(select(func.count()).select_from(TriageRecord)), s.scalar(select(func.count()).select_from(ComplaintCapture)))
    finally:
        s.close()


def test_typed_hindi_capture_persists_originals_corrections_and_audit(pg_client, pg_engine, world):
    capture = typed_hindi_capture()
    res = pg_client.post("/triage", json=triage_payload(world.encounter, capture), headers=world.headers("asha_a"))
    assert res.status_code == 201, res.text
    body = res.json()["triage_record"]
    assert body["complaint_text"] == "The child has had fever for seven days"
    stored = body["complaint_capture"]
    assert stored["language"] == "hi" and stored["input_source"] == "typed"
    assert stored["original_text"] == "बच्चे को तीन दिन से बुखार है"  # first capture preserved
    assert stored["confirmed_original_text"] == "बच्चे को सात दिन से बुखार है"
    assert stored["machine_translation_en"] == "The child has had fever for three days"
    assert stored["original_edited"] is True and stored["english_edited"] is True
    assert stored["translation_status"] == "manual"

    s = sessionmaker(bind=pg_engine)()
    row = s.scalar(select(ComplaintCapture))
    assert row.captured_by_user_id == world.asha_a  # from the JWT, not the client
    audit = s.scalar(select(AuditLog).where(AuditLog.action == "triage_decision"))
    assert audit.details["rule_id"] == "FEV-02"
    assert audit.details["complaint_capture"]["confirmed_text_en"] == "The child has had fever for seven days"
    assert audit.details["complaint_capture"]["original_text"] == "बच्चे को तीन दिन से बुखार है"
    s.close()


def test_first_machine_translation_is_preserved_after_retranslation(pg_client, pg_engine, world):
    """Voice: Whisper's English is kept even though the ASHA corrected the
    transcript and Argos produced the English that was finally confirmed."""
    capture = typed_hindi_capture(
        input_source="voice",
        original_text="बच्चे को खांसी है",
        initial_machine_translation_en="The child has a cough",
        initial_translation_engine="faster-whisper small",
        confirmed_original_text="बच्चे को खांसी और तेज़ सांस है",
        machine_translation_en="The child has a cough and fast breathing",
        translation_engine="argostranslate 1.11.0",
        translation_status="machine",
        confirmed_text_en="The child has a cough and fast breathing",
        consent_confirmed_at=(_now() - timedelta(minutes=3)).isoformat(),
        audio_sha256="c" * 64,
        audio_duration_seconds=5.0,
        audio_mime_type="audio/webm;codecs=opus",
    )
    res = pg_client.post("/triage", json=triage_payload(world.encounter, capture), headers=world.headers("asha_a"))
    assert res.status_code == 201, res.text
    stored = res.json()["triage_record"]["complaint_capture"]
    assert stored["initial_machine_translation_en"] == "The child has a cough"
    assert stored["initial_translation_engine"] == "faster-whisper small"
    assert stored["machine_translation_en"] == "The child has a cough and fast breathing"
    assert stored["original_edited"] is True

    s = sessionmaker(bind=pg_engine)()
    audit = s.scalar(select(AuditLog).where(AuditLog.action == "triage_decision"))
    assert audit.details["complaint_capture"]["initial_machine_translation_en"] == "The child has a cough"
    s.close()

    bad = typed_hindi_capture(initial_machine_translation_en="orphan text without an engine")
    res = pg_client.post("/triage", json=triage_payload(new_encounter_for(pg_engine, world), bad), headers=world.headers("asha_a"))
    assert res.status_code == 422 and "initial_translation_requires_text_and_engine" in res.text


def new_encounter_for(pg_engine, world):
    s = sessionmaker(bind=pg_engine)()
    try:
        encounter_id = new_encounter(s, world.patient, world.facility_a, 99)
        s.commit()
        return encounter_id
    finally:
        s.close()


def test_voice_capture_with_consent_and_audio_metadata_is_accepted(pg_client, world):
    capture = typed_hindi_capture(
        input_source="voice",
        translation_engine="faster-whisper small",
        machine_translation_en="The child has had fever for seven days",
        translation_status="machine",
        original_text="बच्चे को सात दिन से बुखार है",
        consent_confirmed_at=(_now() - timedelta(minutes=3)).isoformat(),
        audio_sha256="a" * 64,
        audio_duration_seconds=6.4,
        audio_mime_type="audio/webm;codecs=opus",
    )
    res = pg_client.post("/triage", json=triage_payload(world.encounter, capture), headers=world.headers("asha_a"))
    assert res.status_code == 201, res.text
    stored = res.json()["triage_record"]["complaint_capture"]
    assert stored["input_source"] == "voice" and stored["audio_duration_seconds"] == 6.4
    assert stored["original_edited"] is False and stored["english_edited"] is False


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"translation_status": "stale"}, "translation_stale_reconfirm_required"),
        ({"translation_status": "machine"}, "edited_translation_must_be_marked_manual"),
        ({"translation_status": "not_required"}, "non_english_capture_requires_translation"),
        ({"input_source": "voice"}, "voice_capture_requires_recording_consent"),
        ({"audio_sha256": "b" * 64}, "typed_capture_must_not_carry_audio_metadata"),
        ({"confirmed_at": "2020-01-01T00:00:00+00:00"}, "confirmed_before_captured"),
        ({"language": "fr"}, None),
    ],
)
def test_inconsistent_captures_are_rejected_and_nothing_is_written(pg_client, pg_engine, world, overrides, message):
    capture = typed_hindi_capture(**overrides)
    res = pg_client.post("/triage", json=triage_payload(world.encounter, capture), headers=world.headers("asha_a"))
    assert res.status_code == 422, res.text
    if message:
        assert message in res.text
    assert _counts(pg_engine) == (0, 0)


def test_extraction_input_must_be_exactly_the_confirmed_english(pg_client, pg_engine, world):
    capture = typed_hindi_capture()
    payload = triage_payload(world.encounter, capture, complaint_text="The child has had fever for three days")
    res = pg_client.post("/triage", json=payload, headers=world.headers("asha_a"))
    assert res.status_code == 422 and "complaint_text_must_equal_confirmed_english" in res.text
    assert _counts(pg_engine) == (0, 0)


def test_confirmed_capture_is_kept_when_severity_came_from_the_checklist(pg_client, world):
    """Extraction unavailable after the ASHA confirmed the complaint: the
    checklist decides severity, and the confirmed provenance is still stored."""
    capture = typed_hindi_capture()
    payload = triage_payload(world.encounter, capture, source="checklist", severity="YELLOW", rule_id="FEV-02")
    res = pg_client.post("/triage", json=payload, headers=world.headers("asha_a"))
    assert res.status_code == 201, res.text
    record = res.json()["triage_record"]
    assert record["source"] == "checklist"
    assert record["complaint_capture"]["confirmed_text_en"] == record["complaint_text"]


def test_english_capture_requires_no_translation(pg_client, world):
    capture = typed_hindi_capture(
        language="en",
        original_text="fever for 7 days",
        machine_translation_en=None,
        translation_engine=None,
        translation_status="not_required",
        confirmed_original_text="fever for 7 days",
        confirmed_text_en="fever for 7 days",
    )
    res = pg_client.post("/triage", json=triage_payload(world.encounter, capture), headers=world.headers("asha_a"))
    assert res.status_code == 201, res.text
    assert res.json()["triage_record"]["complaint_capture"]["english_edited"] is False


def test_replayed_offline_capture_never_creates_a_second_record(pg_client, pg_engine, world):
    capture = typed_hindi_capture()
    headers = {**world.headers("asha_a"), "Idempotency-Key": "op-123"}
    first = pg_client.post("/triage", json=triage_payload(world.encounter, capture), headers=headers)
    replay = pg_client.post("/triage", json=triage_payload(world.encounter, capture), headers=headers)
    assert first.status_code == replay.status_code == 201
    assert replay.json() == first.json()

    # Same capture id under a different/expired idempotency key: refused.
    other = pg_client.post(
        "/triage", json=triage_payload(world.encounter, capture), headers={**world.headers("asha_a"), "Idempotency-Key": "op-999"}
    )
    assert other.status_code == 409 and other.json()["detail"] == "complaint_capture_already_recorded"
    assert _counts(pg_engine) == (1, 1)


def test_checklist_path_queue_order_and_red_escalation_are_unchanged(pg_client, pg_engine, world):
    s = sessionmaker(bind=pg_engine)()
    second = new_encounter(s, world.patient, world.facility_a, 2)
    s.commit()
    s.close()

    green = pg_client.post(
        "/triage",
        json=triage_payload(world.encounter, None, severity="GREEN", rule_id="DEFAULT-01", extracted_facts={}),
        headers=world.headers("asha_a"),
    )
    assert green.status_code == 201 and green.json()["escalation_created"] is False
    assert green.json()["triage_record"]["complaint_capture"] is None

    red = pg_client.post(
        "/triage",
        json=triage_payload(second, None, severity="RED", rule_id="GDS-03", extracted_facts={"convulsions": True}),
        headers=world.headers("asha_a"),
    )
    assert red.status_code == 201
    assert red.json()["escalation_created"] is True
    assert red.json()["queue_position"] == 1  # RED jumps ahead of the earlier GREEN

    queue = pg_client.get(f"/queue/{world.facility_a}", headers=world.headers("doctor_a")).json()
    assert [t["severity"] for t in queue] == ["RED", "GREEN"]

    s = sessionmaker(bind=pg_engine)()
    assert s.scalar(select(func.count()).select_from(EscalationEvent)) == 1
    assert s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "triage_decision")) == 2
    s.close()


def test_triage_remains_facility_scoped(pg_client, world):
    capture = typed_hindi_capture()
    res = pg_client.post("/triage", json=triage_payload(world.encounter, capture), headers=world.headers("doctor_b"))
    assert res.status_code == 403
