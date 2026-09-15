// Pure state for one complaint capture (typed or voice), from first capture
// to the ASHA's confirmation. This is where the "never extract from English
// that no longer matches what the caregiver said" rule lives on the client;
// Core re-enforces the same rules server-side (services/core/app/schemas.py
// ComplaintCaptureIn) so a bypassed UI still cannot store an inconsistent
// capture.
import type { CaptureLanguage } from "./i18n/languages";

export type InputSource = "typed" | "voice";

/**
 * not_required: English capture, the original IS the English.
 * missing:      non-English, no English text yet (e.g. no translation package).
 * machine:      English is exactly the machine translation of the current original.
 * manual:       English was typed or corrected by the ASHA for the current original.
 * stale:        the original changed after the English was produced; must be
 *               retranslated or explicitly corrected before confirmation.
 */
export type TranslationStatus = "not_required" | "missing" | "machine" | "manual" | "stale";

export interface AudioMeta {
  sha256: string;
  durationSeconds: number;
  mimeType: string;
}

export interface CaptureDraft {
  clientCaptureId: string;
  inputSource: InputSource;
  language: CaptureLanguage;
  capturedAt: string;
  consentConfirmedAt: string | null;
  audio: AudioMeta | null;
  /** First captured text (typed or Whisper transcript) -- never overwritten. */
  originalText: string;
  /** First machine translation (Whisper's for voice) -- never overwritten. */
  initialMachineTranslationEn: string | null;
  initialTranslationEngine: string | null;
  /** Latest machine translation (replaced by a retranslation). */
  machineTranslationEn: string | null;
  translationEngine: string | null;
  currentOriginal: string;
  currentEnglish: string;
  /** The original text the current English corresponds to. */
  englishSource: string | null;
  translationStatus: TranslationStatus;
}

const same = (a: string | null, b: string | null) => (a ?? "").trim() === (b ?? "").trim();

export function createTypedDraft(id: string, language: CaptureLanguage, text: string, now: string): CaptureDraft {
  const english = language === "en";
  return {
    clientCaptureId: id,
    inputSource: "typed",
    language,
    capturedAt: now,
    consentConfirmedAt: null,
    audio: null,
    originalText: text,
    initialMachineTranslationEn: null,
    initialTranslationEngine: null,
    machineTranslationEn: null,
    translationEngine: null,
    currentOriginal: text,
    currentEnglish: english ? text : "",
    englishSource: english ? text : null,
    translationStatus: english ? "not_required" : "missing",
  };
}

export function createVoiceDraft(input: {
  id: string;
  language: CaptureLanguage;
  transcript: string;
  translationEn: string;
  engine: string;
  audio: AudioMeta;
  consentConfirmedAt: string;
  capturedAt: string;
}): CaptureDraft {
  const english = input.language === "en";
  return {
    clientCaptureId: input.id,
    inputSource: "voice",
    language: input.language,
    capturedAt: input.capturedAt,
    consentConfirmedAt: input.consentConfirmedAt,
    audio: input.audio,
    originalText: input.transcript,
    initialMachineTranslationEn: english ? null : input.translationEn,
    initialTranslationEngine: english ? null : input.engine,
    machineTranslationEn: english ? null : input.translationEn,
    translationEngine: english ? null : input.engine,
    currentOriginal: input.transcript,
    currentEnglish: english ? input.transcript : input.translationEn,
    englishSource: input.transcript,
    translationStatus: english ? "not_required" : "machine",
  };
}

/** A typed draft whose original is still being written before translation. */
export function setTypedOriginalBeforeReview(draft: CaptureDraft, text: string): CaptureDraft {
  return draft.language === "en"
    ? { ...draft, originalText: text, currentOriginal: text, currentEnglish: text, englishSource: text }
    : { ...draft, originalText: text, currentOriginal: text };
}

