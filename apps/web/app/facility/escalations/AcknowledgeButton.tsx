"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function AcknowledgeButton({ id }: { id: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function acknowledge() {
    setLoading(true);
    await fetch(`/api/escalations/${id}/acknowledge`, { method: "POST" });
    router.refresh();
  }

  return (
    <button
      onClick={acknowledge}
      disabled={loading}
      className="rounded-md bg-severity-red px-3 py-1 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
    >
      {loading ? "..." : "Acknowledge"}
    </button>
  );
}
