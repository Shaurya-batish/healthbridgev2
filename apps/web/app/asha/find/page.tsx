import { FindPatientForm } from "../FindPatientForm";

export default function FindPatientPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Find Patient</h1>
        <p className="mt-1 text-slate-500">Enter the patient&apos;s ABHA number to open their record.</p>
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <FindPatientForm />
      </div>
    </div>
  );
}