export function applyMachineTranslation(draft: CaptureDraft, english: string, engine: string): CaptureDraft {
  if (draft.language === "en") return draft;
  return {
    ...draft,
    initialMachineTranslationEn: draft.initialMachineTranslationEn ?? english,
    initialTranslationEngine: draft.initialTranslationEngine ?? engine,
    machineTranslationEn: english,
    translationEngine: engine,
    currentEnglish: english,
    englishSource: draft.currentOriginal,
    translationStatus: "machine",
  };
}

export function editOriginal(draft: CaptureDraft, text: string): CaptureDraft {
  if (draft.language === "en") {
    return { ...draft, currentOriginal: text, currentEnglish: text, englishSource: text, translationStatus: "not_required" };
  }
  const next = { ...draft, currentOriginal: text };
  if (draft.englishSource === null) return next; // no English yet: stays "missing"
  if (same(text, draft.englishSource)) {
    // Edited back to exactly what was translated: the English matches again.
    const machine = draft.machineTranslationEn !== null && same(draft.currentEnglish, draft.machineTranslationEn);
    return { ...next, translationStatus: machine ? "machine" : "manual" };
  }
  return { ...next, translationStatus: "stale" };
}

/** The ASHA typing/correcting the English is an explicit correction for the CURRENT original. */
export function editEnglish(draft: CaptureDraft, text: string): CaptureDraft {
  if (draft.language === "en") return editOriginal(draft, text);
  const isMachine =
    draft.machineTranslationEn !== null && same(text, draft.machineTranslationEn) && same(draft.currentOriginal, draft.englishSource);
  return {
    ...draft,
    currentEnglish: text,
    englishSource: draft.currentOriginal,
    translationStatus: text.trim() ? (isMachine ? "machine" : "manual") : "missing",
  };
}

export type ConfirmBlocker = "original_required" | "english_required" | "translation_stale" | "consent_required";

export function confirmBlocker(draft: CaptureDraft): ConfirmBlocker | null {
  if (!draft.currentOriginal.trim()) return "original_required";
  if (draft.inputSource === "voice" && !draft.consentConfirmedAt) return "consent_required";
  if (draft.translationStatus === "stale") return "translation_stale";
  if (draft.translationStatus === "missing" || !draft.currentEnglish.trim()) return "english_required";
  return null;
}

/** Shape of Core's ComplaintCaptureIn. Throws if the draft is not confirmable. */
export function buildCapturePayload(draft: CaptureDraft, confirmedAt: string): Record<string, unknown> {
  const blocker = confirmBlocker(draft);
  if (blocker) throw new Error(`capture_not_confirmable:${blocker}`);
  const english = draft.language === "en";
  return {
    client_capture_id: draft.clientCaptureId,
    input_source: draft.inputSource,
    language: draft.language,
    original_text: draft.originalText,
    initial_machine_translation_en: english ? null : draft.initialMachineTranslationEn,
    initial_translation_engine: english ? null : draft.initialTranslationEngine,
    machine_translation_en: english ? null : draft.machineTranslationEn,
    translation_engine: english ? null : draft.translationEngine,
    translation_status: english ? "not_required" : draft.translationStatus,
    confirmed_original_text: draft.currentOriginal.trim(),
    confirmed_text_en: (english ? draft.currentOriginal : draft.currentEnglish).trim(),
    captured_at: draft.capturedAt,
    confirmed_at: confirmedAt,
    consent_confirmed_at: draft.inputSource === "voice" ? draft.consentConfirmedAt : null,
    audio_sha256: draft.audio?.sha256 ?? null,
    audio_duration_seconds: draft.audio?.durationSeconds ?? null,
    audio_mime_type: draft.audio?.mimeType ?? null,
  };
}

/** The only text that may be sent to structured extraction. */
export function confirmedEnglish(draft: CaptureDraft): string {
  const blocker = confirmBlocker(draft);
  if (blocker) throw new Error(`capture_not_confirmable:${blocker}`);
  return (draft.language === "en" ? draft.currentOriginal : draft.currentEnglish).trim();
}
