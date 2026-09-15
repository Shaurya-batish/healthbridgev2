// Pure message lookup. Two resource families, deliberately separate:
//
//  - UI messages (lib/i18n/messages/<lang>.json): buttons, states, errors.
//    Non-English files are marked "unreviewed_draft" until a native speaker
//    reviews them; the UI says so.
//  - Clinical messages (lib/i18n/clinical/<lang>.json): severity headings,
//    instructions and IMNCI rule explanations. A translation is only shown
//    when its file is marked "reviewed" AND the key exists. Otherwise the
//    canonical English text is shown with an explicit notice. Clinical text
//    is never machine translated at runtime.
import type { CaptureLanguage } from "./languages";

export type ReviewStatus = "source" | "reviewed" | "unreviewed_draft" | "not_available";

export interface MessageFile {
  _meta: { language: string; review_status: ReviewStatus; reviewed_by: string | null; notes?: string };
  messages: Record<string, string>;
}

export function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (name in vars ? String(vars[name]) : match));
}

/** UI text: selected language when present, else English. Never throws on a missing key. */
export function uiText(
  files: Partial<Record<CaptureLanguage, MessageFile>>,
  language: CaptureLanguage,
  key: string,
  vars?: Record<string, string | number>,
): string {
  const own = files[language]?.messages[key];
  const english = files.en?.messages[key];
  return interpolate(own ?? english ?? key, vars);
}

export interface ClinicalText {
  text: string;
  /** true when the English canonical text is shown because no reviewed translation exists */
  fallback: boolean;
}

export function clinicalText(
  files: Partial<Record<CaptureLanguage, MessageFile>>,
  language: CaptureLanguage,
  key: string,
  canonicalEnglish: string,
  vars?: Record<string, string | number>,
): ClinicalText {
  if (language === "en") return { text: interpolate(canonicalEnglish, vars), fallback: false };
  const file = files[language];
  const translated = file?._meta.review_status === "reviewed" ? file.messages[key] : undefined;
  if (translated) return { text: interpolate(translated, vars), fallback: false };
  return { text: interpolate(canonicalEnglish, vars), fallback: true };
}
