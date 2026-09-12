"""LangGraph pipeline: complaint text -> Phi-4-mini (facts only) -> sanitize.

Severity is never decided here. This module's only job is to produce a
fact_schema-shaped dict; app.rules_engine.evaluate() is the sole place
severity is assigned (see CONTRACT.md).
"""
from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, StateGraph

from . import ollama_client
from .rules_engine import load_rules
from .schemas import coerce_to_fact_schema


class ExtractionState(TypedDict, total=False):
    complaint_text: str
    age_months: float | None
    raw_facts: dict[str, Any]
    extracted_facts: dict[str, Any]


def build_system_prompt() -> str:
    table = load_rules()
    lines = [
        "You are a clinical fact-extraction assistant for a rural health triage tool.",
        "Read the caregiver's free-text complaint and extract ONLY the facts listed below.",
        "Output STRICT JSON with exactly these keys. Omit a key or set it null if it is not mentioned.",
        "Do NOT infer, diagnose, guess, or output a severity, urgency, priority, color, or danger level.",
        "You are a fact extractor only. A separate, deterministic rule engine decides severity -- never you.",
        "",
        "Fields:",
    ]
    for name, spec in table["fact_schema"].items():
        type_desc = spec["type"]
        if spec.get("enum"):
            type_desc = f"one of {spec['enum']}"
        lines.append(f"- {name}: {type_desc}")
    return "\n".join(lines)


def _extract_node_factory(ollama_call: Callable[..., dict[str, Any]]):
    def _extract(state: ExtractionState) -> ExtractionState:
        system = build_system_prompt()
        user_prompt = f"Complaint: {state['complaint_text']}"
        if state.get("age_months") is not None:
            user_prompt += f"\nPatient age (months): {state['age_months']}"
        raw = ollama_call(prompt=user_prompt, system=system)
        return {**state, "raw_facts": raw}

    return _extract


def _sanitize_node(state: ExtractionState) -> ExtractionState:
    cleaned = coerce_to_fact_schema(state.get("raw_facts") or {})
    if state.get("age_months") is not None and cleaned.get("age_months") is None:
        cleaned["age_months"] = state["age_months"]
    return {**state, "extracted_facts": cleaned}


def build_graph(ollama_call: Callable[..., dict[str, Any]] = ollama_client.generate_json):
    graph = StateGraph(ExtractionState)
    graph.add_node("extract", _extract_node_factory(ollama_call))
    graph.add_node("sanitize", _sanitize_node)
    graph.set_entry_point("extract")
    graph.add_edge("extract", "sanitize")
    graph.add_edge("sanitize", END)
    return graph.compile()


def run_extraction(
    complaint_text: str,
    age_months: float | None = None,
    ollama_call: Callable[..., dict[str, Any]] = ollama_client.generate_json,
) -> dict[str, Any]:
    compiled = build_graph(ollama_call)
    result = compiled.invoke({"complaint_text": complaint_text, "age_months": age_months})
    return result["extracted_facts"]
