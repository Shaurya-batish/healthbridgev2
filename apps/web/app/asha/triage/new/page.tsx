import { getSessionToken, verifySession } from "@/lib/auth";
import { IconAlertTriangle } from "@/components/asha/icons";
import { TriageCaptureForm } from "./TriageCaptureForm";

export default async function NewTriagePage({ searchParams }: { searchParams: { abha?: string } }) {
  const token = getSessionToken();
  const session = token ? await verifySession(token) : null;
  const abha = searchParams.abha ?? "";

  if (!session?.facility_id) {
    return (
      <div className="flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-5 text-amber-900">
        <IconAlertTriangle className="mt-0.5 h-6 w-6 shrink-0" />
        <p className="text-lg">Your account has no facility assigned. Ask an admin to fix this before you can create a token.</p>
      </div>
    );
  }

  return <TriageCaptureForm abhaNumber={abha} facilityId={session.facility_id} />;
}
