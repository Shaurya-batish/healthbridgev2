import { NavBar } from "@/components/NavBar";

export default function FacilityLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <NavBar
        title="HealthBridge Facility"
        links={[
          { href: "/facility", label: "Dashboard" },
          { href: "/facility/queue", label: "Queue" },
          { href: "/facility/escalations", label: "Escalations" },
          { href: "/facility/patients", label: "Patients" },
        ]}
      />
      <main className="mx-auto max-w-4xl px-4 py-6">{children}</main>
    </div>
  );
}
