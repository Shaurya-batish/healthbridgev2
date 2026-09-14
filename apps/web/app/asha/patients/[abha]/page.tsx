import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { SchemeBadge } from "@/components/SchemeBadge";
import { AshaButton } from "@/components/asha/AshaButton";
import { IconArrowRight, IconAlertTriangle } from "@/components/asha/icons";
import type { PatientDetail } from "@/lib/types";

export default async function AshaPatientPage({ params }: { params: { abha: string } }) {
  let detail: PatientDetail | null = null;
  let unreachable = false;

  try {
    detail = (await coreRequest(`/patients/${encodeURIComponent(params.abha)}`, {
      headers: authHeader(getSessionToken()),
    })) as PatientDetail;
  } catch (err) {
    if (err instanceof UpstreamError && err.status === 404) {
      detail = null;
    } else {
      unreachable = true;
    }
  }

  if (unreachable) {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-amber-900">
          <IconAlertTriangle className="mt-0.5 h-6 w-6 shrink-0" />
          <p>We couldn&apos;t reach the server to look up this patient right now. If you&apos;re offline, you can still start a visit — it will save on this phone.</p>
        </div>
        <AshaButton href={`/asha/triage/new?abha=${encodeURIComponent(params.abha)}`} icon={<IconArrowRight />}>
          Start Visit Anyway
        </AshaButton>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 text-slate-600">
          No patient found for ABHA number <span className="font-mono">{params.abha}</span>.
        </div>
        <AshaButton href={`/asha/patients/new?abha=${encodeURIComponent(params.abha)}`} variant="secondary">
          Register This Patient
        </AshaButton>
      </div>
    );
  }

  const { patient } = detail;
  const encounters = detail.encounters ?? [];

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">{patient.fhir.name?.[0]?.text ?? "Unnamed"}</h1>
            <p className="text-slate-500">ABHA: {patient.abha_number}</p>
          </div>
          <SchemeBadge status={patient.scheme_status} />
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-base">
          <div>
            <dt className="text-sm text-slate-500">Date of birth</dt>
            <dd className="font-medium text-slate-700">{patient.fhir.birthDate ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-500">Gender</dt>
            <dd className="font-medium text-slate-700">{patient.fhir.gender ?? "—"}</dd>
          </div>
        </dl>
      </div>

      <AshaButton href={`/asha/triage/new?abha=${encodeURIComponent(patient.abha_number)}`} icon={<IconArrowRight />}>
        Start Visit
      </AshaButton>

      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-700">Past Visits</h2>
        {!encounters.length && <p className="mt-2 text-slate-500">No visits recorded yet.</p>}
        <ul className="mt-2 divide-y divide-slate-100">
          {encounters.map((enc) => (
            <li key={enc.id} className="py-2 text-base text-slate-600">
              {new Date(enc.created_at).toLocaleString()}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
