"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { postAction } from "@/lib/action-result";
import type { ReferralStatus } from "@/lib/types";

const NEXT_STATUS: Partial<Record<ReferralStatus, { label: string; next: ReferralStatus }>> = {
  pending: { label: "Accept", next: "accepted" },
  accepted: { label: "Mark completed", next: "completed" },
};

export function ReferralStatusControl({ id, status }: { id: string; status: ReferralStatus }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const action = NEXT_STATUS[status];
  if (!action) return null;

  async function advance() {
    setLoading(true);
    setError(null);
    const failure = await postAction(`/api/referrals/${id}/status`, { status: action!.next });
    setLoading(false);
    if (failure) {
      setError(failure);
      return;
    }
    router.refresh();
  }

  return (
    <div>
      <button
        onClick={advance}
        disabled={loading}
        className="rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        {loading ? "..." : action.label}
      </button>
      {error && <p className="mt-1 text-xs text-severity-red">{error}</p>}
    </div>
  );
}
