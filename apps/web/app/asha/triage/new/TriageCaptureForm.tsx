"use client";

import { useState } from "react";
import Link from "next/link";
import { useOffline } from "@/lib/OfflineSyncProvider";
import { evaluateTriage, getRuleDescription } from "@/lib/rules-engine";
import { SeverityBadge } from "@/components/SeverityBadge";
import type { ImnciFacts, TriageResult, TriageSource } from "@/lib/types";

type Stage = "capture" | "checklist" | "result" | "saving" | "done" | "error";

export function TriageCaptureForm({ abhaNumber, facilityId }: { abhaNumber: string; facilityId: string }) {
  const { submitEncounterAndTriage, isOnline } = useOffline();
  const [abha, setAbha] = useState(abhaNumber);
  const [complaint, setComplaint] = useState("");
  const [ageMonths, setAgeMonths] = useState<string>("");
  const [facts, setFacts] = useState<ImnciFacts>({});
  const [source, setSource] = useState<TriageSource>("llm");
  const [result, setResult] = useState<TriageResult | null>(null);
  const [stage, setStage] = useState<Stage>("capture");
  const [saveOutcome, setSaveOutcome] = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  async function analyze() {
    setStage("saving");
    const age = ageMonths ? Number(ageMonths) : undefined;

    if (!isOnline) {
      setStage("checklist");
      return;
    }

    try {
      const res = await fetch("/api/triage/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ complaint_text: complaint, age_months: age }),
      });
      const body = await res.json();

      if (body.ai_unavailable) {
        setStage("checklist");
        return;
      }

      setFacts(body.extracted_facts ?? {});
      setSource("llm");
      setResult({
        severity: body.severity,
        rule_id: body.rule_id,
        rule_version: body.rule_version,
        matched_description: getRuleDescription(body.rule_id),
      });
      setStage("result");
    } catch {
      setStage("checklist");
    }
  }

  function submitChecklist(collectedFacts: ImnciFacts) {
    const withAge: ImnciFacts = { ...collectedFacts, age_months: ageMonths ? Number(ageMonths) : null };
    setFacts(withAge);
    setSource("checklist");
    setResult(evaluateTriage(withAge));
    setStage("result");
  }

  async function confirmAndSave() {
    if (!result) return;
    setStage("saving");
    setErrorDetail(null);

    const outcome = await submitEncounterAndTriage(
      "/api/encounters",
      { abha_number: abha, facility_id: facilityId, chief_complaint: complaint || "(structured checklist)" },
      "/api/triage",
      {
        complaint_text: complaint || null,
        source,
        extracted_facts: facts,
        severity: result.severity,
        rule_id: result.rule_id,
        rule_version: result.rule_version,
      },
    );

    if (outcome.status === "rejected") {
      setErrorDetail(typeof outcome.detail === "object" ? JSON.stringify(outcome.detail) : String(outcome.detail));
      setStage("error");
      return;
    }

    setSaveOutcome(
      outcome.status === "sent"
        ? "Saved. Token created and queue updated."
        : "Saved on this device — will sync and create the token when back online.",
    );
    setStage("done");
  }

  if (stage === "done") {
    return (
      <div className="rounded-lg border border-severity-green bg-severity-green-bg p-5 text-sm text-severity-green">
        {saveOutcome}
        <div className="mt-3">
          <Link href="/asha" className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800">
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h1 className="text-lg font-semibold text-slate-800">New visit / triage</h1>

        <label className="mt-3 block text-sm font-medium text-slate-700">
          ABHA number
          <input
            value={abha}
            onChange={(e) => setAbha(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="mt-3 block text-sm font-medium text-slate-700">
          Age (months)
          <input
            type="number"
            min={0}
            value={ageMonths}
            onChange={(e) => setAgeMonths(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        {stage === "capture" && (
          <>
            <label className="mt-3 block text-sm font-medium text-slate-700">
              Complaint (what the caregiver says, in their words)
              <textarea
                value={complaint}
                onChange={(e) => setComplaint(e.target.value)}
                rows={4}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                placeholder="e.g. Child has had fever for 3 days and is not drinking water"
              />
            </label>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                onClick={analyze}
                disabled={!complaint.trim()}
                className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50"
              >
                {isOnline ? "Analyze complaint" : "Offline — use checklist"}
              </button>
              <button
                onClick={() => setStage("checklist")}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                Use structured checklist instead
              </button>
            </div>
          </>
        )}
      </div>

      {stage === "checklist" && <ChecklistForm onSubmit={submitChecklist} />}

      {stage === "result" && result && (
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-700">Triage result</h2>
            <SeverityBadge severity={result.severity} />
          </div>
          <p className="mt-2 text-sm text-slate-600">
            Matched rule <span className="font-mono font-semibold">{result.rule_id}</span> (v{result.rule_version}):{" "}
            {result.matched_description}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Source: {source === "llm" ? "LLM extraction + rule engine" : "Structured checklist + rule engine (offline)"}
          </p>
          <button
            onClick={confirmAndSave}
            className="mt-4 rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800"
          >
            Confirm & create token
          </button>
        </div>
      )}

      {stage === "error" && (
        <div className="rounded-lg border border-severity-red bg-severity-red-bg p-4 text-sm text-severity-red">
          Could not save: {errorDetail}
        </div>
      )}
    </div>
  );
}

function ChecklistForm({ onSubmit }: { onSubmit: (facts: ImnciFacts) => void }) {
  const [facts, setFacts] = useState<ImnciFacts>({});

  function toggle(field: keyof ImnciFacts) {
    setFacts((f) => ({ ...f, [field]: !f[field] }));
  }

  function setNumber(field: keyof ImnciFacts, value: string) {
    setFacts((f) => ({ ...f, [field]: value ? Number(value) : null }));
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-slate-700">
        Structured symptom checklist <span className="font-normal text-slate-400">(same rule table, runs on this device)</span>
      </h2>

      <ChecklistSection title="General danger signs">
        <Check label="Unable to drink or breastfeed" checked={!!facts.unable_to_drink_or_feed} onChange={() => toggle("unable_to_drink_or_feed")} />
        <Check label="Vomits everything" checked={!!facts.vomits_everything} onChange={() => toggle("vomits_everything")} />
        <Check label="Convulsions" checked={!!facts.convulsions} onChange={() => toggle("convulsions")} />
        <Check label="Lethargic or unconscious" checked={!!facts.lethargic_or_unconscious} onChange={() => toggle("lethargic_or_unconscious")} />
      </ChecklistSection>

      <ChecklistSection title="Cough / breathing">
        <Check label="Chest indrawing" checked={!!facts.chest_indrawing} onChange={() => toggle("chest_indrawing")} />
        <Check label="Stridor when calm" checked={!!facts.stridor_when_calm} onChange={() => toggle("stridor_when_calm")} />
        <Check label="Cough present" checked={!!facts.cough_present} onChange={() => toggle("cough_present")} />
        <NumberField
          label="Breaths per minute"
          value={facts.respiratory_rate_per_min ?? ""}
          onChange={(v) => setNumber("respiratory_rate_per_min", v)}
        />
      </ChecklistSection>

      <ChecklistSection title="Diarrhea">
        <Check label="Diarrhea present" checked={!!facts.diarrhea_present} onChange={() => toggle("diarrhea_present")} />
        <NumberField
          label="Duration (days)"
          value={facts.diarrhea_duration_days ?? ""}
          onChange={(v) => setNumber("diarrhea_duration_days", v)}
        />
        <Check label="Blood in stool" checked={!!facts.blood_in_stool} onChange={() => toggle("blood_in_stool")} />
        <Check label="Restless or irritable" checked={!!facts.restless_or_irritable} onChange={() => toggle("restless_or_irritable")} />
        <Check label="Sunken eyes" checked={!!facts.sunken_eyes} onChange={() => toggle("sunken_eyes")} />
        <Check label="Drinks eagerly / thirsty" checked={!!facts.drinks_eagerly_thirsty} onChange={() => toggle("drinks_eagerly_thirsty")} />
        <Check label="Skin pinch: goes back slowly" checked={!!facts.skin_pinch_slow} onChange={() => toggle("skin_pinch_slow")} />
        <Check label="Skin pinch: goes back very slowly" checked={!!facts.skin_pinch_very_slow} onChange={() => toggle("skin_pinch_very_slow")} />
      </ChecklistSection>

      <ChecklistSection title="Fever">
        <Check label="Fever present" checked={!!facts.fever_present} onChange={() => toggle("fever_present")} />
        <NumberField
          label="Duration (days)"
          value={facts.fever_duration_days ?? ""}
          onChange={(v) => setNumber("fever_duration_days", v)}
        />
        <Check label="Stiff neck" checked={!!facts.stiff_neck} onChange={() => toggle("stiff_neck")} />
      </ChecklistSection>

      <ChecklistSection title="Ear">
        <Check label="Ear pain" checked={!!facts.ear_pain} onChange={() => toggle("ear_pain")} />
        <Check label="Ear discharge" checked={!!facts.ear_discharge} onChange={() => toggle("ear_discharge")} />
        <Check label="Tender swelling behind ear" checked={!!facts.tender_swelling_behind_ear} onChange={() => toggle("tender_swelling_behind_ear")} />
      </ChecklistSection>

      <ChecklistSection title="Nutrition">
        <Check label="Visible severe wasting" checked={!!facts.visible_severe_wasting} onChange={() => toggle("visible_severe_wasting")} />
        <Check label="Edema of both feet" checked={!!facts.edema_both_feet} onChange={() => toggle("edema_both_feet")} />
        <label className="flex items-center justify-between py-1 text-sm text-slate-700">
          Palmar pallor
          <select
            value={facts.palmar_pallor ?? "none"}
            onChange={(e) => setFacts((f) => ({ ...f, palmar_pallor: e.target.value as ImnciFacts["palmar_pallor"] }))}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="none">None</option>
            <option value="some">Some</option>
            <option value="severe">Severe</option>
          </select>
        </label>
      </ChecklistSection>

      <button
        onClick={() => onSubmit(facts)}
        className="mt-4 w-full rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800"
      >
        Classify severity
      </button>
    </div>
  );
}

function ChecklistSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4 border-t border-slate-100 pt-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</h3>
      <div className="mt-2 space-y-1">{children}</div>
    </div>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex items-center justify-between py-1 text-sm text-slate-700">
      {label}
      <input type="checkbox" checked={checked} onChange={onChange} className="h-4 w-4" />
    </label>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number | string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center justify-between py-1 text-sm text-slate-700">
      {label}
      <input
        type="number"
        min={0}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm"
      />
    </label>
  );
}
