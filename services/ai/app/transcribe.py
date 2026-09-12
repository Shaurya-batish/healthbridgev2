"""Local Whisper transcription wrapper.

The dependency is imported lazily (inside functions, not at module load) so
this service can start and serve text-only complaints even when the Whisper
package/model isn't installed -- e.g. in this dev sandbox. Pulling the actual
model weights is a real-deployment step (see services/ai/README.md), not
something this build session performs.
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path


class TranscriptionUnavailable(Exception):
    """Raised when Whisper isn't installed/loadable, or transcription fails.

    The /triage/extract endpoint must catch this and return 503, never a raw
    traceback, so the caller can fall back to the structured checklist path.
    """


def is_available() -> bool:
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
            _model_singleton = WhisperModel("small", device="cpu", compute_type="int8")
        except Exception as exc:  # model download/load failure
            raise TranscriptionUnavailable(f"Whisper model could not be loaded: {exc}") from exc
    return _model_singleton


def transcribe_base64_audio(audio_base64: str) -> str:
    try:
        audio_bytes = base64.b64decode(audio_base64)
    except Exception as exc:
        raise TranscriptionUnavailable(f"Invalid base64 audio payload: {exc}") from exc

    model = _get_model()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        segments, _info = model.transcribe(str(tmp_path))
        return " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as exc:
        raise TranscriptionUnavailable(f"Transcription failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
