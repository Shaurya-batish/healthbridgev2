"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { clinicalText, uiText, type ClinicalText, type MessageFile, type ReviewStatus } from "./core";
import { CAPTURE_LANGUAGES, isCaptureLanguage, languageLabel, type CaptureLanguage } from "./languages";
import en from "./messages/en.json";
import hi from "./messages/hi.json";
import pa from "./messages/pa.json";
import bn from "./messages/bn.json";
import mr from "./messages/mr.json";
import ta from "./messages/ta.json";
import clinicalHi from "./clinical/hi.json";
import clinicalPa from "./clinical/pa.json";
import clinicalBn from "./clinical/bn.json";
import clinicalMr from "./clinical/mr.json";
import clinicalTa from "./clinical/ta.json";

export const UI_MESSAGES = { en, hi, pa, bn, mr, ta } as unknown as Record<CaptureLanguage, MessageFile>;
export const CLINICAL_MESSAGES = { hi: clinicalHi, pa: clinicalPa, bn: clinicalBn, mr: clinicalMr, ta: clinicalTa } as unknown as Partial<
  Record<CaptureLanguage, MessageFile>
>;

const STORAGE_KEY = "hb.ui_language";

interface I18nState {
  language: CaptureLanguage;
  setLanguage: (language: CaptureLanguage) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  clinical: (key: string, canonicalEnglish: string, vars?: Record<string, string | number>) => ClinicalText;
  uiReviewStatus: ReviewStatus;
  label: (language: CaptureLanguage) => string;
}

const I18nContext = createContext<I18nState | null>(null);

function initialLanguage(): CaptureLanguage {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isCaptureLanguage(stored)) return stored;
  } catch {
    /* storage blocked: fall through */
  }
  const browser = typeof navigator !== "undefined" ? navigator.language.slice(0, 2).toLowerCase() : "en";
  return (CAPTURE_LANGUAGES as readonly string[]).includes(browser) ? (browser as CaptureLanguage) : "en";
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  // Render English on the server and first paint; switch after mount so
  // hydration never mismatches.
  const [language, setLanguageState] = useState<CaptureLanguage>("en");

  useEffect(() => {
    setLanguageState(initialLanguage());
  }, []);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const setLanguage = useCallback((next: CaptureLanguage) => {
    setLanguageState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* not persisted; still applied for this session */
    }
  }, []);

  const value = useMemo<I18nState>(
    () => ({
      language,
      setLanguage,
      t: (key, vars) => uiText(UI_MESSAGES, language, key, vars),
      clinical: (key, canonical, vars) => clinicalText(CLINICAL_MESSAGES, language, key, canonical, vars),
      uiReviewStatus: UI_MESSAGES[language]._meta.review_status,
      label: languageLabel,
    }),
    [language, setLanguage],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nState {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within LanguageProvider");
  return ctx;
}
