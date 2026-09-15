"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const DETAIL_MESSAGES: Record<string, string> = {
  clinician_role_required: "Only a doctor can approve or reject a substitution.",
  facility_access_denied: "This request belongs to another facility.",
  substitution_request_not_pending: "This request was already decided. Refresh the page.",
  prescription_changed_since_request: "The prescription changed after this request was made, so it was invalidated. Nothing was prescribed.",
  substitute_no_longer_matches: "The products no longer match on current data, so the request was invalidated. Nothing was prescribed.",
};

export function SubstitutionDecision({ requestId, canDecide }: { requestId: string; canDecide: boolean }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (!canDecide) {
    return <p className="text-xs text-slate-500">Only a doctor at this facility can approve or reject.</p>;
  }

  async function decide(action: "approve" | "reject") {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`/api/substitution-requests/${encodeURIComponent(requestId)}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision_note: note || null }),
      });
      if (res.ok) {
        router.refresh();
        return;
      }
      const body = await res.json().catch(() => ({}));
      setMessage(DETAIL_MESSAGES[body.detail] ?? "That didn't save. Nothing was changed — please try again.");
      if (res.status === 409) router.refresh();
    } catch {
      setMessage("Couldn't reach the server — nothing was saved. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-2">
      <label className="block text-xs font-medium text-slate-600">
        Decision note (optional)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} rows={2} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" />
      </label>
      <div className="flex gap-2">
        <button
          onClick={() => void decide("approve")}
          disabled={busy}
          className="rounded-md bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50"
        >
          Approve and update prescription
        </button>
        <button
          onClick={() => void decide("reject")}
          disabled={busy}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
      {message && (
        <p className="text-xs text-severity-red" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
