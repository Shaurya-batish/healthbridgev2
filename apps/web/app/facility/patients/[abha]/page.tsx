import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { requireFacilitySession } from "@/lib/server-session";
import { safeCoreRequest } from "@/lib/facility-data";
import { FacilityUnavailable } from "@/components/FacilityUnavailable";
import { SchemeBadge } from "@/components/SchemeBadge";
import type { Encounter, Patient } from "@/lib/types";
import { VerifySchemeButton } from "./VerifySchemeButton";
import { PatientActionForms } from "./PatientActionForms";

// ABDM's real, spec-accurate adapter is not yet connected to the live
// gateway -- see docs/REAL-INTEGRATION-AUDIT.md. This distinguishes "we
// haven't registered with NHA yet" from "the patient has no linked
// record" rather than collapsing both into one vague label.
type AbdmStatus = "linked" | "not_configured" | "unavailable" | "not_found";

export default async function FacilityPatientPage({ params }: { params: { abha: string } }) {
  const session = await requireFacilitySession();
  const token = getSessionToken();
  let abdmStatus: AbdmStatus = "not_found";

  const patientResult = await safeCoreRequest<Patient & { encounters?: Encounter[] }>(
    `/patients/${encodeURIComponent(params.abha)}`,
  );

  if (!patientResult.ok && patientResult.reason === "not_found") {
    return <p className="text-sm text-slate-500">No patient found for ABHA number {params.abha}.</p>;
  }
  if (!patientResult.ok) {
    return <FacilityUnavailable reason={patientResult.reason} />;
  }
  const patient = patientResult.data;

  try {
    await coreRequest(`/abdm/patient/${encodeURIComponent(params.abha)}`, { headers: authHeader(token) });
    abdmStatus = "linked";
  } catch (err) {
    if (err instanceof UpstreamError && err.status === 501) abdmStatus = "not_configured";
    else if (err instanceof UpstreamError && err.status === 404) abdmStatus = "not_found";
    else abdmStatus = "unavailable";
  }

  const ABDM_LABELS: Record<AbdmStatus, string> = {
    linked: "ABDM record linked",
    not_configured: "ABDM not connected (NHA registration pending — see docs/REAL-INTEGRATION-AUDIT.md)",
    unavailable: "ABDM unreachable right now",
    not_found: "No ABDM-linked record found",
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-800">{patient.fhir.name?.[0]?.text ?? "Unnamed"}</h1>
            <p className="text-sm text-slate-500">ABHA: {patient.abha_number}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              <SchemeBadge status={patient.scheme_status} />
              {patient.scheme_status !== "none" && (
                <span
                  className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
                    patient.scheme_verification_status === "verified"
                      ? "border-teal-300 bg-teal-50 text-teal-700"
                      : patient.scheme_verification_status === "failed"
                        ? "border-severity-red bg-severity-red-bg text-severity-red"
                        : "border-slate-300 bg-slate-50 text-slate-500"
                  }`}
                >
                  {patient.scheme_verification_status === "verified"
                    ? "Verified"
                    : patient.scheme_verification_status === "failed"
                      ? "Verification failed"
                      : "Not verified"}
                </span>
              )}
            </div>
            {patient.scheme_status !== "none" && patient.scheme_verification_status !== "verified" && (
              <VerifySchemeButton abhaNumber={patient.abha_number} />
            )}
            <span className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">
              {ABDM_LABELS[abdmStatus]}
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

      {patient.encounters && patient.encounters.length > 0 && (
        <PatientActionForms
          patientId={patient.id}
          encounterId={patient.encounters[0].id}
          facilityId={session.facility_id}
        />
      )}

      <details className="rounded-lg border border-slate-200 bg-white p-5">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Raw FHIR Patient resource</summary>
        <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
          {JSON.stringify(patient.fhir, null, 2)}
        </pre>
      </details>
    </div>
  );
}
