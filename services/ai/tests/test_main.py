import pytest
from fastapi.testclient import TestClient

from app import config, main, ollama_client, transcribe, translate

client = TestClient(main.app)


def _result(transcript: str, english: str) -> transcribe.TranscriptionResult:
    return transcribe.TranscriptionResult(transcript, english, 2.0, "small")


@pytest.fixture(autouse=True)
def _local_mode(monkeypatch):
    monkeypatch.setenv("AI_MODE", "local")
    monkeypatch.setattr(config, "AI_SHARED_SECRET", None)


def test_health_endpoint_shape(monkeypatch):
    monkeypatch.setattr(ollama_client, "is_reachable", lambda *a, **k: False)
    monkeypatch.setattr(transcribe, "is_available", lambda: False)
    monkeypatch.setattr(translate, "engine_loaded", lambda: True)
    monkeypatch.setattr(translate, "_installed_pairs", lambda: {})
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ai_mode": "local", "ollama_reachable": False, "whisper_available": False, "translation_languages": []}


def test_extract_requires_input():
    resp = client.post("/triage/extract", json={})
    assert resp.status_code == 400


def test_extract_happy_path(monkeypatch):
    monkeypatch.setattr(main, "run_extraction", lambda **kwargs: {"convulsions": True})
    resp = client.post("/triage/extract", json={"complaint_text": "child is convulsing"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["severity"] == "RED"
    assert body["rule_id"] == "GDS-03"
    assert body["extracted_facts"]["convulsions"] is True
    assert body["transcript"] is None


def test_extract_rejects_unsupported_language():
    resp = client.post("/triage/extract", json={"audio_base64": "ZmFrZQ==", "language": "fr"})
    assert resp.status_code == 422


def test_extract_rejects_out_of_range_age():
    resp = client.post("/triage/extract", json={"complaint_text": "fever", "age_months": -1})
    assert resp.status_code == 422
    resp = client.post("/triage/extract", json={"complaint_text": "fever", "age_months": 10**9})
    assert resp.status_code == 422


def test_extract_rejects_whitespace_only_complaint(monkeypatch):
    monkeypatch.setattr(main, "run_extraction", lambda **kwargs: pytest.fail("must not reach the LLM"))
    resp = client.post("/triage/extract", json={"complaint_text": "   "})
    assert resp.status_code == 400


def test_extract_returns_503_when_ollama_unavailable(monkeypatch):
    def raise_unavailable(**kwargs):
        raise ollama_client.OllamaUnavailable("connection refused")

    monkeypatch.setattr(main, "run_extraction", raise_unavailable)
    resp = client.post("/triage/extract", json={"complaint_text": "fever for two days"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "ai_unavailable"


def test_extract_returns_503_on_non_json_model_output(monkeypatch):
    def raise_value_error(**kwargs):
        raise ValueError("model returned garbage")

    monkeypatch.setattr(main, "run_extraction", raise_value_error)
    resp = client.post("/triage/extract", json={"complaint_text": "fever for two days"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "ai_unavailable"


def test_extract_with_audio_sends_only_the_english_translation_to_the_llm(monkeypatch):
    monkeypatch.setattr(
        transcribe,
        "transcribe_and_translate",
        lambda b64, language, mime_type=None: _result("बच्चे के मल में खून है", "the child has blood in the stool"),
    )
    seen = {}

    def fake_extraction(**kwargs):
        seen.update(kwargs)
        return {"blood_in_stool": True}

    monkeypatch.setattr(main, "run_extraction", fake_extraction)
    resp = client.post("/triage/extract", json={"audio_base64": "ZmFrZQ==", "language": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert seen["complaint_text"] == "the child has blood in the stool"
    assert body["transcript"] == "बच्चे के मल में खून है"
    assert body["translation_en"] == "the child has blood in the stool"
    assert body["severity"] == "YELLOW"
    assert body["rule_id"] == "DIAR-03"


def test_extract_with_audio_returns_503_when_transcription_unavailable(monkeypatch):
    def raise_unavailable(b64, language, mime_type=None):
        raise transcribe.TranscriptionUnavailable("faster-whisper not installed")

    monkeypatch.setattr(transcribe, "transcribe_and_translate", raise_unavailable)
    resp = client.post("/triage/extract", json={"audio_base64": "ZmFrZQ=="})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "ai_unavailable"


def test_extract_rejects_extremely_long_complaint_text():
    """Regression test: an unbounded complaint_text used to be forwarded
    straight into an LLM prompt with no size limit at all -- a real
    resource-exhaustion risk on "modest PHC hardware" (CLAUDE.md)."""
    resp = client.post("/triage/extract", json={"complaint_text": "a" * 5000})
    assert resp.status_code == 422


def test_extract_rejects_oversized_audio_base64():
    resp = client.post("/triage/extract", json={"audio_base64": "a" * 20_000_000})
    assert resp.status_code == 422


def test_extract_accepts_complaint_text_at_the_limit(monkeypatch):
    monkeypatch.setattr(main, "run_extraction", lambda **kwargs: {})
    resp = client.post("/triage/extract", json={"complaint_text": "a" * 4000})
    assert resp.status_code == 200


# --- /transcribe (speech -> editable text, never a severity) ---


def test_transcribe_returns_original_and_english_and_no_decision(monkeypatch):
    seen = {}

    def fake(b64, language, mime_type=None):
        seen["language"] = language
        return _result("बच्चे को तेज़ बुखार है", "the child has a high fever")

    monkeypatch.setattr(transcribe, "transcribe_and_translate", fake)
    resp = client.post("/transcribe", json={"audio_base64": "ZmFrZQ==", "language": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "transcript": "बच्चे को तेज़ बुखार है",
        "translation_en": "the child has a high fever",
        "language": "hi",
        "engine": "faster-whisper",
        "model": "small",
        "duration_seconds": 2.0,
        "transcript_warnings": [],
        "translation_warnings": [],
    }
    assert seen["language"] == "hi"
    assert "severity" not in body and "rule_id" not in body


def test_transcribe_requires_language():
    resp = client.post("/transcribe", json={"audio_base64": "ZmFrZQ=="})
    assert resp.status_code == 422


def test_transcribe_rejects_blank_audio():
    resp = client.post("/transcribe", json={"audio_base64": "", "language": "en"})
    assert resp.status_code == 422


def test_transcribe_returns_503_when_whisper_unavailable(monkeypatch):
    def raise_unavailable(b64, language, mime_type=None):
        raise transcribe.TranscriptionUnavailable("faster-whisper not installed")

    monkeypatch.setattr(transcribe, "transcribe_and_translate", raise_unavailable)
    resp = client.post("/transcribe", json={"audio_base64": "ZmFrZQ==", "language": "ta"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "transcription_unavailable"


def test_transcribe_rejects_empty_transcript(monkeypatch):
    monkeypatch.setattr(transcribe, "transcribe_and_translate", lambda b64, language, mime_type=None: _result("", ""))
    resp = client.post("/transcribe", json={"audio_base64": "ZmFrZQ==", "language": "en"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "empty_transcript"


def test_transcribe_rejects_non_base64_as_client_error():
    # Real function, not a stub: bad base64 is refused before Whisper loads.
    resp = client.post("/transcribe", json={"audio_base64": "!!!not base64!!!", "language": "hi"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "invalid_audio"


# --- AI_MODE=degraded (hosted build) ---


def test_degraded_health_reports_false_without_probing(monkeypatch):
    monkeypatch.setenv("AI_MODE", "degraded")
    monkeypatch.setattr(ollama_client, "is_reachable", lambda *a, **k: pytest.fail("must not probe Ollama"))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ai_mode": "degraded", "ollama_reachable": False, "whisper_available": False, "translation_languages": []}


def test_degraded_transcription_is_really_disabled(monkeypatch):
    """Not a stubbed flag: the real transcribe function refuses before
    touching the model, even though faster-whisper may be installed."""
    monkeypatch.setenv("AI_MODE", "degraded")
    assert transcribe.is_available() is False
    with pytest.raises(transcribe.TranscriptionUnavailable):
        transcribe.transcribe_and_translate("ZmFrZQ==", language="hi")
    resp = client.post("/transcribe", json={"audio_base64": "ZmFrZQ==", "language": "hi"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "transcription_unavailable"


def test_degraded_extract_returns_503_immediately(monkeypatch):
    monkeypatch.setenv("AI_MODE", "degraded")
    monkeypatch.setattr(main, "run_extraction", lambda **kwargs: pytest.fail("must not call the LLM"))
    resp = client.post("/triage/extract", json={"complaint_text": "fever for two days"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "ai_unavailable"


def test_invalid_ai_mode_fails_loudly(monkeypatch):
    monkeypatch.setenv("AI_MODE", "cloud")
    with pytest.raises(RuntimeError):
        client.get("/health")


# --- AI_SHARED_SECRET (service exposed through a public tunnel) ---


def test_shared_secret_blocks_requests_without_the_key(monkeypatch):
    monkeypatch.setattr(config, "AI_SHARED_SECRET", "s3cret")
    monkeypatch.setattr(main, "run_extraction", lambda **kwargs: pytest.fail("must not reach the LLM"))
    assert client.post("/triage/extract", json={"complaint_text": "fever"}).status_code == 401
    assert client.post("/transcribe", json={"audio_base64": "ZmFrZQ==", "language": "hi"}, headers={"X-AI-Key": "wrong"}).status_code == 401


def test_shared_secret_allows_the_right_key_and_leaves_health_open(monkeypatch):
    monkeypatch.setattr(config, "AI_SHARED_SECRET", "s3cret")
    monkeypatch.setattr(main, "run_extraction", lambda **kwargs: {})
    monkeypatch.setattr(ollama_client, "is_reachable", lambda *a, **k: False)
    assert client.post("/triage/extract", json={"complaint_text": "fever"}, headers={"X-AI-Key": "s3cret"}).status_code == 200
    assert client.get("/health").status_code == 200
