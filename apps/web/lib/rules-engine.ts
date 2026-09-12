// On-device implementation of the IMNCI rule table grammar defined in
// rules/imnci-rules.v1.json (`condition_grammar`). This is the offline
// fallback evaluator used by the ASHA app's structured checklist per
// CLAUDE.md's offline-degradation rule — it must stay behaviorally
// identical to the Python evaluator in services/ai. No Node-only APIs:
// this file runs in the browser (on-device severity calc) as well as in
// Next.js route handlers.
import ruleTable from "./imnci-rules.v1.json";
import type { ImnciFacts, Severity, TriageResult } from "./types";

type Op = "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "exists";

interface LeafCondition {
  field: string;
  op: Op;
  value?: unknown;
}

interface AllCondition {
  all: Condition[];
}

interface AnyCondition {
  any: Condition[];
}

interface AtLeastCondition {
  atLeast: { n: number; conditions: Condition[] };
}

type Condition = LeafCondition | AllCondition | AnyCondition | AtLeastCondition;

interface Rule {
  id: string;
  category: string;
  severity: Severity;
  description: string;
  when: Condition;
}

interface RuleTable {
  rule_table_id: string;
  version: string;
  severity_order: Severity[];
  default_severity: Severity;
  default_rule_id: string;
  default_description: string;
  rules: Rule[];
}

const table = ruleTable as unknown as RuleTable;

function getField(facts: ImnciFacts, field: string): unknown {
  const value = (facts as Record<string, unknown>)[field];
  return value === undefined ? null : value;
}

function evalLeaf(facts: ImnciFacts, leaf: LeafCondition): boolean {
  const actual = getField(facts, leaf.field);

  if (leaf.op === "exists") {
    return actual !== null;
  }

  if (actual === null) {
    // Missing field: booleans/equality never auto-fire, numeric comparisons
    // are always false. Fail-safe default per CONTRACT.md.
    return false;
  }

  switch (leaf.op) {
    case "eq":
      return actual === leaf.value;
    case "neq":
      return actual !== leaf.value;
    case "gt":
      return typeof actual === "number" && typeof leaf.value === "number" && actual > leaf.value;
    case "gte":
      return typeof actual === "number" && typeof leaf.value === "number" && actual >= leaf.value;
    case "lt":
      return typeof actual === "number" && typeof leaf.value === "number" && actual < leaf.value;
    case "lte":
      return typeof actual === "number" && typeof leaf.value === "number" && actual <= leaf.value;
    default:
      return false;
  }
}

function evalCondition(facts: ImnciFacts, condition: Condition): boolean {
  if ("all" in condition) {
    return condition.all.every((c) => evalCondition(facts, c));
  }
  if ("any" in condition) {
    return condition.any.some((c) => evalCondition(facts, c));
  }
  if ("atLeast" in condition) {
    const matched = condition.atLeast.conditions.filter((c) => evalCondition(facts, c)).length;
    return matched >= condition.atLeast.n;
  }
  return evalLeaf(facts, condition as LeafCondition);
}

function severityRank(severity: Severity): number {
  return table.severity_order.indexOf(severity);
}

/**
 * Evaluates every rule in the table against the given facts and returns the
 * highest-severity match (RED > YELLOW > GREEN). Falls back to the table's
 * default rule/severity when nothing matches. Deterministic and pure — same
 * facts always produce the same result, which is what makes each decision
 * auditable.
 */
export function evaluateTriage(facts: ImnciFacts): TriageResult {
  let best: { rule: Rule } | null = null;

  for (const rule of table.rules) {
    if (!evalCondition(facts, rule.when)) continue;
    if (!best || severityRank(rule.severity) > severityRank(best.rule.severity)) {
      best = { rule };
    }
  }

  if (!best) {
    return {
      severity: table.default_severity,
      rule_id: table.default_rule_id,
      rule_version: table.version,
      matched_description: table.default_description,
    };
  }

  return {
    severity: best.rule.severity,
    rule_id: best.rule.id,
    rule_version: table.version,
    matched_description: best.rule.description,
  };
}

export function getRuleTableVersion(): string {
  return table.version;
}

/** Looks up a rule's description by id (including the default rule) — used to render a consistent explanation regardless of whether severity came from the LLM path or the on-device checklist path. */
export function getRuleDescription(ruleId: string): string {
  if (ruleId === table.default_rule_id) return table.default_description;
  return table.rules.find((r) => r.id === ruleId)?.description ?? "";
}

export function getFactFieldNames(): string[] {
  return Object.keys((ruleTable as { fact_schema: Record<string, unknown> }).fact_schema);
}
