// The six languages the ASHA workflow offers. Selection is always explicit:
// nothing in this app detects a caregiver's language automatically.
// Pure module (no server imports) so client components can use it.
export const CAPTURE_LANGUAGES = ["en", "hi", "pa", "bn", "mr", "ta"] as const;
export type CaptureLanguage = (typeof CAPTURE_LANGUAGES)[number];

export const LANGUAGE_OPTIONS: ReadonlyArray<{ code: CaptureLanguage; nativeLabel: string; englishLabel: string }> = [
  { code: "en", nativeLabel: "English", englishLabel: "English" },
  { code: "hi", nativeLabel: "हिन्दी", englishLabel: "Hindi" },
  { code: "pa", nativeLabel: "ਪੰਜਾਬੀ", englishLabel: "Punjabi" },
  { code: "bn", nativeLabel: "বাংলা", englishLabel: "Bengali" },
  { code: "mr", nativeLabel: "मराठी", englishLabel: "Marathi" },
  { code: "ta", nativeLabel: "தமிழ்", englishLabel: "Tamil" },
];

export function isCaptureLanguage(value: unknown): value is CaptureLanguage {
  return typeof value === "string" && (CAPTURE_LANGUAGES as readonly string[]).includes(value);
}

export function languageLabel(code: CaptureLanguage): string {
  const option = LANGUAGE_OPTIONS.find((o) => o.code === code);
  return option ? (option.code === "en" ? option.nativeLabel : `${option.nativeLabel} (${option.englishLabel})`) : code;
}
