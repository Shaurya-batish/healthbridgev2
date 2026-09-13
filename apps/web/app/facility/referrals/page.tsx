import { requireFacilitySession } from "@/lib/server-session";
import { safeCoreRequest } from "@/lib/facility-data";
import { FacilityUnavailable } from "@/components/FacilityUnavailable";
import { RefreshButton } from "@/components/RefreshButton";
import type { Referral } from "@/lib/types";
import { ReferralStatusControl } from "./ReferralStatusControl";

export const dynamic = "force-dynamic";

export default async function ReferralsPage() {
  const session = await requireFacilitySession();
  const result = await safeCoreRequest<Referral[]>(`/referrals/facility/${session.facility_id}`);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">Referrals</h1>
        <RefreshButton />
      </div>
      {!result.ok && <div className="mt-3"><FacilityUnavailable reason={result.reason} /></div>}
      {result.ok && result.data.length === 0 && <p className="mt-3 text-sm text-slate-400">No referrals yet.</p>}
      {result.ok && (
        <ul className="mt-3 divide-y divide-slate-100">
          {result.data.map((referral) => {
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
      )}
    </div>
  );
}
