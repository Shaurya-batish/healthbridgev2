import { authHeader, coreRequest } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { requireFacilitySession } from "@/lib/server-session";
import { RefreshButton } from "@/components/RefreshButton";
import type { Referral } from "@/lib/types";
import { ReferralStatusControl } from "./ReferralStatusControl";

export const dynamic = "force-dynamic";

export default async function ReferralsPage() {
  const session = await requireFacilitySession();
  const referrals = (await coreRequest(`/referrals/facility/${session.facility_id}`, {
    headers: authHeader(getSessionToken()),
  })) as Referral[];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">Referrals</h1>
        <RefreshButton />
      </div>
      {referrals.length === 0 && <p className="mt-3 text-sm text-slate-400">No referrals yet.</p>}
      <ul className="mt-3 divide-y divide-slate-100">
        {referrals.map((referral) => {
          const direction = referral.from_facility_id === session.facility_id ? "Sent" : "Received";
          return (
            <li key={referral.id} className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm font-semibold text-slate-800">
                  {direction} · {referral.reason}
                </p>
                <p className="text-xs text-slate-400">
                  {new Date(referral.created_at).toLocaleString()} · {referral.status}
                </p>
              </div>
              <ReferralStatusControl id={referral.id} status={referral.status} />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
