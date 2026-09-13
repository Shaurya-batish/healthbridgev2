"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ReferralStatus } from "@/lib/types";

const NEXT_STATUS: Partial<Record<ReferralStatus, { label: string; next: ReferralStatus }>> = {
  pending: { label: "Accept", next: "accepted" },
  accepted: { label: "Mark completed", next: "completed" },
};

export function ReferralStatusControl({ id, status }: { id: string; status: ReferralStatus }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const action = NEXT_STATUS[status];
  if (!action) return null;

  async function advance() {
    setLoading(true);
    await fetch(`/api/referrals/${id}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: action!.next }),
    });
    router.refresh();
  }

  return (
    <button
      onClick={advance}
      disabled={loading}
      className="rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
    >
      {loading ? "..." : action.label}
    </button>
  );
}
