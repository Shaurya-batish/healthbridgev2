"""Pydantic schemas. The extracted-facts model is generated dynamically from
rules/imnci-rules.v1.json's fact_schema so the field list can never drift
from the rule table -- see CONTRACT.md ("read at runtime, not hand-transcribed").
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, create_model

# A caregiver's spoken/typed complaint has no legitimate reason to be huge;
# an unbounded string gets forwarded straight into an LLM prompt run on
# "modest PHC hardware" (CLAUDE.md) -- an extremely long input is both a
# resource-exhaustion and a slow-request risk. 4000 chars is generous for
# a free-text complaint. audio_base64 is capped similarly (~11MB of raw
# audio at base64's ~4/3 size overhead) -- enough for several minutes of
# voice, not an arbitrarily large upload.
_MAX_COMPLAINT_CHARS = 4000
_MAX_AUDIO_BASE64_CHARS = 15_000_000

from .rules_engine import load_rules

_SEVERITY_KEYS = {"severity", "urgency", "color", "priority", "danger_level"}


def _field_type(spec: dict[str, Any]):
    t = spec["type"]
    if t == "number":
        return Optional[float]
    if t == "boolean":
        return Optional[bool]
    if t == "string":
        if "enum" in spec:
            return Optional[Literal[tuple(spec["enum"])]]  # type: ignore[arg-type]
        return Optional[str]
    raise ValueError(f"Unsupported fact_schema type: {t!r}")


def build_extracted_facts_model() -> type[BaseModel]:
    table = load_rules()
    fields: dict[str, Any] = {}
    for name, spec in table["fact_schema"].items():
        fields[name] = (_field_type(spec), None)
    return create_model("ExtractedFacts", **fields)  # type: ignore[call-overload]


ExtractedFacts = build_extracted_facts_model()


def strip_severity_like_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Defense in depth: if the model ignores instructions and emits a
    severity/urgency/color field anyway, drop it before it ever reaches the
    rule evaluator or a client. Severity is decided in exactly one place:
    rules_engine.evaluate().
    """
    return {k: v for k, v in raw.items() if k.lower() not in _SEVERITY_KEYS}


def coerce_to_fact_schema(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate/coerce a raw dict (from the LLM) against the fact_schema,
    dropping unknown keys, severity-like keys, and any single field whose
    value fails schema validation (a hallucinated enum value, wrong type,
    etc.) -- one bad field must not fail the whole extraction. Returns a
    plain dict suitable for rules_engine.evaluate().
    """
    cleaned = strip_severity_like_keys(raw)
    accepted: dict[str, Any] = {}
    for key, value in cleaned.items():
        if key not in ExtractedFacts.model_fields:
            continue
        try:
            single = ExtractedFacts(**{key: value})
        except ValidationError:
            continue
        accepted[key] = getattr(single, key)
    return ExtractedFacts(**accepted).model_dump()


CaptureLanguage = Literal["en", "hi", "pa", "bn", "mr", "ta"]


class ExtractRequest(BaseModel):
    complaint_text: Optional[str] = Field(default=None, max_length=_MAX_COMPLAINT_CHARS)
    audio_base64: Optional[str] = Field(default=None, max_length=_MAX_AUDIO_BASE64_CHARS)
    age_months: Optional[float] = Field(default=None, ge=0, le=1200)
    # Spoken language of audio_base64. Whisper translates the audio to
    # English before extraction; ignored for complaint_text.
    language: CaptureLanguage = "en"


class TranscribeRequest(BaseModel):
    audio_base64: str = Field(min_length=1, max_length=_MAX_AUDIO_BASE64_CHARS)
    language: CaptureLanguage
    # The recorder's MIME type (e.g. "audio/webm;codecs=opus"). Optional for
    # backward compatibility; when present it must be an allowed audio format.
    mime_type: Optional[str] = Field(default=None, max_length=100)


class TranscribeResponse(BaseModel):
    # Original-language text: what the ASHA reviews, corrects and confirms.
    transcript: str
    # Whisper's own English translation of the same audio. After the ASHA
    # confirms (or corrects) it, it is the only text sent to Phi-4-mini.
    translation_en: str
    language: CaptureLanguage
    engine: str
    model: str
    duration_seconds: float
    # e.g. "repetitive_output", "low_confidence", "mostly_non_letters" --
    # shown to the ASHA as a reason to check the text; never auto-corrected.
    transcript_warnings: list[str] = Field(default_factory=list)
    translation_warnings: list[str] = Field(default_factory=list)


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=_MAX_COMPLAINT_CHARS)
    source_language: CaptureLanguage


class TranslateResponse(BaseModel):
    translation_en: str
    source_language: CaptureLanguage
    engine: str
    engine_version: Optional[str] = None


class ExtractResponse(BaseModel):
    transcript: Optional[str] = None
    translation_en: Optional[str] = None
    extracted_facts: dict[str, Any]
    severity: Literal["RED", "YELLOW", "GREEN"]
    rule_id: str
    rule_version: str


class HealthResponse(BaseModel):
    ai_mode: Literal["local", "degraded"]
    ollama_reachable: bool
    whisper_available: bool
    # Source languages with a real, installed <lang>->en typed-text
    # translation package on this host. Empty when none are installed.
    translation_languages: list[str] = Field(default_factory=list)
