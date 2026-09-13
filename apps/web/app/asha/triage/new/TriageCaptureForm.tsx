"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useOffline } from "@/lib/OfflineSyncProvider";
import { evaluateTriage, getRuleDescription } from "@/lib/rules-engine";
import { friendlyErrorMessage } from "@/lib/friendly-error";
import { AshaButton } from "@/components/asha/AshaButton";
import { IconAlertTriangle, IconCheckCircle, IconArrowRight, IconClipboardPulse } from "@/components/asha/icons";
import type { ImnciFacts, Severity, TriageResult, TriageSource } from "@/lib/types";

type Stage = "capture" | "analyzing" | "checklist" | "result" | "submitting" | "done" | "error";

const SEVERITY_UI: Record<
  Severity,
  { header: string; subtext: string; action: string; tone: string; Icon: typeof IconAlertTriangle }
> = {
  RED: {
    header: "URGENT",
    subtext: "Doctor needs to see this patient right away.",
    action: "Move patient to priority queue.",
    tone: "border-severity-red bg-severity-red-bg text-severity-red",
    Icon: IconAlertTriangle,
  },
  YELLOW: {
    header: "NEEDS ATTENTION",
    subtext: "This patient should be seen soon.",
    action: "Patient added to the queue for review.",
    tone: "border-severity-yellow bg-severity-yellow-bg text-severity-yellow",
    Icon: IconAlertTriangle,
  },
  GREEN: {
    header: "NO DANGER SIGN DETECTED",
    subtext: "No urgent signs found right now.",
    action: "Patient added to the queue as routine.",
    tone: "border-severity-green bg-severity-green-bg text-severity-green",
    Icon: IconCheckCircle,
  },
};

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
    setStage("analyzing");
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
    setStage("submitting");
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
      setErrorDetail(friendlyErrorMessage(outcome.detail));
      setStage("error");
      return;
    }

    setSaveOutcome(
      outcome.status === "sent"
        ? "Saved. The patient has a token and is in the queue."
        : "Saved on this phone. It will sync and get a token when you're back online.",
    );
    setStage("done");
  }

  if (stage === "done") {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 rounded-2xl border border-severity-green bg-severity-green-bg p-5 text-severity-green">
          <IconCheckCircle className="mt-0.5 h-7 w-7 shrink-0" />
          <p className="text-lg font-semibold">{saveOutcome}</p>
        </div>
        <AshaButton href="/asha/queue" icon={<IconArrowRight />}>
          View Today&apos;s Queue
        </AshaButton>
        <AshaButton href="/asha" variant="secondary">
          Back to Home
        </AshaButton>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {(stage === "capture" || stage === "analyzing") && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <h1 className="text-2xl font-bold text-slate-800">New Visit</h1>

          <label className="mt-4 block">
            <span className="text-base font-semibold text-slate-700">ABHA Number</span>
            <input
              value={abha}
              onChange={(e) => setAbha(e.target.value)}
              className="mt-1.5 w-full rounded-xl border-2 border-slate-300 px-4 py-3 text-lg"
            />
          </label>

          <label className="mt-4 block">
            <span className="text-base font-semibold text-slate-700">Child&apos;s Age (months)</span>
            <input
              type="number"
              min={0}
              value={ageMonths}
              onChange={(e) => setAgeMonths(e.target.value)}
              className="mt-1.5 w-full rounded-xl border-2 border-slate-300 px-4 py-3 text-lg"
            />
          </label>

          {stage === "capture" && (
            <>
              <label className="mt-4 block">
                <span className="text-base font-semibold text-slate-700">Main Problem</span>
                <textarea
                  value={complaint}
                  onChange={(e) => setComplaint(e.target.value)}
                  rows={4}
                  className="mt-1.5 w-full rounded-xl border-2 border-slate-300 px-4 py-3 text-lg"
                  placeholder="What is wrong, in the caregiver's own words. e.g. Fever for 3 days, not drinking water"
                />
              </label>
              <div className="mt-4 space-y-3">
                <AshaButton onClick={analyze} disabled={!complaint.trim()} icon={<IconClipboardPulse />}>
                  {isOnline ? "Check Danger Signs" : "Offline — Use Checklist"}
                </AshaButton>
                <AshaButton onClick={() => setStage("checklist")} variant="secondary">
                  Use Symptom Checklist Instead
                </AshaButton>
              </div>
            </>
          )}

          {stage === "analyzing" && (
            <div className="mt-5 flex items-center gap-3 rounded-xl bg-slate-50 p-4 text-slate-600">
              <Spinner />
              <p className="text-lg font-medium">Checking for danger signs...</p>
            </div>
          )}
        </div>
      )}

      {stage === "checklist" && <ChecklistForm onSubmit={submitChecklist} />}

      {stage === "result" && result && <ResultCard result={result} source={source} onConfirm={confirmAndSave} />}

      {stage === "submitting" && (
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-5 text-slate-600">
          <Spinner />
          <p className="text-lg font-medium">Saving patient visit...</p>
        </div>
      )}

      {stage === "error" && (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-amber-900">
            <IconAlertTriangle className="mt-0.5 h-6 w-6 shrink-0" />
            <p className="text-lg">{errorDetail}</p>
          </div>
          <AshaButton onClick={() => setStage("result")} variant="secondary">
            Try Again
          </AshaButton>
        </div>
      )}
    </div>
  );
}

