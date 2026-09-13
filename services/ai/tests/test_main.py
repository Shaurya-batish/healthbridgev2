from fastapi.testclient import TestClient

from app import main, ollama_client, transcribe

client = TestClient(main.app)


def test_health_endpoint_shape(monkeypatch):
    monkeypatch.setattr(ollama_client, "is_reachable", lambda *a, **k: False)
    monkeypatch.setattr(transcribe, "is_available", lambda: False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ollama_reachable": False, "whisper_available": False}


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


def test_extract_with_audio_transcribes_first(monkeypatch):
    monkeypatch.setattr(transcribe, "transcribe_base64_audio", lambda b64: "child has diarrhea with blood")
    monkeypatch.setattr(main, "run_extraction", lambda **kwargs: {"blood_in_stool": True})
    resp = client.post("/triage/extract", json={"audio_base64": "ZmFrZQ=="})
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "child has diarrhea with blood"
    assert body["severity"] == "YELLOW"
    assert body["rule_id"] == "DIAR-03"


def test_extract_with_audio_returns_503_when_transcription_unavailable(monkeypatch):
    def raise_unavailable(b64):
        raise transcribe.TranscriptionUnavailable("faster-whisper not installed")

    monkeypatch.setattr(transcribe, "transcribe_base64_audio", raise_unavailable)
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
