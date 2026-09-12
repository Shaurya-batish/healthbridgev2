import { describe, expect, it } from "vitest";
import { evaluateTriage } from "./rules-engine";
import type { ImnciFacts } from "./types";

describe("evaluateTriage", () => {
  it("returns the default GREEN classification when no facts match", () => {
    const result = evaluateTriage({});
    expect(result.severity).toBe("GREEN");
    expect(result.rule_id).toBe("DEFAULT-01");
  });

  const redCases: Array<[string, ImnciFacts]> = [
    ["GDS-01", { unable_to_drink_or_feed: true }],
    ["GDS-02", { vomits_everything: true }],
    ["GDS-03", { convulsions: true }],
    ["GDS-04", { lethargic_or_unconscious: true }],
    ["RESP-01", { chest_indrawing: true }],
    ["RESP-02", { stridor_when_calm: true }],
    ["DIAR-01", { sunken_eyes: true, skin_pinch_very_slow: true }],
    ["FEV-01", { fever_present: true, stiff_neck: true }],
    ["EAR-01", { tender_swelling_behind_ear: true }],
    ["NUT-01", { visible_severe_wasting: true }],
    ["NUT-02", { edema_both_feet: true }],
    ["NUT-03", { palmar_pallor: "severe" }],
  ];

  it.each(redCases)("fires %s as RED", (ruleId, facts) => {
    const result = evaluateTriage(facts);
    expect(result.severity).toBe("RED");
    expect(result.rule_id).toBe(ruleId);
  });

  it("fires RESP-03 (fast breathing) using WHO age-banded thresholds", () => {
    expect(evaluateTriage({ age_months: 1, respiratory_rate_per_min: 61 }).rule_id).toBe("RESP-03");
    expect(evaluateTriage({ age_months: 1, respiratory_rate_per_min: 59 }).severity).toBe("GREEN");
    expect(evaluateTriage({ age_months: 6, respiratory_rate_per_min: 50 }).rule_id).toBe("RESP-03");
    expect(evaluateTriage({ age_months: 6, respiratory_rate_per_min: 49 }).severity).toBe("GREEN");
    expect(evaluateTriage({ age_months: 24, respiratory_rate_per_min: 40 }).rule_id).toBe("RESP-03");
    expect(evaluateTriage({ age_months: 24, respiratory_rate_per_min: 39 }).severity).toBe("GREEN");
  });

  it("fires DIAR-02 (some dehydration) only with at least 2 of 4 signs", () => {
    expect(evaluateTriage({ restless_or_irritable: true, sunken_eyes: true }).rule_id).toBe("DIAR-02");
    expect(evaluateTriage({ restless_or_irritable: true }).severity).toBe("GREEN");
  });

  const yellowCases: Array<[string, ImnciFacts]> = [
    ["DIAR-03", { blood_in_stool: true }],
    ["DIAR-04", { diarrhea_duration_days: 14 }],
    ["FEV-02", { fever_present: true, fever_duration_days: 7 }],
    ["FEV-03", { fever_present: true }],
    ["EAR-02", { ear_pain: true }],
    ["NUT-04", { palmar_pallor: "some" }],
  ];

  it.each(yellowCases)("fires %s as YELLOW", (ruleId, facts) => {
    const result = evaluateTriage(facts);
    expect(result.severity).toBe("YELLOW");
    expect(result.rule_id).toBe(ruleId);
  });

  it("takes the highest severity when multiple rules match", () => {
    // Plain fever alone is FEV-03 (YELLOW), but with stiff neck FEV-01 (RED) must win.
    const result = evaluateTriage({ fever_present: true, stiff_neck: true, ear_pain: true });
    expect(result.severity).toBe("RED");
    expect(result.rule_id).toBe("FEV-01");
  });

  it("treats a missing field as null: never auto-fires and never crashes on comparisons", () => {
    expect(() => evaluateTriage({ diarrhea_duration_days: undefined })).not.toThrow();
    expect(evaluateTriage({}).rule_id).toBe("DEFAULT-01");
  });
});
