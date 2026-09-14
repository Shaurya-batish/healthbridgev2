"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { postAction } from "@/lib/action-result";

export function RespondForm({ teleconsultId }: { teleconsultId: string }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    // A doctor's advice silently vanishing is the worst failure on this
    // screen: the response was previously never checked, so a failed POST
    // looked identical to a successful one.
    const failure = await postAction(`/api/teleconsults/${teleconsultId}/response`, { doctor_response_text: text });
    setLoading(false);
    if (failure) {
      setError(failure);
      return;
    }
    router.refresh();
  }

  return (
    <div>
      <form onSubmit={onSubmit} className="mt-2 flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Your advice or response"
          placeholder="Your advice / response"
          className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs"
        />
        <button type="submit" disabled={loading} className="rounded-md bg-teal-700 px-3 py-1 text-xs font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
          {loading ? "..." : "Send response"}
        </button>
      </form>
      {/* The typed advice is deliberately left in the field on failure so the
          doctor can retry without retyping it. */}
      {error && <p className="mt-1 text-xs text-severity-red">{error}</p>}
    </div>
  );
}
