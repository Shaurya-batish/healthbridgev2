// Recording limits shared by the browser recorder, the offline voice queue
// and the gateway. The AI service re-checks duration after really decoding
// the audio (services/ai/app/transcribe.py) -- these client checks are for
// fast, plain-language feedback, not the security boundary.
export const AUDIO_MIN_SECONDS = 1;
export const AUDIO_MAX_SECONDS = 120;
export const AUDIO_MAX_BYTES = 8 * 1024 * 1024;
/** base64 inflates by 4/3; the gateway refuses anything larger before forwarding. */
export const AUDIO_MAX_BASE64_CHARS = Math.ceil((AUDIO_MAX_BYTES * 4) / 3) + 4;

export const ALLOWED_AUDIO_MIME_TYPES = ["audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"] as const;

/** In preference order; the first the browser supports is used. */
export const RECORDER_MIME_PREFERENCE = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

export function baseMimeType(mimeType: string): string {
  return mimeType.split(";")[0].trim().toLowerCase();
}

export function isAllowedAudioMime(mimeType: unknown): mimeType is string {
  return typeof mimeType === "string" && mimeType.length <= 100 && (ALLOWED_AUDIO_MIME_TYPES as readonly string[]).includes(baseMimeType(mimeType));
}

export function pickRecorderMimeType(isTypeSupported: ((type: string) => boolean) | undefined): string | null {
  if (!isTypeSupported) return null;
  return RECORDER_MIME_PREFERENCE.find((type) => isTypeSupported(type)) ?? null;
}

export type RecordingProblem = "empty" | "too_short" | "too_long" | "too_large" | "unsupported_format";

export function validateRecording(input: { bytes: number; durationSeconds: number; mimeType: string }): RecordingProblem | null {
  if (!isAllowedAudioMime(input.mimeType)) return "unsupported_format";
  if (input.bytes <= 0) return "empty";
  if (input.bytes > AUDIO_MAX_BYTES) return "too_large";
  if (input.durationSeconds < AUDIO_MIN_SECONDS) return "too_short";
  // A small tolerance: the recorder auto-stops at the limit, and timer ticks
  // can land a fraction of a second past it.
  if (input.durationSeconds > AUDIO_MAX_SECONDS + 1) return "too_long";
  return null;
}
