import { authHeader, coreRequest } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { requireFacilitySession } from "@/lib/server-session";
import { RefreshButton } from "@/components/RefreshButton";
import type { Teleconsult } from "@/lib/types";
import { RespondForm } from "./RespondForm";

export const dynamic = "force-dynamic";

const STATUS_LABELS: Record<Teleconsult["status"], string> = {
  pending: "Waiting for a recording",
  recorded: "Recording ready to review",
  reviewed: "Reviewed",
};

export default async function TeleconsultsPage() {
  const session = await requireFacilitySession();
  const teleconsults = (await coreRequest(`/teleconsults/facility/${session.facility_id}`, {
    headers: authHeader(getSessionToken()),
  })) as Teleconsult[];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">Teleconsults</h1>
        <RefreshButton />
      </div>
      <p className="mt-1 text-xs text-slate-400">
        Real self-hosted store-and-forward — an actual recorded file, not a live video call.
      </p>
      {teleconsults.length === 0 && <p className="mt-3 text-sm text-slate-400">No teleconsult requests yet.</p>}
      <ul className="mt-3 divide-y divide-slate-100">
        {teleconsults.map((tc) => (
          <li key={tc.id} className="py-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-800">{STATUS_LABELS[tc.status]}</p>
              <p className="text-xs text-slate-400">{new Date(tc.created_at).toLocaleString()}</p>
            </div>
            {tc.status !== "pending" && (
              <audio controls className="mt-2 w-full" src={`/api/teleconsults/${tc.id}/media`}>
                <a href={`/api/teleconsults/${tc.id}/media`}>Download recording</a>
              </audio>
            )}
            {tc.doctor_response_text && (
              <p className="mt-2 rounded bg-slate-50 p-2 text-xs text-slate-600">Response: {tc.doctor_response_text}</p>
            )}
            {tc.status === "recorded" && <RespondForm teleconsultId={tc.id} />}
          </li>
        ))}
      </ul>
    </div>
  );
}
