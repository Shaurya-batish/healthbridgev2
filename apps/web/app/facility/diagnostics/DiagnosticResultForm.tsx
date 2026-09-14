"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { postAction } from "@/lib/action-result";

export function DiagnosticResultForm({ orderId }: { orderId: string }) {
  const router = useRouter();
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!result.trim()) return;
    setLoading(true);
    setError(null);
    const failure = await postAction(`/api/diagnostics/${orderId}/result`, { result_text: result });
    setLoading(false);
    if (failure) {
      setError(failure);
      return;
    }
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex items-start gap-2">
      <div>
        <input
          value={result}
          onChange={(e) => setResult(e.target.value)}
          aria-label="Diagnostic result"
          placeholder="Result"
          className="w-40 rounded-md border border-slate-300 px-2 py-1 text-xs"
        />
        {error && <p className="mt-1 text-xs text-severity-red">{error}</p>}
      </div>
      <button type="submit" disabled={loading} className="rounded-md bg-teal-700 px-2 py-1 text-xs font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
        {loading ? "..." : "Record result"}
      </button>
    </form>
  );
}
