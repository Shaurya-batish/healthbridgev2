import { requireFacilitySession } from "@/lib/server-session";
import { safeCoreRequest } from "@/lib/facility-data";
import { FacilityUnavailable } from "@/components/FacilityUnavailable";
import { RefreshButton } from "@/components/RefreshButton";
import { MedicineDetails } from "@/components/medicines/MedicineComparison";
import type { SubstitutionRequest } from "@/lib/types";
import { SubstitutionDecision } from "./SubstitutionDecision";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<SubstitutionRequest["status"], string> = {
  pending: "bg-amber-100 text-amber-900",
  approved: "bg-severity-green-bg text-severity-green",
  rejected: "bg-slate-100 text-slate-700",
  invalidated: "bg-severity-red-bg text-severity-red",
};

export default async function SubstitutionsPage() {
  const session = await requireFacilitySession();
  const result = await safeCoreRequest<SubstitutionRequest[]>(`/substitution-requests/facility/${session.facility_id}`);
  const isDoctor = session.role === "doctor";

  const pending = result.ok ? result.data.filter((r) => r.status === "pending") : [];
  const decided = result.ok ? result.data.filter((r) => r.status !== "pending").slice(0, 20) : [];

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold text-slate-800">Substitution review</h1>
          <RefreshButton />
        </div>
        <p className="mt-1 text-sm text-slate-500">
          Requests raised from the informational comparison. Nothing changes a prescription until a doctor approves; approval re-checks the
          prescription and the match first.
        </p>
        {!result.ok && (
          <div className="mt-3">
            <FacilityUnavailable reason={result.reason} />
          </div>
        )}
        {result.ok && pending.length === 0 && <p className="mt-3 text-sm text-slate-400">No pending requests.</p>}
        <ul className="mt-3 space-y-4">
          {pending.map((r) => (
            <li key={r.id} className="rounded-lg border border-slate-200 p-4">
              <p className="text-xs text-slate-500">
                Requested {new Date(r.created_at).toLocaleString()} · prescription version {r.order_version}
                {r.request_note ? ` · “${r.request_note}”` : ""}
              </p>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <div className="rounded-md bg-slate-50 p-3">
                  <p className="text-xs font-semibold uppercase text-slate-500">Currently prescribed</p>
                  <MedicineDetails medicine={r.original_medicine} />
                </div>
                <div className="rounded-md bg-teal-50 p-3">
                  <p className="text-xs font-semibold uppercase text-teal-800">Proposed</p>
                  <MedicineDetails medicine={r.proposed_medicine} />
                </div>
              </div>
              <SubstitutionDecision requestId={r.id} canDecide={isDoctor} />
            </li>
          ))}
        </ul>
      </div>

      {decided.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-700">Recent decisions</h2>
          <ul className="mt-2 divide-y divide-slate-100">
            {decided.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span>
                  {r.original_medicine.brand_name} → {r.proposed_medicine.brand_name}
                  {r.decision_note ? <span className="text-slate-500"> · {r.decision_note}</span> : null}
                </span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_TONE[r.status]}`}>
                  {r.status}
                  {r.reviewed_at ? ` · ${new Date(r.reviewed_at).toLocaleDateString()}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
