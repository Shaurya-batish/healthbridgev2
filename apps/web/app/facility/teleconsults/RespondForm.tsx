"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export function RespondForm({ teleconsultId }: { teleconsultId: string }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setLoading(true);
    await fetch(`/api/teleconsults/${teleconsultId}/response`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doctor_response_text: text }),
    });
    setLoading(false);
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="mt-2 flex gap-2">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Your advice / response"
        className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs"
      />
      <button type="submit" disabled={loading} className="rounded-md bg-teal-700 px-3 py-1 text-xs font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
        {loading ? "..." : "Send response"}
      </button>
    </form>
  );
}
