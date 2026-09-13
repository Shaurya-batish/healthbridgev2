import { requireFacilitySession } from "@/lib/server-session";
import { safeCoreRequest } from "@/lib/facility-data";
import { FacilityUnavailable } from "@/components/FacilityUnavailable";
import { RefreshButton } from "@/components/RefreshButton";
import type { DiagnosticOrder } from "@/lib/types";
import { DiagnosticResultForm } from "./DiagnosticResultForm";

export const dynamic = "force-dynamic";

export default async function DiagnosticsPage() {
  const session = await requireFacilitySession();
  const result = await safeCoreRequest<DiagnosticOrder[]>(`/diagnostics/facility/${session.facility_id}`);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">Diagnostics</h1>
        <RefreshButton />
      </div>
      {!result.ok && <div className="mt-3"><FacilityUnavailable reason={result.reason} /></div>}
      {result.ok && result.data.length === 0 && <p className="mt-3 text-sm text-slate-400">No diagnostic orders yet.</p>}
      {result.ok && (
        <ul className="mt-3 divide-y divide-slate-100">
          {result.data.map((order) => (
            <li key={order.id} className="flex items-center justify-between gap-3 py-3">
              <div>
                <p className="text-sm font-semibold text-slate-800">{order.test_name}</p>
                <p className="text-xs text-slate-400">
                  {order.status}
                  {order.result_text && ` · Result: ${order.result_text}`}
                </p>
              </div>
              {order.status !== "completed" && order.status !== "cancelled" && <DiagnosticResultForm orderId={order.id} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
