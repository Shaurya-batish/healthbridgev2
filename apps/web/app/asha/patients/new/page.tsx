"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useOffline } from "@/lib/OfflineSyncProvider";
import type { SchemeStatus } from "@/lib/types";

export default function RegisterPatientPage() {
  const router = useRouter();
  const { submitCreatePatient } = useOffline();
  const [form, setForm] = useState({
    abha_number: "",
    name: "",
    dob: "",
    gender: "female",
    scheme_status: "none" as SchemeStatus,
  });
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("saving");
    setError(null);

    const result = await submitCreatePatient("/api/patients", form);

    if (result.status === "rejected") {
      setStatus("error");
      setError(typeof result.detail === "object" ? JSON.stringify(result.detail) : String(result.detail));
      return;
    }

    router.push(`/asha/patients/${encodeURIComponent(form.abha_number)}`);
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h1 className="text-lg font-semibold text-slate-800">Register patient</h1>
      <p className="mt-1 text-sm text-slate-500">Works offline — this will sync automatically once you're back online.</p>

      <form onSubmit={onSubmit} className="mt-4 space-y-4">
        <Field label="ABHA number">
          <input
            required
            value={form.abha_number}
            onChange={(e) => setForm({ ...form, abha_number: e.target.value })}
            className="input"
          />
        </Field>
        <Field label="Full name">
          <input
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="input"
          />
        </Field>
        <Field label="Date of birth">
          <input
            type="date"
            required
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
        <Field label="Government scheme">
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

        {error && <p className="text-sm text-severity-red">{error}</p>}

        <button
          type="submit"
          disabled={status === "saving"}
          className="w-full rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
        >
          {status === "saving" ? "Saving..." : "Save patient"}
        </button>
      </form>

      <style jsx>{`
        .input {
          width: 100%;
          border-radius: 0.375rem;
          border: 1px solid #cbd5e1;
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
        }
      `}</style>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
