"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AshaButton } from "@/components/asha/AshaButton";
import { IconSearch } from "@/components/asha/icons";

export function FindPatientForm() {
  const router = useRouter();
  const [abha, setAbha] = useState("");
  const [touched, setTouched] = useState(false);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!abha.trim()) return;
    router.push(`/asha/patients/${encodeURIComponent(abha.trim())}`);
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <label className="block">
        <span className="text-base font-semibold text-slate-700">ABHA Number</span>
        <input
          type="text"
          inputMode="numeric"
          placeholder="e.g. 12-3456-7890-1234"
          value={abha}
          onChange={(e) => setAbha(e.target.value)}
          className="mt-2 w-full rounded-xl border-2 border-slate-300 px-4 py-4 text-lg focus:border-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-600 focus:ring-offset-1"
        />
        {touched && !abha.trim() && <p className="mt-1 text-sm text-red-700">Enter the patient&apos;s ABHA number.</p>}
      </label>
      <AshaButton type="submit" icon={<IconSearch />}>
        Find Patient
      </AshaButton>
    </form>
  );
}
