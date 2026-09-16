import { describe, expect, it } from "vitest";
import { clinicalText, interpolate, uiText, type MessageFile } from "./core";
import { CAPTURE_LANGUAGES } from "./languages";
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

const UI = { en, hi, pa, bn, mr, ta } as unknown as Record<string, MessageFile>;
const CLINICAL = { hi: clinicalHi, pa: clinicalPa, bn: clinicalBn, mr: clinicalMr, ta: clinicalTa } as unknown as Record<string, MessageFile>;

describe("UI message lookup", () => {
  const files = {
    en: { _meta: { language: "en", review_status: "source", reviewed_by: null }, messages: { a: "Hello {name}", b: "Only English" } },
    hi: { _meta: { language: "hi", review_status: "unreviewed_draft", reviewed_by: null }, messages: { a: "नमस्ते {name}" } },
  } as const;

  it("uses the selected language, falls back to English, then to the key", () => {
    expect(uiText(files, "hi", "a", { name: "Asha" })).toBe("नमस्ते Asha");
    expect(uiText(files, "hi", "b")).toBe("Only English");
    expect(uiText(files, "hi", "missing.key")).toBe("missing.key");
  });

  it("leaves unknown placeholders visible rather than silently dropping them", () => {
    expect(interpolate("{a} and {b}", { a: 1 })).toBe("1 and {b}");
  });
});

describe("clinical text is never shown from an unreviewed translation", () => {
  const unreviewed = { hi: { _meta: { language: "hi", review_status: "unreviewed_draft", reviewed_by: null }, messages: { "rule.GDS-03": "दौरे" } } } as const;
  const reviewed = { hi: { _meta: { language: "hi", review_status: "reviewed", reviewed_by: "Dr X, 2026-10-01" }, messages: { "rule.GDS-03": "दौरे" } } } as const;

  it("falls back to canonical English with a flag when not reviewed", () => {
    expect(clinicalText(unreviewed, "hi", "rule.GDS-03", "Convulsions")).toEqual({ text: "Convulsions", fallback: true });
    expect(clinicalText({}, "ta", "rule.GDS-03", "Convulsions")).toEqual({ text: "Convulsions", fallback: true });
  });

  it("shows a reviewed translation, and English needs no fallback", () => {
    expect(clinicalText(reviewed, "hi", "rule.GDS-03", "Convulsions")).toEqual({ text: "दौरे", fallback: false });
    expect(clinicalText(unreviewed, "en", "rule.GDS-03", "Convulsions")).toEqual({ text: "Convulsions", fallback: false });
  });
});

describe("shipped resource files", () => {
  const englishKeys = Object.keys(en.messages).sort();

  it("every UI language file exists, covers every English key, and non-English files are honestly marked", () => {
    for (const code of CAPTURE_LANGUAGES) {
      const file = UI[code];
      expect(file, code).toBeDefined();
      expect(Object.keys(file.messages).sort(), code).toEqual(englishKeys);
      if (code !== "en") expect(file._meta.review_status, code).toBe("unreviewed_draft");
    }
  });

  it("placeholders in translations match the English source", () => {
    const vars = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();
    for (const code of CAPTURE_LANGUAGES) {
      for (const key of englishKeys) {
        expect(vars(UI[code].messages[key]), `${code}:${key}`).toEqual(vars((en.messages as Record<string, string>)[key]));
      }
    }
  });

  it("no clinical file claims review without a named reviewer", () => {
    for (const [code, file] of Object.entries(CLINICAL)) {
      if (file._meta.review_status === "reviewed") expect(file._meta.reviewed_by, code).toBeTruthy();
      else expect(file._meta.review_status, code).toBe("not_available");
    }
  });
});
