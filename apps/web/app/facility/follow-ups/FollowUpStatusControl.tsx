"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { postAction } from "@/lib/action-result";

export function FollowUpStatusControl({ id }: { id: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function setStatus(status: "completed" | "missed") {
    setLoading(true);
    setError(null);
    const failure = await postAction(`/api/follow-ups/${id}/status`, { status });
    setLoading(false);
    if (failure) {
      setError(failure);
      return;
    }
    router.refresh();
  }

  return (
    <div>
      <div className="flex gap-2">
        <button
          onClick={() => setStatus("completed")}
          disabled={loading}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Completed
        </button>
        <button
          onClick={() => setStatus("missed")}
          disabled={loading}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Missed
        </button>
      </div>
      {error && <p className="mt-1 text-xs text-severity-red">{error}</p>}
    </div>
  );
}
