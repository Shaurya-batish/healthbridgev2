"use client";

import { confirmBlocker, type CaptureDraft } from "@/lib/complaint-capture";
import { useI18n } from "@/lib/i18n/LanguageProvider";
import { languageLabel } from "@/lib/i18n/languages";
import { AshaButton } from "@/components/asha/AshaButton";
import { IconAlertTriangle, IconClipboardPulse } from "@/components/asha/icons";

/** Original + English side by side, both editable. Confirmation is blocked
 * while the English is missing or stale (see lib/complaint-capture.ts). */
export function ComplaintReview({
  draft,
  onOriginalChange,
  onEnglishChange,
  onRetranslate,
  retranslating,
  onConfirm,
  canAnalyze,
  transcriptWarnings = [],
  translationWarnings = [],
}: {
  transcriptWarnings?: string[];
  translationWarnings?: string[];
  draft: CaptureDraft;
  onOriginalChange: (text: string) => void;
  onEnglishChange: (text: string) => void;
  onRetranslate: (() => void) | null;
  retranslating: boolean;
  onConfirm: () => void;
  canAnalyze: boolean;
}) {
  const { t } = useI18n();
  const english = draft.language === "en";
  const blocker = confirmBlocker(draft);

  const status =
    draft.translationStatus === "stale"
      ? { tone: "border-amber-400 bg-amber-50 text-amber-900", text: t("review.statusStale") }
      : draft.translationStatus === "machine"
        ? { tone: "border-sky-300 bg-sky-50 text-sky-900", text: t("review.statusMachine", { engine: draft.translationEngine ?? "" }) }
        : draft.translationStatus === "manual"
          ? { tone: "border-slate-300 bg-slate-50 text-slate-700", text: t("review.statusManual") }
          : draft.translationStatus === "missing"
            ? { tone: "border-amber-300 bg-amber-50 text-amber-900", text: t("review.statusMissing") }
            : null;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-xl font-bold text-slate-800">{t("review.title")}</h2>

      {transcriptWarnings.length > 0 && (
        <p className="mt-3 flex items-start gap-2 rounded-lg border border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="alert">
          <IconAlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          {t("review.transcriptSuspect")}
        </p>
      )}

      <label className="mt-4 block">
        <span className="text-base font-semibold text-slate-700">{t("review.original", { language: languageLabel(draft.language) })}</span>
        <textarea
          lang={draft.language}
          value={draft.currentOriginal}
          onChange={(e) => onOriginalChange(e.target.value)}
          rows={4}
          className="mt-1.5 w-full rounded-xl border-2 border-slate-300 px-4 py-3 text-lg"
        />
        <span className="mt-1 block text-sm text-slate-500">{t("review.originalHint")}</span>
      </label>

      {!english && (
        <div className="mt-4">
          <label className="block">
            <span className="text-base font-semibold text-slate-700">{t("review.english")}</span>
            <textarea
              lang="en"
              value={draft.currentEnglish}
              onChange={(e) => onEnglishChange(e.target.value)}
              rows={4}
              aria-invalid={draft.translationStatus === "stale"}
              className={`mt-1.5 w-full rounded-xl border-2 px-4 py-3 text-lg ${
                draft.translationStatus === "stale" ? "border-amber-500" : "border-slate-300"
              }`}
            />
          </label>
          {status && (
            <p className={`mt-2 rounded-lg border px-3 py-2 text-sm ${status.tone}`} role={draft.translationStatus === "stale" ? "alert" : undefined}>
              {status.text}
            </p>
          )}
          {translationWarnings.length > 0 && draft.translationStatus === "machine" && (
            <p className="mt-2 rounded-lg border border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="alert">
              {t("review.translationSuspect")}
            </p>
          )}
          {onRetranslate && (
            <div className="mt-3">
              <AshaButton onClick={onRetranslate} variant="outline" disabled={retranslating}>
                {retranslating ? t("capture.translating") : t("review.retranslate")}
              </AshaButton>
            </div>
          )}
        </div>
      )}

      <p className="mt-3 text-sm text-slate-500">{t("review.firstCaptured")}</p>

      {blocker && (
        <p className="mt-3 flex items-start gap-2 text-base text-amber-900">
          <IconAlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          {t(`review.blocked.${blocker}`)}
        </p>
      )}

      <div className="mt-4">
        <AshaButton onClick={onConfirm} disabled={!!blocker || !canAnalyze} icon={<IconClipboardPulse />}>
          {t("review.confirm")}
        </AshaButton>
      </div>
    </div>
  );
}
