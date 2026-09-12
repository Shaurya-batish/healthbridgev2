import { getSessionToken, verifySession } from "@/lib/auth";
import { TriageCaptureForm } from "./TriageCaptureForm";

export default async function NewTriagePage({ searchParams }: { searchParams: { abha?: string } }) {
  const token = getSessionToken();
  const session = token ? await verifySession(token) : null;
  const abha = searchParams.abha ?? "";

  if (!session?.facility_id) {
    return (
      <div className="rounded-lg border border-severity-red bg-severity-red-bg p-5 text-sm text-severity-red">
        Your account has no facility assigned — an admin needs to fix this before you can create a token.
      </div>
    );
  }

  return <TriageCaptureForm abhaNumber={abha} facilityId={session.facility_id} />;
}
