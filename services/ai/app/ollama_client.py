"""Thin HTTP client for a local Ollama instance serving Phi-4-mini.

Kept separate from graph.py so the LangGraph node stays testable with a
mocked transport (see tests/test_graph.py) without needing a live Ollama.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from . import config


class OllamaUnavailable(Exception):
    """Raised when Ollama cannot be reached or times out."""


def is_reachable(timeout: float = config.OLLAMA_HEALTH_TIMEOUT_SECONDS) -> bool:
    try:
        resp = httpx.get(f"{config.OLLAMA_HOST}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def generate_json(prompt: str, system: str | None = None, client: httpx.Client | None = None) -> dict[str, Any]:
    """Call Ollama's /api/generate with format=json and return the parsed JSON body.

    Raises OllamaUnavailable on any network/timeout error, or ValueError if
    the model's output is not valid JSON.
    """
    payload: dict[str, Any] = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
    }
    if system:
        payload["system"] = system

    owns_client = client is None
    http_client = client or httpx.Client(timeout=config.OLLAMA_TIMEOUT_SECONDS)
    try:
        resp = http_client.post(f"{config.OLLAMA_HOST}/api/generate", json=payload)
        resp.raise_for_status()
        body = resp.json()
    except httpx.HTTPError as exc:
        raise OllamaUnavailable(str(exc)) from exc
    finally:
        if owns_client:
            http_client.close()

    raw_text = body.get("response", "")
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama returned non-JSON output: {raw_text!r}") from exc
