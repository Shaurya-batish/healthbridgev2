"""Local Whisper transcription wrapper.

The dependency is imported lazily (inside functions, not at module load) so
this service can start and serve text-only complaints even when the Whisper
package/model isn't installed. Pulling the actual model weights is a
real-deployment step (see services/ai/README.md).

Multilingual capture (OVERNIGHT-BRIEF item 3, decided): the same audio is
decoded twice --

1. task="transcribe" in the declared language -> the ORIGINAL-language text,
   which the ASHA confirms and which is stored verbatim in the audit log;
2. task="translate" -> English text, which is the only thing Phi-4-mini
   ever sees.

The extraction prompt and IMNCI rule table therefore stay English-only and
do not need re-validating per language. Phi-4-mini is never asked to
translate.
"""
from __future__ import annotations

import base64
import binascii
import tempfile
from pathlib import Path

from . import config

# Languages the ASHA app offers for voice capture. Passed to Whisper
# explicitly -- autodetect on short, noisy clinical speech is materially
# less accurate than a declared language.
SUPPORTED_LANGUAGES = ("en", "hi", "pa", "bn", "mr", "ta")


class TranscriptionUnavailable(Exception):
    """Raised when Whisper isn't installed/loadable, or transcription fails.

    Endpoints must catch this and return 503, never a raw traceback, so the
    caller can fall back to the structured checklist path.
    """


class InvalidAudio(Exception):
    """The payload isn't decodable audio -- a client error, not an outage."""


def is_available() -> bool:
    if config.is_degraded():
        return False
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


_model_singleton = None


def _get_model():
    global _model_singleton
    if _model_singleton is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriptionUnavailable("faster-whisper is not installed") from exc
        try:
            _model_singleton = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        except Exception as exc:  # model download/load failure
            raise TranscriptionUnavailable(f"Whisper model could not be loaded: {exc}") from exc
    return _model_singleton


def _decode(audio_base64: str) -> bytes:
    try:
        audio_bytes = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidAudio(f"Invalid base64 audio payload: {exc}") from exc
    if not audio_bytes:
        raise InvalidAudio("Empty audio payload")
    return audio_bytes


def _run(model, path: Path, language: str, task: str) -> str:
    segments, _info = model.transcribe(str(path), language=language, task=task)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe_and_translate(audio_base64: str, language: str) -> tuple[str, str]:
    """Returns (original_language_transcript, english_text)."""
    if config.is_degraded():
        raise TranscriptionUnavailable("AI_MODE=degraded: transcription is disabled on this deployment")
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language {language!r}")

    audio_bytes = _decode(audio_base64)
    model = _get_model()

    # faster-whisper decodes via PyAV and sniffs the container itself, so the
    # suffix is cosmetic -- browsers' MediaRecorder sends webm/ogg, not wav.
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        original = _run(model, tmp_path, language, "transcribe")
        # For English the translate pass would only re-derive the same text.
        english = original if language == "en" else _run(model, tmp_path, language, "translate")
        return original, english
    except Exception as exc:
        # PyAV raises on undecodable bytes; anything else is a runtime failure.
        if exc.__class__.__module__.startswith("av"):
            raise InvalidAudio(f"Audio could not be decoded: {exc}") from exc
        raise TranscriptionUnavailable(f"Transcription failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
