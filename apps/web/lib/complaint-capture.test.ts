import { describe, expect, it } from "vitest";
import {
  applyMachineTranslation,
  buildCapturePayload,
  confirmBlocker,
  confirmedEnglish,
  createTypedDraft,
  createVoiceDraft,
  editEnglish,
  editOriginal,
} from "./complaint-capture";

const T0 = "2026-09-15T10:00:00.000Z";
const T1 = "2026-09-15T10:02:00.000Z";

describe("typed non-English capture", () => {
  it("cannot be confirmed until English exists, then carries the machine translation", () => {
    let d = createTypedDraft("cap-00000001", "hi", "बच्चे को तीन दिन से बुखार है", T0);
    expect(d.translationStatus).toBe("missing");
    expect(confirmBlocker(d)).toBe("english_required");

    d = applyMachineTranslation(d, "The child has had fever for three days", "argostranslate 1.11.0");
    expect(confirmBlocker(d)).toBeNull();
    expect(confirmedEnglish(d)).toBe("The child has had fever for three days");

    const payload = buildCapturePayload(d, T1);
    expect(payload).toMatchObject({
      language: "hi",
      input_source: "typed",
      translation_status: "machine",
      original_text: "बच्चे को तीन दिन से बुखार है",
      confirmed_original_text: "बच्चे को तीन दिन से बुखार है",
      machine_translation_en: "The child has had fever for three days",
      confirmed_text_en: "The child has had fever for three days",
      audio_sha256: null,
      consent_confirmed_at: null,
    });
  });

  it("marks the English stale when the original is corrected, and blocks extraction", () => {
    let d = createTypedDraft("cap-00000002", "hi", "तीन दिन से बुखार", T0);
    d = applyMachineTranslation(d, "fever for three days", "argostranslate 1.11.0");
    d = editOriginal(d, "सात दिन से बुखार");
    expect(d.translationStatus).toBe("stale");
    expect(confirmBlocker(d)).toBe("translation_stale");
    expect(() => confirmedEnglish(d)).toThrow(/translation_stale/);
    expect(() => buildCapturePayload(d, T1)).toThrow(/translation_stale/);
  });

  it("retranslation clears staleness and keeps the first captured original", () => {
    let d = createTypedDraft("cap-00000003", "hi", "तीन दिन से बुखार", T0);
    d = applyMachineTranslation(d, "fever for three days", "argostranslate 1.11.0");
    d = editOriginal(d, "सात दिन से बुखार");
    d = applyMachineTranslation(d, "fever for seven days", "argostranslate 1.11.0");
    expect(confirmBlocker(d)).toBeNull();
    const payload = buildCapturePayload(d, T1);
    expect(payload.original_text).toBe("तीन दिन से बुखार");
    expect(payload.confirmed_original_text).toBe("सात दिन से बुखार");
    expect(payload.confirmed_text_en).toBe("fever for seven days");
    expect(payload.translation_status).toBe("machine");
  });

  it("an explicit English correction after a stale edit is recorded as manual", () => {
    let d = createTypedDraft("cap-00000004", "hi", "तीन दिन से बुखार", T0);
    d = applyMachineTranslation(d, "fever for three days", "argostranslate 1.11.0");
    d = editOriginal(d, "सात दिन से बुखार");
    d = editEnglish(d, "fever for seven days");
    expect(d.translationStatus).toBe("manual");
    expect(buildCapturePayload(d, T1)).toMatchObject({ translation_status: "manual", machine_translation_en: "fever for three days" });
  });

  it("editing the original back to what was translated restores the match", () => {
    let d = createTypedDraft("cap-00000005", "hi", "तीन दिन से बुखार", T0);
    d = applyMachineTranslation(d, "fever for three days", "argostranslate 1.11.0");
    d = editOriginal(d, "सात दिन से बुखार");
    d = editOriginal(d, "तीन दिन से बुखार");
    expect(d.translationStatus).toBe("machine");
  });

  it("a language without a translation package can proceed only with ASHA-typed English", () => {
    let d = createTypedDraft("cap-00000006", "pa", "ਬੱਚੇ ਨੂੰ ਬੁਖਾਰ ਹੈ", T0);
    expect(confirmBlocker(d)).toBe("english_required");
    d = editEnglish(d, "  ");
    expect(confirmBlocker(d)).toBe("english_required");
    d = editEnglish(d, "The child has fever");
    expect(buildCapturePayload(d, T1)).toMatchObject({ translation_status: "manual", machine_translation_en: null });
  });
});

describe("English capture", () => {
  it("needs no translation and sends the confirmed original as the English", () => {
    let d = createTypedDraft("cap-00000007", "en", "fever for 3 days", T0);
    d = editOriginal(d, "fever for 7 days");
    expect(d.translationStatus).toBe("not_required");
    expect(buildCapturePayload(d, T1)).toMatchObject({
      translation_status: "not_required",
      confirmed_text_en: "fever for 7 days",
      machine_translation_en: null,
      translation_engine: null,
    });
  });
});

describe("voice capture", () => {
  const audio = { sha256: "a".repeat(64), durationSeconds: 6.4, mimeType: "audio/webm;codecs=opus" };

  it("carries consent, audio metadata and Whisper provenance", () => {
    const d = createVoiceDraft({
      id: "cap-00000008",
      language: "ta",
      transcript: "குழந்தைக்கு காய்ச்சல்",
      translationEn: "The child has fever",
      engine: "faster-whisper small",
      audio,
      consentConfirmedAt: T0,
      capturedAt: T0,
    });
    expect(buildCapturePayload(d, T1)).toMatchObject({
      input_source: "voice",
      translation_status: "machine",
      translation_engine: "faster-whisper small",
      audio_sha256: audio.sha256,
      audio_duration_seconds: 6.4,
      consent_confirmed_at: T0,
    });
  });

  it("retranslating a corrected transcript keeps Whisper's first English in the record", () => {
    let d = createVoiceDraft({
      id: "cap-00000011",
      language: "hi",
      transcript: "बच्चे को खांसी है",
      translationEn: "The child has a cough",
      engine: "faster-whisper small",
      audio,
      consentConfirmedAt: T0,
      capturedAt: T0,
    });
    d = editOriginal(d, "बच्चे को खांसी और तेज़ सांस है");
    d = applyMachineTranslation(d, "The child has a cough and fast breathing", "argostranslate 1.11.0");
    expect(buildCapturePayload(d, T1)).toMatchObject({
      initial_machine_translation_en: "The child has a cough",
      initial_translation_engine: "faster-whisper small",
      machine_translation_en: "The child has a cough and fast breathing",
      translation_engine: "argostranslate 1.11.0",
      translation_status: "machine",
    });
  });

  it("a corrected transcript makes Whisper's English stale", () => {
    let d = createVoiceDraft({
      id: "cap-00000009",
      language: "hi",
      transcript: "बच्चे को खांसी है",
      translationEn: "The child has a cough",
      engine: "faster-whisper small",
      audio,
      consentConfirmedAt: T0,
      capturedAt: T0,
    });
    d = editOriginal(d, "बच्चे को खांसी और तेज़ सांस है");
    expect(confirmBlocker(d)).toBe("translation_stale");
  });

  it("refuses confirmation without recording consent", () => {
    const d = { ...createVoiceDraft({ id: "cap-00000010", language: "en", transcript: "cough", translationEn: "cough", engine: "faster-whisper small", audio, consentConfirmedAt: T0, capturedAt: T0 }), consentConfirmedAt: null };
    expect(confirmBlocker(d)).toBe("consent_required");
  });
});
