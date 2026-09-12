"""Pydantic schemas. The extracted-facts model is generated dynamically from
rules/imnci-rules.v1.json's fact_schema so the field list can never drift
from the rule table -- see CONTRACT.md ("read at runtime, not hand-transcribed").
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ValidationError, create_model

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


class ExtractRequest(BaseModel):
    complaint_text: Optional[str] = None
    audio_base64: Optional[str] = None
    age_months: Optional[float] = None


class ExtractResponse(BaseModel):
    transcript: Optional[str] = None
    extracted_facts: dict[str, Any]
    severity: Literal["RED", "YELLOW", "GREEN"]
    rule_id: str
    rule_version: str


class HealthResponse(BaseModel):
    ollama_reachable: bool
    whisper_available: bool
