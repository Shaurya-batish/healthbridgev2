"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function AdjustStockControl({ stockId }: { stockId: string }) {
  const router = useRouter();
  const [amount, setAmount] = useState("1");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function adjust(reason: "dispensed" | "restock") {
    const qty = Number(amount);
    if (!qty || qty <= 0) return;
    setLoading(true);
    setError(null);
    const res = await fetch(`/api/medicine-stock/${stockId}/adjust`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ change_qty: reason === "dispensed" ? -qty : qty, reason }),
    });
    setLoading(false);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(typeof body.detail === "string" ? body.detail : "Could not update stock.");
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        aria-label="Quantity to dispense or restock"
        min={1}
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        className="w-16 rounded-md border border-slate-300 px-2 py-1 text-sm"
      />
      <button
        onClick={() => adjust("dispensed")}
        disabled={loading}
        className="rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        Dispense
      </button>
      <button
        onClick={() => adjust("restock")}
        disabled={loading}
        className="rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        Restock
      </button>
      {error && <p className="text-xs text-severity-red">{error}</p>}
    </div>
  );
}
