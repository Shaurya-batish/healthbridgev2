"""Contract tests for typed-text translation and the upgraded /transcribe.

These use fakes for the model runtimes (Argos / Whisper) and are NOT evidence
that real translation or transcription works -- that is what
tests/test_real_models.py is for (opt-in, runs the real models on real audio).
The unavailable/validation paths below do run the real module code.
"""
import base64
import io
import os
import wave

import pytest
from fastapi.testclient import TestClient

from app import config, main, transcribe, translate

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _local_mode(monkeypatch):
    monkeypatch.setenv("AI_MODE", "local")
    monkeypatch.setattr(config, "AI_SHARED_SECRET", None)


def _wav_base64(seconds: float, rate: int = 16000) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return base64.b64encode(buf.getvalue()).decode()


class _FakeTranslation:
    def __init__(self, out: str):
        self.out = out
        self.seen: list[str] = []

    def translate(self, text):
        self.seen.append(text)
        return self.out


# --- /translate -------------------------------------------------------------


def test_translate_returns_labelled_machine_english(monkeypatch):
    fake = _FakeTranslation("the child has fever")
    monkeypatch.setattr(translate, "_installed_pairs", lambda: {"hi": fake})
    monkeypatch.setitem(__import__("sys").modules, "argostranslate", object())
    resp = client.post("/translate", json={"text": "बच्चे को बुखार है", "source_language": "hi"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["translation_en"] == "the child has fever"
    assert body["engine"] == "argostranslate"
    assert body["source_language"] == "hi"
    assert "severity" not in body
    assert fake.seen == ["बच्चे को बुखार है"]


def test_translate_reports_missing_language_package_honestly(monkeypatch):
    monkeypatch.setattr(translate, "_installed_pairs", lambda: {"hi": _FakeTranslation("x")})
    monkeypatch.setitem(__import__("sys").modules, "argostranslate", object())
    resp = client.post("/translate", json={"text": "ਬੱਚੇ ਨੂੰ ਬੁਖਾਰ ਹੈ", "source_language": "pa"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == {"code": "translation_unavailable", "reason": "language_not_installed"}


def test_translate_without_engine_installed_is_unavailable_not_500(monkeypatch):
    # Real import path: simulate argostranslate absent.
    monkeypatch.setitem(__import__("sys").modules, "argostranslate", None)
    resp = client.post("/translate", json={"text": "बुखार", "source_language": "hi"})
    assert resp.status_code == 503
    assert resp.json()["detail"]["reason"] == "engine_not_installed"


def test_translate_rejects_english_blank_and_oversized():
    assert client.post("/translate", json={"text": "fever", "source_language": "en"}).json()["detail"] == "translation_not_required"
    assert client.post("/translate", json={"text": "   ", "source_language": "hi"}).status_code == 422
    assert client.post("/translate", json={"text": "a" * 4001, "source_language": "hi"}).status_code == 422
    assert client.post("/translate", json={"text": "x", "source_language": "fr"}).status_code == 422


def test_translate_is_disabled_in_degraded_mode(monkeypatch):
    monkeypatch.setenv("AI_MODE", "degraded")
    monkeypatch.setattr(translate, "start_warmup", lambda: pytest.fail("degraded mode must not load the engine"))
    assert translate.available_languages() == []
    resp = client.post("/translate", json={"text": "बुखार", "source_language": "hi"})
    assert resp.status_code == 503
    assert resp.json()["detail"]["reason"] == "degraded_mode"


def test_health_lists_only_really_installed_translation_languages(monkeypatch):
    monkeypatch.setattr(main.ollama_client, "is_reachable", lambda *a, **k: False)
    monkeypatch.setattr(transcribe, "is_available", lambda: False)
    monkeypatch.setattr(translate, "engine_loaded", lambda: True)
    monkeypatch.setattr(translate, "_installed_pairs", lambda: {"hi": object(), "bn": object()})
    assert client.get("/health").json()["translation_languages"] == ["bn", "hi"]


def test_health_never_blocks_on_loading_the_translation_engine(monkeypatch):
    """A freshly started AI host must answer /health quickly; languages are
    reported only after the heavy Argos import has finished in the background."""
    started = []
    monkeypatch.setattr(main.ollama_client, "is_reachable", lambda *a, **k: False)
    monkeypatch.setattr(transcribe, "is_available", lambda: False)
    monkeypatch.setattr(translate, "engine_loaded", lambda: False)
    monkeypatch.setattr(translate, "start_warmup", lambda: started.append(True))
    monkeypatch.setattr(translate, "_installed_pairs", lambda: pytest.fail("must not scan packages before the engine loads"))
    assert client.get("/health").json()["translation_languages"] == []
    assert started == [True]


def test_minisbd_sentence_splitting_is_the_default():
    # Bengali's bundled stanza splitter crashes under stanza 1.10; see translate.py.
    assert os.environ.get("ARGOS_CHUNK_TYPE") == "MINISBD"


# --- /transcribe validation (real module code, no model needed) ---------------


def test_transcribe_rejects_unsupported_mime_before_decoding():
    resp = client.post("/transcribe", json={"audio_base64": _wav_base64(1), "language": "hi", "mime_type": "video/x-matroska"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "unsupported_audio_format"


def test_transcribe_rejects_too_short_audio_before_loading_whisper(monkeypatch):
    monkeypatch.setattr(transcribe, "_get_model", lambda: pytest.fail("must not load Whisper for invalid audio"))
    resp = client.post("/transcribe", json={"audio_base64": _wav_base64(0.2), "language": "hi", "mime_type": "audio/wav"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "audio_too_short"


def test_transcribe_rejects_too_long_audio_before_loading_whisper(monkeypatch):
    monkeypatch.setattr(transcribe, "MAX_DURATION_SECONDS", 2.0)
    monkeypatch.setattr(transcribe, "_get_model", lambda: pytest.fail("must not load Whisper for invalid audio"))
    resp = client.post("/transcribe", json={"audio_base64": _wav_base64(3), "language": "ta", "mime_type": "audio/wav"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "audio_too_long"


def test_transcribe_rejects_undecodable_bytes_as_client_error():
    garbage = base64.b64encode(b"definitely not an audio container" * 10).decode()
    resp = client.post("/transcribe", json={"audio_base64": garbage, "language": "hi", "mime_type": "audio/webm"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "invalid_audio"


def test_transcribe_runs_both_whisper_passes_on_one_decode_with_provenance(monkeypatch):
    calls = []

    class FakeModel:
        def transcribe(self, samples, language, task, **decoding):
            calls.append((language, task, decoding))
            text = "बच्चे को बुखार है" if task == "transcribe" else "the child has fever"
            return [type("S", (), {"text": text})()], None

    monkeypatch.setattr(transcribe, "_get_model", lambda: FakeModel())
    resp = client.post("/transcribe", json={"audio_base64": _wav_base64(1.5), "language": "hi", "mime_type": "audio/wav"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transcript"] == "बच्चे को बुखार है"
    assert body["translation_en"] == "the child has fever"
    assert body["engine"] == "faster-whisper"
    assert body["model"] == config.WHISPER_MODEL
    assert body["duration_seconds"] == 1.5
    assert [c[:2] for c in calls] == [("hi", "transcribe"), ("hi", "translate")]
    # Original-language pass: deterministic beam search with bounded fallback.
    assert calls[0][2] == {"temperature": (0.0, 0.2, 0.4), "beam_size": 5, "condition_on_previous_text": False}
    # English pass keeps Whisper defaults (the beam settings made Tamil loop).
    assert calls[1][2] == {}
    assert body["transcript_warnings"] == [] and body["translation_warnings"] == []
    assert "severity" not in body


def test_transcribe_flags_degenerate_output_from_whisper_signals(monkeypatch):
    """Real observation: a browser recording decoded to '।।।।…'. The service
    must flag it for the ASHA, not present it as ordinary text."""

    def seg(text, ratio, logprob):
        return type("S", (), {"text": text, "compression_ratio": ratio, "avg_logprob": logprob})()

    class FakeModel:
        def transcribe(self, samples, language, task, **decoding):
            if task == "transcribe":
                return [seg("।" * 60, 12.0, -0.3)], None
            return [seg("It is not a waste of time", 1.1, -1.4)], None

    monkeypatch.setattr(transcribe, "_get_model", lambda: FakeModel())
    resp = client.post("/transcribe", json={"audio_base64": _wav_base64(1.5), "language": "hi", "mime_type": "audio/wav"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transcript"] == "।" * 60  # shown as-is, never silently altered
    assert body["transcript_warnings"] == ["repetitive_output", "mostly_non_letters"]
    assert body["translation_warnings"] == ["low_confidence"]
