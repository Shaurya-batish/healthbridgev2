"""Real store-and-forward teleconsult tests -- an actual file is written to
disk and read back, not a status flag standing in for one. See
docs/REAL-INTEGRATION-AUDIT.md."""

import hashlib
import uuid

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _media_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TELECONSULT_MEDIA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _create_teleconsult(client, **overrides):
    payload = {
        "encounter_id": str(uuid.uuid4()),
        "patient_id": str(uuid.uuid4()),
        "facility_id": str(uuid.uuid4()),
        **overrides,
    }
    res = client.post("/teleconsults", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_defaults_to_pending(client):
    teleconsult = _create_teleconsult(client)
    assert teleconsult["status"] == "pending"


def test_media_upload_writes_a_real_file_and_computes_a_real_checksum(client, tmp_path):
    teleconsult = _create_teleconsult(client)
    audio_bytes = b"not-really-audio-but-real-bytes-for-the-test" * 100
    expected_checksum = hashlib.sha256(audio_bytes).hexdigest()

    res = client.post(
        f"/teleconsults/{teleconsult['id']}/media",
        files={"file": ("recording.webm", audio_bytes, "audio/webm")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "recorded"
    assert body["media_size_bytes"] == len(audio_bytes)
    assert body["media_checksum_sha256"] == expected_checksum

    # The file must genuinely exist on disk with the exact uploaded bytes --
    # this is what makes it "real" store-and-forward, not a fake screen.
    written_files = list(tmp_path.rglob("recording.*"))
    assert len(written_files) == 1
    assert written_files[0].read_bytes() == audio_bytes


def test_download_returns_the_real_uploaded_bytes(client):
    teleconsult = _create_teleconsult(client)
    audio_bytes = b"real playable content"
    client.post(
        f"/teleconsults/{teleconsult['id']}/media",
        files={"file": ("recording.ogg", audio_bytes, "audio/ogg")},
    )

    res = client.get(f"/teleconsults/{teleconsult['id']}/media")
    assert res.status_code == 200
    assert res.content == audio_bytes


def test_oversized_upload_is_rejected_not_read_fully_into_memory(client, monkeypatch):
    """Regression test: uploads used to be read fully into memory with no
    size check at all -- a real DoS vector. TELECONSULT_MAX_UPLOAD_BYTES is
    set tiny here so the test doesn't need to actually send 25MB."""
    monkeypatch.setenv("TELECONSULT_MAX_UPLOAD_BYTES", "100")
    get_settings.cache_clear()

    teleconsult = _create_teleconsult(client)
    oversized = b"x" * 1000
    res = client.post(
        f"/teleconsults/{teleconsult['id']}/media",
        files={"file": ("recording.webm", oversized, "audio/webm")},
    )
    assert res.status_code == 413
    assert res.json()["detail"] == "upload_too_large"


def test_unsupported_content_type_rejected(client):
    teleconsult = _create_teleconsult(client)
    res = client.post(
        f"/teleconsults/{teleconsult['id']}/media",
        files={"file": ("payload.exe", b"whatever", "application/x-msdownload")},
    )
    assert res.status_code == 400


def test_doctor_response_requires_a_recording_first(client):
    teleconsult = _create_teleconsult(client)
    res = client.post(f"/teleconsults/{teleconsult['id']}/response", json={"doctor_response_text": "advice"})
    assert res.status_code == 409


def test_full_lifecycle_pending_to_recorded_to_reviewed(client):
    teleconsult = _create_teleconsult(client)
    client.post(
        f"/teleconsults/{teleconsult['id']}/media",
        files={"file": ("recording.mp3", b"audio-bytes", "audio/mpeg")},
    )
    res = client.post(f"/teleconsults/{teleconsult['id']}/response", json={"doctor_response_text": "Give ORS, review in 2 days"})
    assert res.status_code == 200
    assert res.json()["status"] == "reviewed"
    assert res.json()["doctor_response_text"] == "Give ORS, review in 2 days"
