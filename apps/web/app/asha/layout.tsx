import { OfflineSyncProvider } from "@/lib/OfflineSyncProvider";
import { OfflineBanner } from "@/components/OfflineBanner";
import { NavBar } from "@/components/NavBar";

export default function AshaLayout({ children }: { children: React.ReactNode }) {
  return (
    <OfflineSyncProvider>
      <div className="min-h-screen bg-slate-50">
        <NavBar
          title="HealthBridge ASHA"
          links={[
            { href: "/asha", label: "Home" },
            { href: "/asha/patients/new", label: "Register patient" },
          ]}
        />
        <OfflineBanner />
        <main className="mx-auto max-w-2xl px-4 py-6">{children}</main>
      </div>
    </OfflineSyncProvider>
  );
}
