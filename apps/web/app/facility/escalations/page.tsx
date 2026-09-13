import { requireFacilitySession } from "@/lib/server-session";
import { safeCoreRequest } from "@/lib/facility-data";
import { FacilityUnavailable } from "@/components/FacilityUnavailable";
import { RefreshButton } from "@/components/RefreshButton";
import { AcknowledgeButton } from "./AcknowledgeButton";
import type { EscalationEvent } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function EscalationsPage() {
  const session = await requireFacilitySession();
  const result = await safeCoreRequest<EscalationEvent[]>(`/escalations/${session.facility_id}`);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-severity-red">Open escalations</h1>
        <RefreshButton />
      </div>
      {!result.ok && <div className="mt-3"><FacilityUnavailable reason={result.reason} /></div>}
      {result.ok && result.data.length === 0 && <p className="mt-3 text-sm text-slate-400">No open escalations.</p>}
      {result.ok && (
        <ul className="mt-3 divide-y divide-slate-100">
          {result.data.map((event) => (
            <li key={event.id} className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm font-semibold text-slate-800">Escalation {event.id.slice(0, 8)}</p>
                <p className="text-xs text-slate-400">{new Date(event.created_at).toLocaleString()} · {event.status}</p>
              </div>
              {event.status === "open" && <AcknowledgeButton id={event.id} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
