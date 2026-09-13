import { authHeader, coreRequest } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { requireFacilitySession } from "@/lib/server-session";
import { RefreshButton } from "@/components/RefreshButton";
import type { FollowUp } from "@/lib/types";
import { FollowUpStatusControl } from "./FollowUpStatusControl";

export const dynamic = "force-dynamic";

export default async function FollowUpsPage() {
  const session = await requireFacilitySession();
  const followUps = (await coreRequest(`/follow-ups/facility/${session.facility_id}`, {
    headers: authHeader(getSessionToken()),
  })) as FollowUp[];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">Follow-ups due</h1>
        <RefreshButton />
      </div>
      {followUps.length === 0 && <p className="mt-3 text-sm text-slate-400">Nothing due.</p>}
      <ul className="mt-3 divide-y divide-slate-100">
        {followUps.map((followUp) => (
          <li key={followUp.id} className="flex items-center justify-between gap-3 py-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">{followUp.reason}</p>
              <p className="text-xs text-slate-400">Due {followUp.scheduled_date}</p>
            </div>
            <FollowUpStatusControl id={followUp.id} />
          </li>
        ))}
      </ul>
    </div>
  );
}
