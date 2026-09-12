"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export default function FacilityPatientSearchPage() {
  const router = useRouter();
  const [abha, setAbha] = useState("");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!abha.trim()) return;
    router.push(`/facility/patients/${encodeURIComponent(abha.trim())}`);
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h1 className="text-lg font-semibold text-slate-800">Find patient</h1>
      <form onSubmit={onSubmit} className="mt-3 flex gap-2">
        <input
          value={abha}
          onChange={(e) => setAbha(e.target.value)}
          placeholder="ABHA number"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <button type="submit" className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800">
          Search
        </button>
      </form>
    </div>
  );
}
