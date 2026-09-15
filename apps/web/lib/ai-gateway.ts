// Gateway-side handling of every call into the AI service, kept free of
// Next.js request/cookie plumbing so the degradation contract can be unit
// tested with the AI service genuinely absent (a transport that throws, as
// fetch does on ECONNREFUSED).
//
// The contract, per CLAUDE.md's offline-degradation rule: whatever happens
// on the AI side -- down, AI_MODE=degraded, laptop tunnel closed, timeout,
// 4xx, a malformed body -- the client receives a clean, typed "unavailable"
// signal and never a raw 5xx. The ASHA app then drops to the structured
// checklist, which runs the same rule table on-device.
import { UpstreamError } from "./api-client";

export const CAPTURE_LANGUAGES = ["en", "hi", "pa", "bn", "mr", "ta"] as const;
export type CaptureLanguage = (typeof CAPTURE_LANGUAGES)[number];

// Mirrors services/ai/app/schemas.py so an oversized body is refused here
// instead of being shipped across the network first.
const MAX_AUDIO_BASE64_CHARS = 15_000_000;
const MAX_COMPLAINT_CHARS = 4000;

export const EXTRACT_TIMEOUT_MS = 45_000;
export const TRANSCRIBE_TIMEOUT_MS = 90_000;
export const HEALTH_TIMEOUT_MS = 3_000;

export type AiCall = (path: string, init?: RequestInit, timeoutMs?: number) => Promise<unknown>;

export type AiUnavailable = { ai_unavailable: true };

export type TranscribeOutcome =
  | { transcript: string; translation_en: string; language: CaptureLanguage }
  | { transcription_unavailable: true; reason: "unavailable" | "empty" | "invalid_request" };

export interface AiStatus {
  ai_reachable: boolean;
  ai_mode: "local" | "degraded" | null;
  whisper_available: boolean;
  ollama_reachable: boolean;
}

const SEVERITIES = ["RED", "YELLOW", "GREEN"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonBlank(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function isCaptureLanguage(value: unknown): value is CaptureLanguage {
  return typeof value === "string" && (CAPTURE_LANGUAGES as readonly string[]).includes(value);
}

/** Text complaint -> facts -> rule decision. The complaint must already be
 * English (typed, or Whisper's translation of a voice note): no language is
 * forwarded, because the extraction prompt is deliberately English-only. */
export async function extractViaAi(payload: unknown, call: AiCall): Promise<Record<string, unknown> | AiUnavailable> {
  if (!isRecord(payload)) return { ai_unavailable: true };
  const complaint = payload.complaint_text;
  if (!nonBlank(complaint) || complaint.length > MAX_COMPLAINT_CHARS) return { ai_unavailable: true };

  const body: Record<string, unknown> = { complaint_text: complaint };
  if (typeof payload.age_months === "number" && Number.isFinite(payload.age_months)) body.age_months = payload.age_months;

  try {
    const result = await call("/triage/extract", { method: "POST", body: JSON.stringify(body) }, EXTRACT_TIMEOUT_MS);
    // Never pass through a body that doesn't carry a rule-engine decision.
    if (!isRecord(result) || !SEVERITIES.includes(result.severity as string) || typeof result.rule_id !== "string") {
      return { ai_unavailable: true };
    }
    return result;
  } catch {
    return { ai_unavailable: true };
  }
}

export async function transcribeViaAi(payload: unknown, call: AiCall): Promise<TranscribeOutcome> {
  if (
    !isRecord(payload) ||
    typeof payload.audio_base64 !== "string" ||
    payload.audio_base64.length === 0 ||
    payload.audio_base64.length > MAX_AUDIO_BASE64_CHARS ||
    !isCaptureLanguage(payload.language)
  ) {
    return { transcription_unavailable: true, reason: "invalid_request" };
  }

  try {
    const result = await call(
      "/transcribe",
      { method: "POST", body: JSON.stringify({ audio_base64: payload.audio_base64, language: payload.language }) },
      TRANSCRIBE_TIMEOUT_MS,
    );
    if (!isRecord(result) || !nonBlank(result.transcript) || !nonBlank(result.translation_en)) {
      return { transcription_unavailable: true, reason: "empty" };
    }
    return { transcript: result.transcript, translation_en: result.translation_en, language: payload.language };
  } catch (err) {
    if (err instanceof UpstreamError && err.status === 422) {
      const detail = isRecord(err.body) ? err.body.detail : undefined;
      return { transcription_unavailable: true, reason: detail === "empty_transcript" ? "empty" : "invalid_request" };
    }
    return { transcription_unavailable: true, reason: "unavailable" };
  }
}

export async function aiStatus(call: AiCall): Promise<AiStatus> {
  try {
    const result = await call("/health", { method: "GET" }, HEALTH_TIMEOUT_MS);
    if (!isRecord(result)) throw new Error("malformed");
    return {
      ai_reachable: true,
      ai_mode: result.ai_mode === "local" || result.ai_mode === "degraded" ? result.ai_mode : null,
      whisper_available: result.whisper_available === true,
      ollama_reachable: result.ollama_reachable === true,
    };
  } catch {
    return { ai_reachable: false, ai_mode: null, whisper_available: false, ollama_reachable: false };
  }
}
