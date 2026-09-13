import { authHeader, coreRequest } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { requireFacilitySession } from "@/lib/server-session";
import { RefreshButton } from "@/components/RefreshButton";
import type { DiagnosticOrder } from "@/lib/types";
import { DiagnosticResultForm } from "./DiagnosticResultForm";

export const dynamic = "force-dynamic";

export default async function DiagnosticsPage() {
  const session = await requireFacilitySession();
  const orders = (await coreRequest(`/diagnostics/facility/${session.facility_id}`, {
    headers: authHeader(getSessionToken()),
  })) as DiagnosticOrder[];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">Diagnostics</h1>
        <RefreshButton />
      </div>
      {orders.length === 0 && <p className="mt-3 text-sm text-slate-400">No diagnostic orders yet.</p>}
      <ul className="mt-3 divide-y divide-slate-100">
        {orders.map((order) => (
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
    </div>
  );
}
