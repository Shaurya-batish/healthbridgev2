import { ConnectivityStatus } from "@/components/asha/ConnectivityStatus";
import { AshaButton } from "@/components/asha/AshaButton";
import { PendingVoiceCaptures } from "@/components/asha/PendingVoiceCaptures";
import { IconUserPlus, IconSearch, IconQueue, IconClipboardPulse } from "@/components/asha/icons";
import { getSessionToken, verifySession } from "@/lib/auth";

export default async function AshaHomePage() {
  const token = getSessionToken();
  const session = token ? await verifySession(token) : null;

  return (
    <div className="space-y-5">
      <ConnectivityStatus />

      {session?.sub && <PendingVoiceCaptures userId={session.sub} />}

      <div className="space-y-3">
        <AshaButton href="/asha/patients/new" icon={<IconUserPlus />}>
          Register Patient
        </AshaButton>
        <AshaButton href="/asha/find" variant="secondary" icon={<IconSearch />}>
          Find Patient
        </AshaButton>
        <AshaButton href="/asha/queue" variant="outline" icon={<IconQueue />}>
          Today&apos;s Queue
        </AshaButton>
        <AshaButton href="/asha/medicines" variant="outline" icon={<IconClipboardPulse />}>
          Compare Medicines
        </AshaButton>
      </div>
    </div>
  );
}
