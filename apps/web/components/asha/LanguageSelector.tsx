"use client";

import { LANGUAGE_OPTIONS, type CaptureLanguage } from "@/lib/i18n/languages";

/** Explicit language choice with native-script labels. Never auto-detects. */
export function LanguageSelector({
  id,
  label,
  help,
  value,
  onChange,
  disabled,
  compact,
}: {
  id: string;
  label: string;
  help?: string;
  value: CaptureLanguage;
  onChange: (language: CaptureLanguage) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "flex items-center gap-2" : "block"}>
      <label htmlFor={id} className={compact ? "text-sm font-medium text-slate-600" : "text-base font-semibold text-slate-700"}>
        {label}
      </label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        aria-describedby={help ? `${id}-help` : undefined}
        onChange={(e) => onChange(e.target.value as CaptureLanguage)}
        className={
          compact
            ? "min-h-[44px] rounded-lg border border-slate-300 bg-white px-2 text-base"
            : "mt-1.5 min-h-[52px] w-full rounded-xl border-2 border-slate-300 bg-white px-3 text-lg disabled:bg-slate-100"
        }
      >
        {LANGUAGE_OPTIONS.map((option) => (
          <option key={option.code} value={option.code} lang={option.code}>
            {option.code === "en" ? option.nativeLabel : `${option.nativeLabel} — ${option.englishLabel}`}
          </option>
        ))}
      </select>
      {help && !compact && (
        <p id={`${id}-help`} className="mt-1 text-sm text-slate-500">
          {help}
        </p>
      )}
    </div>
  );
}
