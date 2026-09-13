import { requireFacilitySession } from "@/lib/server-session";
import { safeCoreRequest } from "@/lib/facility-data";
import { FacilityUnavailable } from "@/components/FacilityUnavailable";
import type { DashboardTiles } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function FacilityDashboardPage() {
  const session = await requireFacilitySession();
  const result = await safeCoreRequest<DashboardTiles>(`/dashboard/${session.facility_id}`);

  if (!result.ok) {
    return <FacilityUnavailable reason={result.reason} />;
  }
  const tiles = result.data;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Tile label="Triaged by severity">
        <div className="flex gap-4">
          <Stat value={tiles.triaged_by_severity.RED} label="Red" className="text-severity-red" />
          <Stat value={tiles.triaged_by_severity.YELLOW} label="Yellow" className="text-severity-yellow" />
          <Stat value={tiles.triaged_by_severity.GREEN} label="Green" className="text-severity-green" />
        </div>
      </Tile>
      <Tile label="Queue length">
        <p className="text-3xl font-bold text-slate-800">{tiles.queue_length}</p>
      </Tile>
      <Tile label="Teleconsults done">
        <p className="text-3xl font-bold text-slate-800">{tiles.teleconsults_done}</p>
      </Tile>
      <Tile label="Red cases escalated">
        <p className="text-3xl font-bold text-severity-red">{tiles.red_cases_escalated}</p>
      </Tile>
    </div>
  );
}

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</h2>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Stat({ value, label, className }: { value: number; label: string; className?: string }) {
  return (
    <div>
      <p className={`text-2xl font-bold ${className}`}>{value}</p>
      <p className="text-xs text-slate-400">{label}</p>
    </div>
  );
}
