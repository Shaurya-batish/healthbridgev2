"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export function DiagnosticResultForm({ orderId }: { orderId: string }) {
  const router = useRouter();
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!result.trim()) return;
    setLoading(true);
    await fetch(`/api/diagnostics/${orderId}/result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result_text: result }),
    });
    setLoading(false);
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex items-center gap-2">
      <input
        value={result}
        onChange={(e) => setResult(e.target.value)}
        placeholder="Result"
        className="w-40 rounded-md border border-slate-300 px-2 py-1 text-xs"
      />
      <button type="submit" disabled={loading} className="rounded-md bg-teal-700 px-2 py-1 text-xs font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
        {loading ? "..." : "Record result"}
      </button>
    </form>
  );
}
