import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { SchemeBadge } from "@/components/SchemeBadge";
import type { Encounter, Patient } from "@/lib/types";

export default async function FacilityPatientPage({ params }: { params: { abha: string } }) {
  const token = getSessionToken();
  let patient: (Patient & { encounters?: Encounter[] }) | null = null;
  let abdmBundle: unknown = null;

  try {
    patient = (await coreRequest(`/patients/${encodeURIComponent(params.abha)}`, {
      headers: authHeader(token),
    })) as Patient & { encounters?: Encounter[] };
  } catch (err) {
    if (!(err instanceof UpstreamError && err.status === 404)) throw err;
  }

  if (!patient) {
    return <p className="text-sm text-slate-500">No patient found for ABHA number {params.abha}.</p>;
  }

  try {
    abdmBundle = await coreRequest(`/abdm/patient/${encodeURIComponent(params.abha)}`, { headers: authHeader(token) });
  } catch {
    abdmBundle = null;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-800">{patient.fhir.name?.[0]?.text ?? "Unnamed"}</h1>
            <p className="text-sm text-slate-500">ABHA: {patient.abha_number}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <SchemeBadge status={patient.scheme_status} />
            <span
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                abdmBundle ? "border-teal-300 bg-teal-50 text-teal-700" : "border-slate-300 bg-slate-50 text-slate-500"
              }`}
            >
              {abdmBundle ? "ABDM record linked (sandbox)" : "ABDM record unavailable"}
            </span>
          </div>
        </div>
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

      <details className="rounded-lg border border-slate-200 bg-white p-5">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Raw FHIR Patient resource</summary>
        <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
          {JSON.stringify(patient.fhir, null, 2)}
        </pre>
      </details>
    </div>
  );
}
