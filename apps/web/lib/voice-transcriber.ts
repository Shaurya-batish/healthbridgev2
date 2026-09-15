"use client";

// Browser-side call to the authenticated transcription gateway, shared by the
// live recorder and the offline voice queue. Never fabricates a transcript:
// any failure is returned as a typed reason.
import type { CaptureLanguage } from "./i18n/languages";
import { arrayBufferToBase64 } from "./voice-recorder";
import type { Transcriber } from "./voice-queue";

export type ClientTranscribeResult =
  | {
      ok: true;
      transcript: string;
      translation_en: string;
      engine: string;
      model: string;
      duration_seconds: number | null;
      transcript_warnings: string[];
      translation_warnings: string[];
    }
  | { ok: false; retryable: boolean; reason: string };

const strings = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []);

// Problems with the recording itself: retrying the same bytes cannot help.
const NON_RETRYABLE = new Set(["invalid_request", "invalid_audio", "too_short", "too_long", "unsupported_format", "empty"]);

export async function transcribeAudio(bytes: ArrayBuffer, mimeType: string, language: CaptureLanguage): Promise<ClientTranscribeResult> {
  let res: Response;
  try {
    res = await fetch("/api/triage/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio_base64: arrayBufferToBase64(bytes), language, mime_type: mimeType }),
      signal: AbortSignal.timeout(100_000),
    });
  } catch {
    return { ok: false, retryable: true, reason: "network" };
  }
  if (!res.ok) {
    // 401 (session expired) and gateway errors are worth retrying later.
    return { ok: false, retryable: true, reason: res.status === 401 ? "signed_out" : "unavailable" };
  }
  const body = (await res.json().catch(() => null)) as Record<string, unknown> | null;
  if (!body) return { ok: false, retryable: true, reason: "unavailable" };
  if (body.transcription_unavailable) {
    const reason = typeof body.reason === "string" ? body.reason : "unavailable";
    return { ok: false, retryable: !NON_RETRYABLE.has(reason), reason };
  }
  if (typeof body.transcript !== "string" || typeof body.translation_en !== "string") {
    return { ok: false, retryable: true, reason: "unavailable" };
  }
  return {
    ok: true,
    transcript: body.transcript,
    translation_en: body.translation_en,
    engine: typeof body.engine === "string" ? body.engine : "unknown",
    model: typeof body.model === "string" ? body.model : "unknown",
    duration_seconds: typeof body.duration_seconds === "number" ? body.duration_seconds : null,
    transcript_warnings: strings(body.transcript_warnings),
    translation_warnings: strings(body.translation_warnings),
  };
}

export const queueTranscriber: Transcriber = async (capture) => {
  if (!capture.audioBytes) return { ok: false, retryable: false, error: "audio_deleted" };
  const result = await transcribeAudio(capture.audioBytes, capture.mimeType, capture.language);
  if (!result.ok) return { ok: false, retryable: result.retryable, error: result.reason };
  return {
    ok: true,
    transcript: {
      transcript: result.transcript,
      translation_en: result.translation_en,
      engine: result.engine,
      model: result.model,
      transcript_warnings: result.transcript_warnings,
      translation_warnings: result.translation_warnings,
    },
  };
};

/** i18n key for a transcription failure reason. */
export function transcriptionErrorKey(reason: string): string {
  if (reason === "empty") return "voice.error.transcription_empty";
  if (["invalid_request", "invalid_audio", "too_short", "too_long", "unsupported_format"].includes(reason)) return `voice.error.${reason}`;
  return "voice.error.transcription_unavailable";
}
