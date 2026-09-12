import { authHeader, coreRequest } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { requireFacilitySession } from "@/lib/server-session";
import { RefreshButton } from "@/components/RefreshButton";
import { AcknowledgeButton } from "./AcknowledgeButton";
import type { EscalationEvent } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function EscalationsPage() {
  const session = await requireFacilitySession();
  const escalations = (await coreRequest(`/escalations/${session.facility_id}`, {
    headers: authHeader(getSessionToken()),
  })) as EscalationEvent[];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-severity-red">Open escalations</h1>
        <RefreshButton />
      </div>
      {escalations.length === 0 && <p className="mt-3 text-sm text-slate-400">No open escalations.</p>}
      <ul className="mt-3 divide-y divide-slate-100">
        {escalations.map((event) => (
          <li key={event.id} className="flex items-center justify-between py-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">Escalation {event.id.slice(0, 8)}</p>
              <p className="text-xs text-slate-400">{new Date(event.created_at).toLocaleString()} · {event.status}</p>
            </div>
            {event.status === "open" && <AcknowledgeButton id={event.id} />}
          </li>
        ))}
      </ul>
    </div>
  );
}
