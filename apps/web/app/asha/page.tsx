import Link from "next/link";
import { FindPatientForm } from "./FindPatientForm";

export default function AshaHomePage() {
  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-slate-800">Find a patient</h2>
        <p className="mt-1 text-sm text-slate-500">Enter an ABHA number to open their record, or register a new patient.</p>
        <FindPatientForm />
      </section>

      <section className="rounded-lg border border-dashed border-slate-300 bg-white p-5 text-center">
        <p className="text-sm text-slate-500">New patient at this visit?</p>
        <Link
          href="/asha/patients/new"
          className="mt-2 inline-block rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800"
        >
          Register patient
        </Link>
      </section>
    </div>
  );
}
