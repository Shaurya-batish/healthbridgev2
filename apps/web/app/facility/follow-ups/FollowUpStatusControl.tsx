"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function FollowUpStatusControl({ id }: { id: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function setStatus(status: "completed" | "missed") {
    setLoading(true);
    await fetch(`/api/follow-ups/${id}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    router.refresh();
  }

  return (
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
  );
}
