"""Deterministic IMNCI rule evaluator.

Loads the versioned rule table from rules/imnci-rules.v1.json (single source
of truth, shared with the TypeScript on-device evaluator in apps/web) and
decides severity from a facts object. This module is the ONLY place severity
is decided in this service -- the LLM extraction pipeline must never be
allowed to set severity itself. See CONTRACT.md.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import config

SEVERITY_RANK = {"GREEN": 0, "YELLOW": 1, "RED": 2}


class RulesFileNotFound(FileNotFoundError):
    pass


def _candidate_paths() -> list[Path]:
    here = Path(__file__).resolve()
    candidates = []
    if config.RULES_PATH:
        candidates.append(Path(config.RULES_PATH))
    # services/ai/app/rules_engine.py -> parents: app, ai, services, repo_root
    candidates.append(here.parents[3] / "rules" / "imnci-rules.v1.json")
    # Docker image layout: rules/ copied alongside the service (services/ai/rules)
    candidates.append(here.parents[1] / "rules" / "imnci-rules.v1.json")
    candidates.append(Path.cwd() / "rules" / "imnci-rules.v1.json")
    return candidates


def resolve_rules_path() -> Path:
    for candidate in _candidate_paths():
        if candidate.is_file():
            return candidate
    raise RulesFileNotFound(
        "Could not locate imnci-rules.v1.json. Tried: "
        + ", ".join(str(c) for c in _candidate_paths())
        + ". Set RULES_PATH to override."
    )


@lru_cache(maxsize=1)
def load_rules() -> dict[str, Any]:
    path = resolve_rules_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clear_cache() -> None:
    load_rules.cache_clear()


def _get_field(facts: dict[str, Any], field: str) -> Any:
    return facts.get(field, None)


def _eval_leaf(cond: dict[str, Any], facts: dict[str, Any]) -> bool:
    field = cond["field"]
    op = cond["op"]
    value = _get_field(facts, field)

    if op == "exists":
        return value is not None

    # Per rules/imnci-rules.v1.json condition_grammar.missing_field_semantics:
    # a missing/null fact never satisfies a leaf condition, regardless of op.
    if value is None:
        return False

    target = cond.get("value")
    if op == "eq":
        return value == target
    if op == "neq":
        return value != target
    if op in ("gt", "gte", "lt", "lte"):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if not isinstance(target, (int, float)) or isinstance(target, bool):
            return False
        if op == "gt":
            return value > target
        if op == "gte":
            return value >= target
        if op == "lt":
            return value < target
        if op == "lte":
            return value <= target
    raise ValueError(f"Unknown condition op: {op!r}")


def eval_condition(cond: dict[str, Any], facts: dict[str, Any]) -> bool:
    if "all" in cond:
        return all(eval_condition(c, facts) for c in cond["all"])
    if "any" in cond:
        return any(eval_condition(c, facts) for c in cond["any"])
    if "atLeast" in cond:
        spec = cond["atLeast"]
        n = spec["n"]
        count = sum(1 for c in spec["conditions"] if eval_condition(c, facts))
        return count >= n
    if "field" in cond:
        return _eval_leaf(cond, facts)
    raise ValueError(f"Malformed condition, no recognized key: {cond!r}")


def evaluate(facts: dict[str, Any], rules_table: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return {severity, rule_id, rule_version, matched_rules} for a facts object.

    severity = highest-ranked severity among every rule whose `when` matches;
    falls back to the table's default_rule_id/default_severity if none match.
    """
    table = rules_table if rules_table is not None else load_rules()

    matched = [rule for rule in table["rules"] if eval_condition(rule["when"], facts)]

    if not matched:
        return {
            "severity": table["default_severity"],
            "rule_id": table["default_rule_id"],
            "rule_version": table["version"],
            "matched_rules": [],
        }

    best = max(matched, key=lambda r: SEVERITY_RANK[r["severity"]])
    return {
        "severity": best["severity"],
        "rule_id": best["id"],
        "rule_version": table["version"],
        "matched_rules": [r["id"] for r in matched],
    }
