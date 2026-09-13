import { authHeader, coreRequest } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { requireFacilitySession } from "@/lib/server-session";
import { SeverityBadge } from "@/components/SeverityBadge";
import { IconQueue, IconAlertTriangle } from "@/components/asha/icons";
import type { QueueToken } from "@/lib/types";

export const dynamic = "force-dynamic";

const STATUS_LABELS: Record<QueueToken["status"], string> = {
  waiting: "Waiting",
  in_progress: "With doctor",
  done: "Seen",
};

export default async function AshaQueuePage() {
  let facilityId: string | null = null;
  try {
    facilityId = (await requireFacilitySession()).facility_id;
  } catch {
    facilityId = null;
  }

  let queue: QueueToken[] | null = null;
  if (facilityId) {
    try {
      queue = (await coreRequest(`/queue/${facilityId}`, {
        headers: authHeader(getSessionToken()),
      })) as QueueToken[];
    } catch {
      queue = null;
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Today&apos;s Queue</h1>
        <p className="mt-1 text-slate-500">Patients waiting at your facility, most urgent first.</p>
      </div>

      {!facilityId && (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-amber-900">
          <IconAlertTriangle className="mt-0.5 h-6 w-6 shrink-0" />
          <p>Your account has no facility assigned. Ask an admin to fix this before you can see the queue.</p>
        </div>
      )}

      {facilityId && queue === null && (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-amber-900">
          <IconAlertTriangle className="mt-0.5 h-6 w-6 shrink-0" />
          <p>We couldn&apos;t load the queue right now. Your saved information is safe — try again in a moment.</p>
        </div>
      )}

      {queue !== null && queue.length === 0 && (
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-5 text-slate-500">
          <IconQueue className="h-6 w-6 shrink-0" />
          <p>No patients waiting right now.</p>
        </div>
      )}

      {queue !== null && queue.length > 0 && (
        <ul className="space-y-3">
          {queue.map((token, idx) => (
            <li key={token.id} className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4">
              <div>
                <p className="text-lg font-semibold text-slate-800">
                  #{idx + 1} · Token {token.token_number}
                </p>
                <p className="text-sm text-slate-500">{STATUS_LABELS[token.status]}</p>
              </div>
              <SeverityBadge severity={token.severity} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
