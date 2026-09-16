// Gateway-side handling of every call into the AI service, kept free of
// Next.js request/cookie plumbing so the degradation contract can be unit
// tested with the AI service genuinely absent (a transport that throws, as
// fetch does on ECONNREFUSED).
//
// The contract, per CLAUDE.md's offline-degradation rule: whatever happens
// on the AI side -- down, AI_MODE=degraded, laptop tunnel closed, timeout,
// 4xx, a malformed body -- the client receives a clean, typed "unavailable"
// signal and never a raw 5xx. The ASHA app then offers typed input and the
// structured checklist, which runs the same rule table on-device.
//
// Voice contract (one explicit two-step flow): /transcribe returns text only;
// the ASHA confirms it; /triage/extract receives ONLY the confirmed English
// complaint_text + age. Audio is never forwarded to extraction.
import { UpstreamError } from "./api-client";
import { AUDIO_MAX_BASE64_CHARS, isAllowedAudioMime } from "./audio-constraints";
import { CAPTURE_LANGUAGES, isCaptureLanguage, type CaptureLanguage } from "./i18n/languages";

export { CAPTURE_LANGUAGES, isCaptureLanguage };
export type { CaptureLanguage };

const MAX_COMPLAINT_CHARS = 4000;

export const EXTRACT_TIMEOUT_MS = 45_000;
export const TRANSCRIBE_TIMEOUT_MS = 90_000;
export const TRANSLATE_TIMEOUT_MS = 30_000;
export const HEALTH_TIMEOUT_MS = 3_000;

export type AiCall = (path: string, init?: RequestInit, timeoutMs?: number) => Promise<unknown>;

export type AiUnavailable = { ai_unavailable: true };

export type TranscribeFailureReason =
  | "unavailable"
  | "empty"
  | "invalid_request"
  | "invalid_audio"
  | "too_short"
  | "too_long"
  | "unsupported_format";

export const QUALITY_WARNINGS = ["repetitive_output", "low_confidence", "mostly_non_letters"] as const;
export type QualityWarning = (typeof QUALITY_WARNINGS)[number];

export type TranscribeOutcome =
  | {
      transcript: string;
      translation_en: string;
      language: CaptureLanguage;
      engine: string;
      model: string;
      duration_seconds: number | null;
      transcript_warnings: QualityWarning[];
      translation_warnings: QualityWarning[];
    }
  | { transcription_unavailable: true; reason: TranscribeFailureReason };

function warningsFrom(value: unknown): QualityWarning[] {
  return Array.isArray(value) ? value.filter((w): w is QualityWarning => (QUALITY_WARNINGS as readonly unknown[]).includes(w)) : [];
}

export type TranslateFailureReason = "language_not_installed" | "engine_not_installed" | "degraded_mode" | "unavailable" | "invalid_request";

export type TranslateOutcome =
  | { translation_en: string; source_language: CaptureLanguage; engine: string; engine_version: string | null }
  | { translation_unavailable: true; reason: TranslateFailureReason };

export interface AiStatus {
  ai_reachable: boolean;
  ai_mode: "local" | "degraded" | null;
  whisper_available: boolean;
  ollama_reachable: boolean;
  translation_languages: CaptureLanguage[];
}

const SEVERITIES = ["RED", "YELLOW", "GREEN"];

const TRANSCRIBE_422: Record<string, TranscribeFailureReason> = {
  empty_transcript: "empty",
  invalid_audio: "invalid_audio",
  audio_too_short: "too_short",
  audio_too_long: "too_long",
  unsupported_audio_format: "unsupported_format",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonBlank(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/** Confirmed English complaint -> facts -> rule decision. Only complaint_text
 * and age are forwarded: the extraction prompt is deliberately English-only,
 * and the language/original text are persisted by Core, not sent to the LLM. */
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
    payload.audio_base64.length > AUDIO_MAX_BASE64_CHARS ||
    !isCaptureLanguage(payload.language)
  ) {
    return { transcription_unavailable: true, reason: "invalid_request" };
  }
  if (!isAllowedAudioMime(payload.mime_type)) {
    return { transcription_unavailable: true, reason: "unsupported_format" };
  }

  try {
    const result = await call(
      "/transcribe",
      {
        method: "POST",
        body: JSON.stringify({ audio_base64: payload.audio_base64, language: payload.language, mime_type: payload.mime_type }),
      },
      TRANSCRIBE_TIMEOUT_MS,
    );
    if (!isRecord(result) || !nonBlank(result.transcript) || !nonBlank(result.translation_en)) {
      return { transcription_unavailable: true, reason: "empty" };
    }
    return {
      transcript: result.transcript,
      translation_en: result.translation_en,
      language: payload.language,
      engine: nonBlank(result.engine) ? result.engine : "unknown",
      model: nonBlank(result.model) ? result.model : "unknown",
      duration_seconds: typeof result.duration_seconds === "number" ? result.duration_seconds : null,
      transcript_warnings: warningsFrom(result.transcript_warnings),
      translation_warnings: warningsFrom(result.translation_warnings),
    };
  } catch (err) {
    if (err instanceof UpstreamError && err.status === 422) {
      const detail = isRecord(err.body) ? err.body.detail : undefined;
      return { transcription_unavailable: true, reason: (typeof detail === "string" && TRANSCRIBE_422[detail]) || "invalid_request" };
    }
    return { transcription_unavailable: true, reason: "unavailable" };
  }
}

/** Typed complaint in the selected language -> labelled machine English.
 * Never used for clinical rule text, never returns a severity. */
export async function translateViaAi(payload: unknown, call: AiCall): Promise<TranslateOutcome> {
  if (
    !isRecord(payload) ||
    !nonBlank(payload.text) ||
    payload.text.length > MAX_COMPLAINT_CHARS ||
    !isCaptureLanguage(payload.source_language) ||
    payload.source_language === "en"
  ) {
    return { translation_unavailable: true, reason: "invalid_request" };
  }
  try {
    const result = await call(
      "/translate",
      { method: "POST", body: JSON.stringify({ text: payload.text, source_language: payload.source_language }) },
      TRANSLATE_TIMEOUT_MS,
    );
    if (!isRecord(result) || !nonBlank(result.translation_en)) {
      return { translation_unavailable: true, reason: "unavailable" };
    }
    return {
      translation_en: result.translation_en,
      source_language: payload.source_language,
      engine: nonBlank(result.engine) ? result.engine : "unknown",
      engine_version: nonBlank(result.engine_version) ? result.engine_version : null,
    };
  } catch (err) {
    if (err instanceof UpstreamError && err.status === 503 && isRecord(err.body) && isRecord(err.body.detail)) {
      const reason = err.body.detail.reason;
      if (reason === "language_not_installed" || reason === "engine_not_installed" || reason === "degraded_mode") {
        return { translation_unavailable: true, reason };
      }
    }
    if (err instanceof UpstreamError && err.status === 422) return { translation_unavailable: true, reason: "invalid_request" };
    return { translation_unavailable: true, reason: "unavailable" };
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
      translation_languages: Array.isArray(result.translation_languages)
        ? result.translation_languages.filter(isCaptureLanguage)
        : [],
    };
  } catch {
    return { ai_reachable: false, ai_mode: null, whisper_available: false, ollama_reachable: false, translation_languages: [] };
  }
}
