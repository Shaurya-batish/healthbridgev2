"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { MedicineSearch } from "@/components/medicines/MedicineSearch";
import { MedicineDetails } from "@/components/medicines/MedicineComparison";
import type { MedicineSummary } from "@/lib/types";

const DETAIL_MESSAGES: Record<string, string> = {
  clinician_role_required: "Only a doctor can prescribe.",
  facility_access_denied: "This encounter belongs to another facility.",
  medicine_discontinued: "That product is marked discontinued in the source data.",
  encounter_not_found: "The visit no longer exists. Refresh the page.",
};

/** Doctor-only prescribing against the patient's latest encounter. Core
 * enforces the role; this form is hidden for other roles as a convenience. */
export function PrescribeForm({ encounterId }: { encounterId: string }) {
  const router = useRouter();
  const [medicine, setMedicine] = useState<MedicineSummary | null>(null);
  const [instructions, setInstructions] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!medicine || !instructions.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/medication-orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ encounter_id: encounterId, medicine_id: medicine.id, instructions }),
      });
      if (res.ok) {
        setMessage({ ok: true, text: "Prescription saved." });
        setMedicine(null);
        setInstructions("");
        router.refresh();
      } else {
        const body = await res.json().catch(() => ({}));
        setMessage({ ok: false, text: DETAIL_MESSAGES[body.detail] ?? "Could not save the prescription. Nothing was changed." });
      }
    } catch {
      setMessage({ ok: false, text: "Couldn't reach the server — nothing was saved." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-slate-700">Prescribe (doctor)</h3>
      {!medicine ? (
        <div className="mt-2">
          <MedicineSearch onSelect={setMedicine} compact />
        </div>
      ) : (
        <form onSubmit={submit} className="mt-2 space-y-2">
          <MedicineDetails medicine={medicine} />
          <button type="button" onClick={() => setMedicine(null)} className="text-xs font-semibold text-teal-800">
            Choose a different product
          </button>
          <label className="block text-xs font-medium text-slate-600">
            Instructions (dose, frequency, duration)
            <textarea
              required
              maxLength={1000}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <button type="submit" disabled={busy || !instructions.trim()} className="rounded-md bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50">
            {busy ? "Saving..." : "Save prescription"}
          </button>
        </form>
      )}
      {message && <p className={`mt-2 text-xs ${message.ok ? "text-severity-green" : "text-severity-red"}`}>{message.text}</p>}
    </div>
  );
}
