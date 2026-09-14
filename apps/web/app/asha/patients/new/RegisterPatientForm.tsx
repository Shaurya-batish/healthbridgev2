"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useOffline } from "@/lib/OfflineSyncProvider";
import { AshaButton } from "@/components/asha/AshaButton";
import { IconArrowLeft, IconArrowRight, IconCheckCircle } from "@/components/asha/icons";
import { friendlyErrorMessage } from "@/lib/friendly-error";
import type { SchemeStatus } from "@/lib/types";

const TOTAL_STEPS = 3;

export function RegisterPatientForm({ initialAbha = "" }: { initialAbha?: string }) {
  const router = useRouter();
  const { submitCreatePatient } = useOffline();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    abha_number: initialAbha,
    name: "",
    dob: "",
    gender: "female",
    scheme_status: "none" as SchemeStatus,
  });
  const [status, setStatus] = useState<"idle" | "saving" | "error" | "queued">("idle");
  const [error, setError] = useState<string | null>(null);
  const [stepError, setStepError] = useState<string | null>(null);

  function next() {
    if (step === 1) {
      if (!form.abha_number.trim() || !form.name.trim()) {
        setStepError("Please fill in both the ABHA number and the patient's name.");
        return;
      }
    }
    if (step === 2 && !form.dob) {
      setStepError("Please enter the date of birth.");
      return;
    }
    setStepError(null);
    setStep((s) => Math.min(TOTAL_STEPS, s + 1));
  }

  function back() {
    setStepError(null);
    setStep((s) => Math.max(1, s - 1));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("saving");
    setError(null);

    const result = await submitCreatePatient("/api/patients", form);

    if (result.status === "rejected") {
      setStatus("error");
      setError(friendlyErrorMessage(result.detail));
      return;
    }

    // Only navigate when the patient actually reached the server. The detail
    // page is server-rendered, so with no connectivity it is either missing
    // from the service-worker cache (the ASHA lands on the browser's own
    // error page and cannot tell whether her work was saved) or it reports
    // "no patient found" for the record she just entered. When the write is
    // queued locally, confirm it in place instead -- the same shape the
    // triage flow already uses for a queued save.
    if (result.status === "queued") {
      setStatus("queued");
      return;
    }

    router.push(`/asha/patients/${encodeURIComponent(form.abha_number)}`);
  }

  if (status === "queued") {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 rounded-2xl border border-severity-green bg-severity-green-bg p-5 text-severity-green">
          <IconCheckCircle className="mt-0.5 h-7 w-7 shrink-0" />
          <div>
            <p className="text-xl font-bold">Saved on this phone</p>
            <p className="mt-1 text-base font-medium">
              {form.name} is saved here and will sync automatically when you have signal. You do not need to enter this patient again.
            </p>
          </div>
        </div>
        {/* Home is the one route the service worker reliably has cached, so it
            is the only navigation offered here. /asha/triage/new?abha=... is
            server-rendered per ABHA and would be a cache miss with no signal --
            exactly the dead end this panel exists to avoid. */}
        <AshaButton href="/asha" icon={<IconArrowRight />}>
          Back to Home
        </AshaButton>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <StepHeader step={step} />

      <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
        {step === 1 && (
          <>
            <Field label="ABHA Number">
              <input
                autoFocus
                inputMode="numeric"
                value={form.abha_number}
                onChange={(e) => setForm({ ...form, abha_number: e.target.value })}
                className="input"
                placeholder="e.g. 12-3456-7890-1234"
              />
            </Field>
            <Field label="Patient Name">
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="input"
                placeholder="Full name"
              />
            </Field>
          </>
        )}

        {step === 2 && (
          <>
            <Field label="Date of Birth">
              <input
                type="date"
                value={form.dob}
                onChange={(e) => setForm({ ...form, dob: e.target.value })}
                className="input"
              />
            </Field>
            <Field label="Gender">
              <select value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })} className="input">
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
              </select>
            </Field>
          </>
        )}

        {step === 3 && (
          <>
            <Field label="Government Scheme (if any)">
              <select
                value={form.scheme_status}
                onChange={(e) => setForm({ ...form, scheme_status: e.target.value as SchemeStatus })}
                className="input"
              >
                <option value="none">None on record</option>
                <option value="PMJAY">PM-JAY</option>
                <option value="state">State scheme</option>
              </select>
            </Field>
            <ReviewSummary form={form} />
          </>
        )}

        {stepError && <p className="text-base text-red-700">{stepError}</p>}
        {error && <p className="text-base text-red-700">{error}</p>}

        <div className="flex gap-3 pt-2">
          {step > 1 && (
            <AshaButton type="button" variant="secondary" onClick={back} icon={<IconArrowLeft />}>
              Back
            </AshaButton>
          )}
          {step < TOTAL_STEPS && (
            <AshaButton type="button" onClick={next} icon={<IconArrowRight />}>
              Next
            </AshaButton>
          )}
          {step === TOTAL_STEPS && (
            <AshaButton type="submit" disabled={status === "saving"} icon={<IconCheckCircle />}>
              {status === "saving" ? "Saving..." : "Save Patient"}
            </AshaButton>
          )}
        </div>
      </form>

      <style jsx>{`
        .input {
          width: 100%;
          border-radius: 0.75rem;
          border: 2px solid #cbd5e1;
          padding: 1rem;
          font-size: 1.125rem;
        }
      `}</style>
    </div>
  );
}

function StepHeader({ step }: { step: number }) {
  const labels = ["Patient identity", "Birth & gender", "Scheme & review"];
  return (
    <div>
      <p className="text-sm font-semibold uppercase tracking-wide text-teal-700">
        Step {step} of {TOTAL_STEPS} · {labels[step - 1]}
      </p>
      <div className="mt-2 flex gap-2">
        {Array.from({ length: TOTAL_STEPS }, (_, i) => (
          <div key={i} className={`h-2 flex-1 rounded-full ${i < step ? "bg-teal-600" : "bg-slate-200"}`} />
        ))}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-base font-semibold text-slate-700">{label}</span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

function ReviewSummary({ form }: { form: { abha_number: string; name: string; dob: string; gender: string } }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4 text-base text-slate-600">
      <p className="font-semibold text-slate-700">{form.name || "—"}</p>
      <p>ABHA: {form.abha_number || "—"}</p>
      <p>DOB: {form.dob || "—"} · {form.gender}</p>
    </div>
  );
}
