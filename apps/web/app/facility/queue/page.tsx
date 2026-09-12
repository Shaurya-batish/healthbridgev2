import { authHeader, coreRequest } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { requireFacilitySession } from "@/lib/server-session";
import { SeverityBadge } from "@/components/SeverityBadge";
import { RefreshButton } from "@/components/RefreshButton";
import type { QueueToken } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function QueuePage() {
  const session = await requireFacilitySession();
  const queue = (await coreRequest(`/queue/${session.facility_id}`, {
    headers: authHeader(getSessionToken()),
  })) as QueueToken[];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">Queue</h1>
        <RefreshButton />
      </div>
      {queue.length === 0 && <p className="mt-3 text-sm text-slate-400">No tokens waiting.</p>}
      <ul className="mt-3 divide-y divide-slate-100">
        {queue.map((token, idx) => (
          <li key={token.id} className="flex items-center justify-between py-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">
                #{idx + 1} · Token {token.token_number}
              </p>
              <p className="text-xs text-slate-400">{token.status}</p>
            </div>
            <SeverityBadge severity={token.severity} />
          </li>
        ))}
      </ul>
    </div>
  );
}
