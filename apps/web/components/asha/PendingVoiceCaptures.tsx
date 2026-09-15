"use client";

import { useCallback, useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n/LanguageProvider";
import { languageLabel } from "@/lib/i18n/languages";
import { deleteVoiceCapture, listVoiceCaptures, processVoiceQueue, retryVoiceCapture, RETENTION_HOURS, type QueuedVoiceCapture } from "@/lib/voice-queue";
import { queueTranscriber } from "@/lib/voice-transcriber";
import { AshaButton } from "@/components/asha/AshaButton";

const STATUS_TONE: Record<QueuedVoiceCapture["status"], string> = {
  pending_upload: "bg-amber-100 text-amber-900",
  transcribing: "bg-sky-100 text-sky-900",
  awaiting_confirmation: "bg-teal-100 text-teal-900",
  failed: "bg-red-100 text-red-900",
  completed: "bg-slate-100 text-slate-600",
};

/** The signed-in ASHA's own offline recordings: uploads eligible ones when
 * online (on mount, on reconnect, or on demand) and lets her review, retry or
 * delete them. Transcribed recordings are never submitted automatically. */
export function PendingVoiceCaptures({ userId }: { userId: string }) {
  const { t } = useI18n();
  const [captures, setCaptures] = useState<QueuedVoiceCapture[]>([]);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setCaptures(await listVoiceCaptures(userId));
  }, [userId]);

  const sync = useCallback(async () => {
    if (!navigator.onLine) return refresh();
    setBusy(true);
    try {
      await processVoiceQueue(userId, queueTranscriber);
    } finally {
      setBusy(false);
      await refresh();
    }
  }, [userId, refresh]);

  useEffect(() => {
    void sync();
    const onOnline = () => void sync();
    window.addEventListener("online", onOnline);
    // Scheduled backoff retries and captures orphaned by a reload need a
    // periodic pass; the queue itself skips anything not yet due.
    const timer = window.setInterval(() => void sync(), 20_000);
    return () => {
      window.removeEventListener("online", onOnline);
      window.clearInterval(timer);
    };
  }, [sync]);

  if (!captures.length) return null;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4" aria-labelledby="pending-voice-title">
      <div className="flex items-center justify-between gap-2">
        <h2 id="pending-voice-title" className="text-lg font-bold text-slate-800">
          {t("pending.title")}
        </h2>
        <button onClick={() => void sync()} disabled={busy} className="min-h-[44px] rounded-lg px-3 text-base font-semibold text-teal-800 disabled:opacity-50">
          {t("pending.checkNow")}
        </button>
      </div>
      <p className="mt-1 text-sm text-slate-500">{t("pending.retention", { hours: RETENTION_HOURS })}</p>
      <ul className="mt-3 space-y-3">
        {captures.map((c) => (
          <li key={c.id} className="rounded-xl border border-slate-200 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold text-slate-800">{t("pending.patient", { abha: c.abhaNumber })}</p>
              <span className={`rounded-full px-3 py-1 text-sm font-semibold ${STATUS_TONE[c.status]}`}>
                {c.status === "pending_upload" && c.lastError ? t("pending.status.retrying") : t(`pending.status.${c.status}`)}
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {t("pending.recordedAt", { time: new Date(c.capturedAt).toLocaleString(), language: languageLabel(c.language) })}
            </p>
            {c.lastError && c.status !== "awaiting_confirmation" && <p className="mt-1 font-mono text-xs text-slate-500">{c.lastError}</p>}
            <div className="mt-3 space-y-2">
              {c.status === "awaiting_confirmation" && (
                <AshaButton href={`/asha/triage/new?capture=${encodeURIComponent(c.id)}`}>{t("pending.review")}</AshaButton>
              )}
              {c.status === "failed" && c.audioBytes && (
                <AshaButton
                  variant="outline"
                  onClick={async () => {
                    await retryVoiceCapture(userId, c.id);
                    await sync();
                  }}
                >
                  {t("pending.retry")}
                </AshaButton>
              )}
              {c.status !== "completed" && c.status !== "transcribing" && (
                <AshaButton
                  variant="secondary"
                  onClick={async () => {
                    await deleteVoiceCapture(userId, c.id);
                    await refresh();
                  }}
                >
                  {t("pending.delete")}
                </AshaButton>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
