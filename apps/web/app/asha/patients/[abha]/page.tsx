import Link from "next/link";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { SchemeBadge } from "@/components/SchemeBadge";
import type { Encounter, Patient } from "@/lib/types";

export default async function AshaPatientPage({ params }: { params: { abha: string } }) {
  let patient: (Patient & { encounters?: Encounter[] }) | null = null;
  let unreachable = false;

  try {
    patient = (await coreRequest(`/patients/${encodeURIComponent(params.abha)}`, {
      headers: authHeader(getSessionToken()),
    })) as Patient & { encounters?: Encounter[] };
  } catch (err) {
    if (err instanceof UpstreamError && err.status === 404) {
      patient = null;
    } else {
      unreachable = true;
    }
  }

  if (unreachable) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-5 text-sm text-amber-900">
        Can&apos;t reach the server to look up this patient right now. If you&apos;re offline, you can still start a
        new visit — the record will resolve once you sync.
        <div className="mt-3">
          <Link
            href={`/asha/triage/new?abha=${encodeURIComponent(params.abha)}`}
            className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800"
          >
            Start visit anyway
          </Link>
        </div>
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-600">
        No patient found for ABHA number <span className="font-mono">{params.abha}</span>.
        <div className="mt-3">
          <Link href="/asha/patients/new" className="text-teal-700 underline">
            Register this patient
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-800">{patient.fhir.name?.[0]?.text ?? "Unnamed"}</h1>
            <p className="text-sm text-slate-500">ABHA: {patient.abha_number}</p>
          </div>
          <SchemeBadge status={patient.scheme_status} />
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <div>
            <dt className="text-slate-400">DOB</dt>
            <dd>{patient.fhir.birthDate ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Gender</dt>
            <dd>{patient.fhir.gender ?? "—"}</dd>
          </div>
        </dl>
        <Link
          href={`/asha/triage/new?abha=${encodeURIComponent(patient.abha_number)}`}
          className="mt-4 inline-block rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800"
        >
          Start visit / triage
        </Link>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-slate-700">Visit history</h2>
        {!patient.encounters?.length && <p className="mt-2 text-sm text-slate-400">No visits recorded yet.</p>}
        <ul className="mt-2 divide-y divide-slate-100">
          {patient.encounters?.map((enc) => (
            <li key={enc.id} className="py-2 text-sm text-slate-600">
              {new Date(enc.created_at).toLocaleString()}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
