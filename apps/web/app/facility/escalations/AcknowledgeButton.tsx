"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { postAction } from "@/lib/action-result";

export function AcknowledgeButton({ id }: { id: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function acknowledge() {
    setLoading(true);
    setError(null);
    const failure = await postAction(`/api/escalations/${id}/acknowledge`);
    setLoading(false);
    if (failure) {
      // Previously: the response was ignored and `loading` was never reset, so
      // a failed acknowledgement left the button stuck on "..." with no
      // message -- on a RED case that must never be ambiguous.
      setError(failure);
      return;
    }
    router.refresh();
  }

  return (
    <div className="text-right">
      <button
        onClick={acknowledge}
        disabled={loading}
        className="rounded-md bg-severity-red px-3 py-1 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
      >
        {loading ? "..." : "Acknowledge"}
      </button>
      {error && <p className="mt-1 max-w-[220px] text-xs text-severity-red">{error}</p>}
    </div>
  );
}
