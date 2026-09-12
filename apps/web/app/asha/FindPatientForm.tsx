"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export function FindPatientForm() {
  const router = useRouter();
  const [abha, setAbha] = useState("");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!abha.trim()) return;
    router.push(`/asha/patients/${encodeURIComponent(abha.trim())}`);
  }

  return (
    <form onSubmit={onSubmit} className="mt-3 flex gap-2">
      <input
        type="text"
        placeholder="ABHA number"
        value={abha}
        onChange={(e) => setAbha(e.target.value)}
        className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
      />
      <button type="submit" className="rounded-md bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-900">
        Open
      </button>
    </form>
  );
}
