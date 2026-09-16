"use client";

import { useI18n } from "@/lib/i18n/LanguageProvider";
import { languageLabel } from "@/lib/i18n/languages";
import { AshaButton } from "@/components/asha/AshaButton";
import { IconAlertTriangle, IconArrowRight, IconCheckCircle } from "@/components/asha/icons";
import type { Severity, TriageResult, TriageSource } from "@/lib/types";

// Canonical English clinical text. Translations are only shown from reviewed
// resources (lib/i18n/clinical); severity and rule ids are never translated.
const SEVERITY_UI: Record<Severity, { header: string; subtext: string; action: string; tone: string; Icon: typeof IconAlertTriangle }> = {
  RED: {
    header: "URGENT",
    subtext: "Doctor needs to see this patient right away.",
    action: "Move patient to priority queue.",
    tone: "border-severity-red bg-severity-red-bg text-severity-red",
    Icon: IconAlertTriangle,
  },
  YELLOW: {
    header: "NEEDS ATTENTION",
    subtext: "This patient should be seen soon.",
    action: "Patient added to the queue for review.",
    tone: "border-severity-yellow bg-severity-yellow-bg text-severity-yellow",
    Icon: IconAlertTriangle,
  },
  GREEN: {
    header: "NO DANGER SIGN DETECTED",
    subtext: "No urgent signs found right now.",
    action: "Patient added to the queue as routine.",
    tone: "border-severity-green bg-severity-green-bg text-severity-green",
    Icon: IconCheckCircle,
  },
};

export function TriageResultCard({ result, source, onConfirm }: { result: TriageResult; source: TriageSource; onConfirm: () => void }) {
  const { t, clinical, language } = useI18n();
  const ui = SEVERITY_UI[result.severity];
  const header = clinical(`severity.${result.severity}.header`, ui.header);
  const subtext = clinical(`severity.${result.severity}.subtext`, ui.subtext);
  const action = clinical(`severity.${result.severity}.action`, ui.action);
  const reason = clinical(`rule.${result.rule_id}`, result.matched_description);
  const fallback = [header, subtext, action, reason].some((c) => c.fallback);

  return (
    <div className={`space-y-4 rounded-2xl border-2 p-5 ${ui.tone}`}>
      <div className="flex items-center gap-3">
        <ui.Icon className="h-9 w-9 shrink-0" />
        <div>
          <h2 className="text-2xl font-extrabold tracking-wide" lang={header.fallback ? "en" : language}>
            {header.text}
          </h2>
          <p className="text-base font-medium" lang={subtext.fallback ? "en" : language}>
            {subtext.text}
          </p>
        </div>
      </div>

      {fallback && language !== "en" && (
        <p className="rounded-lg bg-white/70 px-3 py-2 text-sm text-slate-700">{t("result.clinicalFallback", { language: languageLabel(language) })}</p>
      )}

      <div className="rounded-xl bg-white/60 p-4 text-slate-800">
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">{t("result.reason")}</p>
        <p className="mt-1 text-lg" lang={reason.fallback ? "en" : language}>
          {reason.text}
        </p>
        <p className="mt-1 font-mono text-xs text-slate-500">{t("result.rule", { ruleId: result.rule_id, version: result.rule_version })}</p>
      </div>

      <div className="rounded-xl bg-white/60 p-4 text-slate-800">
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">{t("result.action")}</p>
        <p className="mt-1 text-lg" lang={action.fallback ? "en" : language}>
          {action.text}
        </p>
      </div>

      <p className="text-sm opacity-75">{source === "llm" ? t("result.sourceLlm") : t("result.sourceChecklist")}</p>

      <AshaButton onClick={onConfirm} variant="primary" icon={<IconArrowRight />}>
        {t("result.confirmSave")}
      </AshaButton>
    </div>
  );
}
