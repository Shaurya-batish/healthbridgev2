"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function VerifySchemeButton({ abhaNumber }: { abhaNumber: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function verify() {
    setLoading(true);
    setError(null);
    const res = await fetch(`/api/patients/${encodeURIComponent(abhaNumber)}/verify-scheme`, { method: "POST" });
    setLoading(false);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(
        body.detail === "scheme_verification_not_configured"
          ? "Not connected — needs NHA empanelment (see docs/REAL-INTEGRATION-AUDIT.md)."
          : "Verification call failed.",
      );
      return;
    }
    router.refresh();
  }

  return (
    <div className="text-right">
      <button
        onClick={verify}
        disabled={loading}
        className="rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        {loading ? "Checking..." : "Verify scheme eligibility"}
      </button>
      {error && <p className="mt-1 max-w-[220px] text-xs text-severity-red">{error}</p>}
    </div>
  );
}
