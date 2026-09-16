"use client";

import { useState, type FormEvent } from "react";
import { formLabel, releaseLabel, strengthLabel } from "@/lib/medicine-format";
import type { MedicineList, MedicineSummary } from "@/lib/types";

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; data: MedicineList }
  | { status: "error"; message: string };

export function describeHttpFailure(status: number): string {
  if (status === 401) return "Your session has expired. Sign in again.";
  if (status === 403) return "You don't have access to this facility's data.";
  if (status === 422) return "Enter at least 2 characters.";
  return "Medicine data is unavailable right now. Try again in a moment.";
}

/** Searches imported reference medicines (brand or ingredient). */
export function MedicineSearch({ onSelect, compact }: { onSelect: (medicine: MedicineSummary) => void; compact?: boolean }) {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<SearchState>({ status: "idle" });

  async function search(e: FormEvent) {
    e.preventDefault();
    if (query.trim().length < 2) return setState({ status: "error", message: describeHttpFailure(422) });
    setState({ status: "loading" });
    try {
      const res = await fetch(`/api/medicines?q=${encodeURIComponent(query.trim())}&limit=20`);
      if (!res.ok) return setState({ status: "error", message: describeHttpFailure(res.status) });
      setState({ status: "done", data: (await res.json()) as MedicineList });
    } catch {
      setState({ status: "error", message: describeHttpFailure(502) });
    }
  }

  return (
    <div>
      <form onSubmit={search} className="flex gap-2" role="search">
        <label htmlFor="medicine-query" className="sr-only">
          Medicine brand or ingredient
        </label>
        <input
          id="medicine-query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Brand or ingredient, e.g. paracetamol"
          className={`min-h-[44px] w-full rounded-lg border-2 border-slate-300 px-3 ${compact ? "text-sm" : "text-base"}`}
        />
        <button type="submit" className="min-h-[44px] rounded-lg bg-teal-700 px-4 font-semibold text-white disabled:opacity-50" disabled={state.status === "loading"}>
          Search
        </button>
      </form>

      <div aria-live="polite" className="mt-3">
        {state.status === "loading" && <p className="text-sm text-slate-500">Searching…</p>}
        {state.status === "error" && <p className="text-sm text-severity-red">{state.message}</p>}
        {state.status === "done" && state.data.total === 0 && (
          <p className="text-sm text-slate-500">
            No matching medicines in the imported reference data. If no dataset has been imported on this server yet, an admin must run
            the medicine importer (see docs).
          </p>
        )}
        {state.status === "done" && state.data.items.length > 0 && (
          <>
            <p className="text-xs text-slate-500">
              Showing {state.data.items.length} of {state.data.total}
            </p>
            <ul className="mt-1 divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
              {state.data.items.map((m) => (
                <li key={m.id}>
                  <button type="button" onClick={() => onSelect(m)} className="block min-h-[44px] w-full px-3 py-2 text-left hover:bg-slate-50">
                    <span className="block font-semibold text-slate-800">
                      {m.brand_name}
                      {m.is_discontinued && <span className="ml-2 text-xs font-normal text-severity-red">discontinued</span>}
                    </span>
                    <span className="block text-sm text-slate-600">{m.ingredients.map(strengthLabel).join(" + ") || "No ingredients listed"}</span>
                    <span className="block text-xs text-slate-500">
                      {formLabel(m.dosage_form)} · {releaseLabel(m.release_type)}
                      {m.manufacturer ? ` · ${m.manufacturer}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
