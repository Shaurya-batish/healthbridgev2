"use client";

import { useEffect, useRef, useState } from "react";
import { AUDIO_MAX_SECONDS } from "@/lib/audio-constraints";
import { useI18n } from "@/lib/i18n/LanguageProvider";
import { browserRecorderDeps, sha256Hex, VoiceRecorderController, type RecorderState } from "@/lib/voice-recorder";
import { AshaButton } from "@/components/asha/AshaButton";
import { IconAlertTriangle } from "@/components/asha/icons";

export interface RecordedAudio {
  bytes: ArrayBuffer;
  mimeType: string;
  durationSeconds: number;
  sha256: string;
  consentConfirmedAt: string;
  capturedAt: string;
}

/**
 * Tap-to-start / tap-to-stop recording (no press-and-hold, so it works with a
 * keyboard, switch access and gloved hands). Microphone tracks are released
 * on stop, cancel, unmount and page hide -- see VoiceRecorderController.
 */
export function VoiceRecorderPanel({ busy, onSubmit }: { busy: boolean; onSubmit: (audio: RecordedAudio) => void }) {
  const { t } = useI18n();
  const [state, setState] = useState<RecorderState>({ status: "idle" });
  const [consentAt, setConsentAt] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const controllerRef = useRef<VoiceRecorderController | null>(null);

  useEffect(() => {
    const controller = new VoiceRecorderController(browserRecorderDeps(), setState);
    controllerRef.current = controller;
    const release = () => controller.dispose();
    window.addEventListener("pagehide", release);
    return () => {
      window.removeEventListener("pagehide", release);
      controller.dispose();
    };
  }, []);

  function start() {
    if (!consentAt) return;
    setStartedAt(new Date().toISOString());
    void controllerRef.current?.start();
  }

  async function submit() {
    if (state.status !== "recorded" || !consentAt || !startedAt) return;
    const bytes = await state.blob.arrayBuffer();
    onSubmit({
      bytes,
      mimeType: state.mimeType,
      durationSeconds: state.durationSeconds,
      sha256: await sha256Hex(bytes),
      consentConfirmedAt: consentAt,
      capturedAt: startedAt,
    });
  }

  const recording = state.status === "recording" || state.status === "requesting";

  return (
    <div className="mt-4 space-y-3">
      <label className="flex min-h-[44px] items-start gap-3 rounded-xl bg-slate-50 p-3 text-base text-slate-700">
        <input
          type="checkbox"
          checked={!!consentAt}
          disabled={recording || busy}
          onChange={(e) => setConsentAt(e.target.checked ? new Date().toISOString() : null)}
          className="mt-1 h-6 w-6 shrink-0 accent-teal-700"
        />
        <span>{t("voice.consent")}</span>
      </label>
      {!consentAt && state.status === "idle" && <p className="text-sm text-slate-500">{t("voice.consentFirst")}</p>}

      <div role="status" aria-live="polite" className="min-h-[1.5rem] text-lg font-semibold text-slate-700">
        {state.status === "requesting" && t("voice.requesting")}
        {state.status === "recording" && (
          <span className="flex items-center gap-2 text-severity-red">
            <span className="h-3 w-3 animate-pulse rounded-full bg-severity-red" aria-hidden="true" />
            {t("voice.recording", { seconds: state.elapsedSeconds, max: AUDIO_MAX_SECONDS })}
          </span>
        )}
        {state.status === "recorded" && (
          <>
            {t("voice.recorded", { seconds: state.durationSeconds })}
            {state.autoStopped && <span className="block text-sm font-normal text-amber-800">{t("voice.autoStopped", { max: AUDIO_MAX_SECONDS })}</span>}
          </>
        )}
      </div>

      {state.status === "error" && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-3 text-amber-900" role="alert">
          <IconAlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <p>{t(`voice.error.${state.error}`, { max: AUDIO_MAX_SECONDS })}</p>
        </div>
      )}

      {(state.status === "idle" || state.status === "error") && (
        <AshaButton onClick={start} disabled={!consentAt || busy}>
          {state.status === "error" ? t("voice.rerecord") : t("voice.start")}
        </AshaButton>
      )}
      {state.status === "recording" && (
        <AshaButton onClick={() => controllerRef.current?.stop()} variant="danger">
          {t("voice.stop")}
        </AshaButton>
      )}
      {recording && (
        <AshaButton onClick={() => controllerRef.current?.cancel()} variant="secondary">
          {t("voice.cancel")}
        </AshaButton>
      )}
      {state.status === "recorded" && (
        <>
          <AshaButton onClick={submit} disabled={busy}>
            {t("voice.transcribe")}
          </AshaButton>
          <AshaButton onClick={() => controllerRef.current?.cancel()} variant="secondary" disabled={busy}>
            {t("voice.rerecord")}
          </AshaButton>
        </>
      )}
      <p className="text-sm text-slate-500">{t("voice.privacy")}</p>
    </div>
  );
}
