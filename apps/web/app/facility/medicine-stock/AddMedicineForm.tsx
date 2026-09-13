"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export function AddMedicineForm({ facilityId }: { facilityId: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("tablets");
  const [quantity, setQuantity] = useState("0");
  const [threshold, setThreshold] = useState("0");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const res = await fetch("/api/medicine-stock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        facility_id: facilityId,
        medicine_name: name,
        unit,
        initial_quantity: Number(quantity),
        reorder_threshold: Number(threshold),
      }),
    });
    setLoading(false);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(typeof body.detail === "string" ? body.detail : "Could not add item.");
      return;
    }
    setName("");
    setQuantity("0");
    setThreshold("0");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="mt-4 flex flex-wrap items-end gap-2 border-t border-slate-100 pt-4">
      <label className="text-sm">
        <span className="block text-slate-500">Medicine name</span>
        <input required value={name} onChange={(e) => setName(e.target.value)} className="mt-1 rounded-md border border-slate-300 px-2 py-1" />
      </label>
      <label className="text-sm">
        <span className="block text-slate-500">Unit</span>
        <input value={unit} onChange={(e) => setUnit(e.target.value)} className="mt-1 w-24 rounded-md border border-slate-300 px-2 py-1" />
      </label>
      <label className="text-sm">
        <span className="block text-slate-500">Starting quantity</span>
        <input type="number" min={0} value={quantity} onChange={(e) => setQuantity(e.target.value)} className="mt-1 w-24 rounded-md border border-slate-300 px-2 py-1" />
      </label>
      <label className="text-sm">
        <span className="block text-slate-500">Reorder threshold</span>
        <input type="number" min={0} value={threshold} onChange={(e) => setThreshold(e.target.value)} className="mt-1 w-24 rounded-md border border-slate-300 px-2 py-1" />
      </label>
      <button type="submit" disabled={loading} className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
        {loading ? "Adding..." : "Add item"}
      </button>
      {error && <p className="w-full text-sm text-severity-red">{error}</p>}
    </form>
  );
}