function ResultCard({ result, source, onConfirm }: { result: TriageResult; source: TriageSource; onConfirm: () => void }) {
  const ui = SEVERITY_UI[result.severity];
  return (
    <div className={`space-y-4 rounded-2xl border-2 p-5 ${ui.tone}`}>
      <div className="flex items-center gap-3">
        <ui.Icon className="h-9 w-9 shrink-0" />
        <div>
          <h2 className="text-2xl font-extrabold tracking-wide">{ui.header}</h2>
          <p className="text-base font-medium">{ui.subtext}</p>
        </div>
      </div>

      <div className="rounded-xl bg-white/60 p-4 text-slate-800">
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Reason</p>
        <p className="mt-1 text-lg">{result.matched_description}</p>
      </div>

      <div className="rounded-xl bg-white/60 p-4 text-slate-800">
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Action</p>
        <p className="mt-1 text-lg">{ui.action}</p>
      </div>

      <p className="text-sm opacity-75">
        {source === "llm" ? "Checked using the patient's description." : "Checked using the symptom checklist (works offline)."}
      </p>

      <AshaButton onClick={onConfirm} variant="primary" icon={<IconArrowRight />}>
        Confirm & Add to Queue
      </AshaButton>
    </div>
  );
}

function Spinner() {
  return <span className="h-6 w-6 shrink-0 animate-spin rounded-full border-4 border-slate-300 border-t-teal-700" aria-hidden="true" />;
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
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-xl font-bold text-slate-800">Check Danger Signs</h2>
      <p className="mt-1 text-slate-500">
        Tick anything that is true for this patient. Same rules as the automatic check — works without internet.
        6 short sections below, then the result.
      </p>

      <ChecklistSection index={1} total={6} title="General danger signs">
        <Check label="Unable to drink or breastfeed" checked={!!facts.unable_to_drink_or_feed} onChange={() => toggle("unable_to_drink_or_feed")} />
        <Check label="Vomits everything" checked={!!facts.vomits_everything} onChange={() => toggle("vomits_everything")} />
        <Check label="Convulsions (fits)" checked={!!facts.convulsions} onChange={() => toggle("convulsions")} />
        <Check label="Very sleepy or unconscious" checked={!!facts.lethargic_or_unconscious} onChange={() => toggle("lethargic_or_unconscious")} />
      </ChecklistSection>

      <ChecklistSection index={2} total={6} title="Breathing Problem">
        <Check label="Chest pulls in when breathing" checked={!!facts.chest_indrawing} onChange={() => toggle("chest_indrawing")} />
        <Check label="Noisy breathing (stridor) even when calm" checked={!!facts.stridor_when_calm} onChange={() => toggle("stridor_when_calm")} />
        <Check label="Cough present" checked={!!facts.cough_present} onChange={() => toggle("cough_present")} />
        <NumberField label="Breaths per minute" value={facts.respiratory_rate_per_min ?? ""} onChange={(v) => setNumber("respiratory_rate_per_min", v)} />
      </ChecklistSection>

      <ChecklistSection index={3} total={6} title="Loose Motions (Diarrhea)">
        <Check label="Loose motions present" checked={!!facts.diarrhea_present} onChange={() => toggle("diarrhea_present")} />
        <NumberField label="How many days" value={facts.diarrhea_duration_days ?? ""} onChange={(v) => setNumber("diarrhea_duration_days", v)} />
        <Check label="Blood in stool" checked={!!facts.blood_in_stool} onChange={() => toggle("blood_in_stool")} />
        <Check label="Restless or irritable" checked={!!facts.restless_or_irritable} onChange={() => toggle("restless_or_irritable")} />
        <Check label="Sunken eyes" checked={!!facts.sunken_eyes} onChange={() => toggle("sunken_eyes")} />
        <Check label="Drinks water eagerly, very thirsty" checked={!!facts.drinks_eagerly_thirsty} onChange={() => toggle("drinks_eagerly_thirsty")} />
        <Check label="Skin pinch: goes back slowly" checked={!!facts.skin_pinch_slow} onChange={() => toggle("skin_pinch_slow")} />
        <Check label="Skin pinch: goes back very slowly" checked={!!facts.skin_pinch_very_slow} onChange={() => toggle("skin_pinch_very_slow")} />
      </ChecklistSection>

      <ChecklistSection index={4} total={6} title="Temperature">
        <Check label="Fever present" checked={!!facts.fever_present} onChange={() => toggle("fever_present")} />
        <NumberField label="How many days" value={facts.fever_duration_days ?? ""} onChange={(v) => setNumber("fever_duration_days", v)} />
        <Check label="Stiff neck" checked={!!facts.stiff_neck} onChange={() => toggle("stiff_neck")} />
      </ChecklistSection>

      <ChecklistSection index={5} total={6} title="Ear">
        <Check label="Ear pain" checked={!!facts.ear_pain} onChange={() => toggle("ear_pain")} />
        <Check label="Ear discharge (pus/fluid)" checked={!!facts.ear_discharge} onChange={() => toggle("ear_discharge")} />
        <Check label="Painful swelling behind the ear" checked={!!facts.tender_swelling_behind_ear} onChange={() => toggle("tender_swelling_behind_ear")} />
      </ChecklistSection>

      <ChecklistSection index={6} total={6} title="Nutrition">
        <Check label="Visible severe thinness" checked={!!facts.visible_severe_wasting} onChange={() => toggle("visible_severe_wasting")} />
        <Check label="Swelling in both feet" checked={!!facts.edema_both_feet} onChange={() => toggle("edema_both_feet")} />
        <label className="flex items-center justify-between gap-3 py-2 text-lg text-slate-700">
          Paleness of palms
          <select
            value={facts.palmar_pallor ?? "none"}
            onChange={(e) => setFacts((f) => ({ ...f, palmar_pallor: e.target.value as ImnciFacts["palmar_pallor"] }))}
            className="rounded-lg border-2 border-slate-300 px-3 py-2 text-base"
          >
            <option value="none">None</option>
            <option value="some">Some</option>
            <option value="severe">Severe</option>
          </select>
        </label>
      </ChecklistSection>

      <div className="mt-5">
        <AshaButton onClick={() => onSubmit(facts)} icon={<IconArrowRight />}>
          See Result
        </AshaButton>
      </div>
    </div>
  );
}

function ChecklistSection({
  title,
  index,
  total,
  children,
}: {
  title: string;
  index: number;
  total: number;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-5 border-t border-slate-100 pt-4">
      <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
        Section {index} of {total} · {title}
      </h3>
      <div className="mt-1 divide-y divide-slate-50">{children}</div>
    </div>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex items-center justify-between gap-3 py-3 text-lg text-slate-700">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={onChange} className="h-7 w-7 shrink-0 accent-teal-700" />
    </label>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number | string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center justify-between gap-3 py-3 text-lg text-slate-700">
      <span>{label}</span>
      <input
        type="number"
        min={0}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-24 rounded-lg border-2 border-slate-300 px-2 py-2 text-lg"
      />
    </label>
  );
}
