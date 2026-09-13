import { ConnectivityStatus } from "@/components/asha/ConnectivityStatus";
import { AshaButton } from "@/components/asha/AshaButton";
import { IconUserPlus, IconSearch, IconQueue } from "@/components/asha/icons";

export default function AshaHomePage() {
  return (
    <div className="space-y-5">
      <ConnectivityStatus />

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
      </div>
    </div>
  );
}
