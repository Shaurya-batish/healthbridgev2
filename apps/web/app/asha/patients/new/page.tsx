import { RegisterPatientForm } from "./RegisterPatientForm";

export default function RegisterPatientPage({ searchParams }: { searchParams: { abha?: string } }) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Register Patient</h1>
        <p className="mt-1 text-slate-500">Works offline — this will save on this phone and sync automatically.</p>
      </div>
      <RegisterPatientForm initialAbha={searchParams.abha ?? ""} />
    </div>
  );
}
