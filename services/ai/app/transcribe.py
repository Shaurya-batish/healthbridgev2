"""Local Whisper transcription wrapper.

The dependency is imported lazily (inside functions, not at module load) so
this service can start and serve text-only complaints even when the Whisper
package/model isn't installed. Pulling the actual model weights is a
real-deployment step (see services/ai/README.md).

Multilingual capture (OVERNIGHT-BRIEF item 3, decided): the same audio is
decoded ONCE and run through Whisper twice --

1. task="transcribe" in the declared language -> the ORIGINAL-language text,
   which the ASHA reviews, may correct, and confirms;
2. task="translate" -> English text, which (after the ASHA confirms or
   corrects it) is the only thing Phi-4-mini ever sees.

The extraction prompt and IMNCI rule table therefore stay English-only and
do not need re-validating per language. Phi-4-mini is never asked to
translate. Language is always declared by the ASHA; nothing here claims
automatic language detection.
"""
from __future__ import annotations

import base64
import binascii
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import config

ENGINE = "faster-whisper"

# Languages the ASHA app offers for voice capture. Passed to Whisper
# explicitly -- autodetect on short, noisy clinical speech is materially
# less accurate than a declared language.
SUPPORTED_LANGUAGES = ("en", "hi", "pa", "bn", "mr", "ta")

# Formats a browser MediaRecorder (or a test fixture) actually produces.
# PyAV sniffs the container itself; this allowlist exists so the service
# refuses arbitrary uploads rather than trying to decode anything.
SUPPORTED_MIME_TYPES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav")

MIN_DURATION_SECONDS = 0.5
MAX_DURATION_SECONDS = 120.0
_SAMPLE_RATE = 16000

# Per-pass decoding, chosen from measurements on 2026-09-15 (docs/MULTILINGUAL-VOICE-MEDICINES.md):
# - transcribe: Whisper's default temperature fallback climbed to 0.8 on real
#   browser (Opus) recordings and produced mixed-script garbage in the
#   ORIGINAL-language text, varying run to run. Beam search with a bounded
#   fallback gave clean, repeatable Hindi and no regression on FLEURS clips.
# - translate: the same settings made Tamil translation loop ("birds of the
#   forest, birds of the forest, ..."), so the English pass keeps defaults.
# Neither pass is reliable enough to skip the ASHA's review and correction.
TRANSCRIBE_DECODING = {"temperature": (0.0, 0.2, 0.4), "beam_size": 5, "condition_on_previous_text": False}
TRANSLATE_DECODING: dict = {}


class TranscriptionUnavailable(Exception):
    """Raised when Whisper isn't installed/loadable, or transcription fails.

    Endpoints must catch this and return 503, never a raw traceback, so the
    caller can fall back to typed input or the structured checklist.
    """


class InvalidAudio(Exception):
    """The payload isn't usable audio -- a client error, not an outage."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    translation_en: str
    duration_seconds: float
    model: str
    # Whisper's own quality signals, surfaced to the ASHA -- never used to
    # silently alter or drop text. See _quality_warnings.
    transcript_warnings: tuple[str, ...] = ()
    translation_warnings: tuple[str, ...] = ()


# Thresholds mirror faster-whisper's own fallback triggers.
_MAX_COMPRESSION_RATIO = 2.4
_MIN_AVG_LOGPROB = -1.0


def _quality_warnings(segments: list, text: str) -> tuple[str, ...]:
    """Flags output a human must treat with suspicion. Measured cause: real
    browser recordings sometimes decoded to repeated punctuation or
    mixed-script text (2026-09-15)."""
    warnings: list[str] = []
    ratios = [getattr(s, "compression_ratio", None) for s in segments]
    logprobs = [getattr(s, "avg_logprob", None) for s in segments]
    if any(r is not None and r > _MAX_COMPRESSION_RATIO for r in ratios):
        warnings.append("repetitive_output")
    known = [lp for lp in logprobs if lp is not None]
    if known and sum(known) / len(known) < _MIN_AVG_LOGPROB:
        warnings.append("low_confidence")
    compact = text.replace(" ", "")
    if compact and sum(c.isalpha() for c in compact) / len(compact) < 0.5:
        warnings.append("mostly_non_letters")
    return tuple(warnings)


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


def _decode_base64(audio_base64: str) -> bytes:
    try:
        audio_bytes = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidAudio("invalid_audio", f"Invalid base64 audio payload: {exc}") from exc
    if not audio_bytes:
        raise InvalidAudio("invalid_audio", "Empty audio payload")
    return audio_bytes


def _decode_samples(path: Path):
    try:
        from faster_whisper.audio import decode_audio
    except ImportError as exc:
        raise TranscriptionUnavailable("faster-whisper is not installed") from exc
    try:
        return decode_audio(str(path), sampling_rate=_SAMPLE_RATE)
    except Exception as exc:
        # PyAV raises on undecodable or truncated containers.
        raise InvalidAudio("invalid_audio", f"Audio could not be decoded: {exc}") from exc


def _run(model, samples, language: str, task: str) -> tuple[str, tuple[str, ...]]:
    decoding = TRANSCRIBE_DECODING if task == "transcribe" else TRANSLATE_DECODING
    segments, _info = model.transcribe(samples, language=language, task=task, **decoding)
    segments = list(segments)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    return text, _quality_warnings(segments, text)


def transcribe_and_translate(audio_base64: str, language: str, mime_type: str | None = None) -> TranscriptionResult:
    if config.is_degraded():
        raise TranscriptionUnavailable("AI_MODE=degraded: transcription is disabled on this deployment")
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language {language!r}")
    if mime_type is not None and mime_type.split(";")[0].strip().lower() not in SUPPORTED_MIME_TYPES:
        raise InvalidAudio("unsupported_audio_format", f"Unsupported audio format {mime_type!r}")

    audio_bytes = _decode_base64(audio_base64)

    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        samples = _decode_samples(tmp_path)
        duration = len(samples) / _SAMPLE_RATE
        if duration < MIN_DURATION_SECONDS:
            raise InvalidAudio("audio_too_short", f"Recording is {duration:.2f}s")
        if duration > MAX_DURATION_SECONDS:
            raise InvalidAudio("audio_too_long", f"Recording is {duration:.1f}s")

        model = _get_model()
        try:
            original, original_warnings = _run(model, samples, language, "transcribe")
            # For English the translate pass would only re-derive the same text.
            if language == "en":
                english, english_warnings = original, original_warnings
            else:
                english, english_warnings = _run(model, samples, language, "translate")
        except Exception as exc:
            raise TranscriptionUnavailable(f"Transcription failed: {exc}") from exc
        return TranscriptionResult(
            original, english, round(duration, 2), config.WHISPER_MODEL, original_warnings, english_warnings
        )
    finally:
        tmp_path.unlink(missing_ok=True)
