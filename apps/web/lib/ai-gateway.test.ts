import { describe, expect, it, vi } from "vitest";
import { UpstreamError } from "./api-client";
import { aiStatus, extractViaAi, transcribeViaAi, translateViaAi, type AiCall } from "./ai-gateway";
import { evaluateTriage } from "./rules-engine";

// What fetch actually does when nothing is listening on AI_SERVICE_URL
// (service stopped, or the laptop's tunnel closed).
const serviceStopped: AiCall = async () => {
  throw new TypeError("fetch failed: connect ECONNREFUSED 127.0.0.1:8100");
};
const upstream = (status: number, detail: unknown): AiCall => async () => {
  throw new UpstreamError(status, { detail });
};

function sentBody(call: ReturnType<typeof vi.fn<AiCall>>, index = 0): unknown {
  return JSON.parse(call.mock.calls[index][1]!.body as string);
}

const AUDIO = { audio_base64: "ZmFrZQ==", mime_type: "audio/webm;codecs=opus" };

describe("AI service stopped entirely", () => {
  it("extract returns a clean ai_unavailable signal, never throws", async () => {
    await expect(extractViaAi({ complaint_text: "fever 3 days", age_months: 24 }, serviceStopped)).resolves.toEqual({
      ai_unavailable: true,
    });
  });

  it("transcribe reports unavailable (not a raw error)", async () => {
    await expect(transcribeViaAi({ ...AUDIO, language: "hi" }, serviceStopped)).resolves.toEqual({
      transcription_unavailable: true,
      reason: "unavailable",
    });
  });

  it("translate reports unavailable (not a raw error)", async () => {
    await expect(translateViaAi({ text: "बुखार", source_language: "hi" }, serviceStopped)).resolves.toEqual({
      translation_unavailable: true,
      reason: "unavailable",
    });
  });

  it("status reports everything false", async () => {
    await expect(aiStatus(serviceStopped)).resolves.toEqual({
      ai_reachable: false,
      ai_mode: null,
      whisper_available: false,
      ollama_reachable: false,
      translation_languages: [],
    });
  });

  it("the checklist fallback still reaches a rule-table severity with no AI at all", () => {
    const result = evaluateTriage({ convulsions: true, age_months: 18 });
    expect(result.severity).toBe("RED");
    expect(result.rule_id).toBe("GDS-03");
  });
});

describe("AI_MODE=degraded and tunnel auth failures", () => {
  it("extract 503 maps to ai_unavailable", async () => {
    await expect(extractViaAi({ complaint_text: "fever" }, upstream(503, "ai_unavailable"))).resolves.toEqual({ ai_unavailable: true });
  });

  it("transcribe 503 maps to unavailable", async () => {
    const out = await transcribeViaAi({ ...AUDIO, language: "ta" }, upstream(503, "transcription_unavailable"));
    expect(out).toEqual({ transcription_unavailable: true, reason: "unavailable" });
  });

  it("a 401 from a mis-keyed tunnel degrades the same way", async () => {
    const out = await transcribeViaAi({ ...AUDIO, language: "hi" }, upstream(401, "invalid_ai_key"));
    expect(out).toEqual({ transcription_unavailable: true, reason: "unavailable" });
  });

  it("status passes the truthful health flags and only known translation languages through", async () => {
    const call: AiCall = async () => ({
      ai_mode: "degraded",
      whisper_available: false,
      ollama_reachable: false,
      translation_languages: ["hi", "bn", "xx"],
    });
    await expect(aiStatus(call)).resolves.toEqual({
      ai_reachable: true,
      ai_mode: "degraded",
      whisper_available: false,
      ollama_reachable: false,
      translation_languages: ["hi", "bn"],
    });
  });
});

describe("extractViaAi", () => {
  it("passes a real rule decision through and sends only English text + age (never language or audio)", async () => {
    const decision = { severity: "RED", rule_id: "GDS-03", rule_version: "v1", extracted_facts: { convulsions: true } };
    const call = vi.fn<AiCall>(async () => decision);
    const out = await extractViaAi({ complaint_text: "fits", language: "hi", age_months: 12, audio_base64: "ZmFrZQ==" }, call);
    expect(out).toEqual(decision);
    expect(sentBody(call)).toEqual({ complaint_text: "fits", age_months: 12 });
  });

  it("drops a body without a valid severity", async () => {
    await expect(extractViaAi({ complaint_text: "x" }, async () => ({ severity: "PURPLE", rule_id: "X" }))).resolves.toEqual({
      ai_unavailable: true,
    });
  });

  it("refuses blank, oversized and non-object input without calling the AI", async () => {
    const call = vi.fn<AiCall>();
    for (const bad of [null, "text", { complaint_text: "   " }, { complaint_text: "a".repeat(200_000) }]) {
      await expect(extractViaAi(bad, call)).resolves.toEqual({ ai_unavailable: true });
    }
    expect(call).not.toHaveBeenCalled();
  });
});

describe("transcribeViaAi", () => {
  it("returns original transcript + English translation + provenance and never a severity", async () => {
    const out = await transcribeViaAi({ ...AUDIO, language: "hi" }, async () => ({
      transcript: "बुखार है",
      translation_en: "has fever",
      language: "hi",
      engine: "faster-whisper",
      model: "small",
      duration_seconds: 3.2,
      transcript_warnings: ["repetitive_output", "not_a_known_warning"],
      severity: "RED",
    }));
    expect(out).toEqual({
      transcript: "बुखार है",
      translation_en: "has fever",
      language: "hi",
      engine: "faster-whisper",
      model: "small",
      duration_seconds: 3.2,
      transcript_warnings: ["repetitive_output"],
      translation_warnings: [],
    });
  });

  it("requires a supported language, allowed format, and non-empty bounded audio -- server side", async () => {
    const call = vi.fn<AiCall>();
    for (const bad of [
      { ...AUDIO },
      { ...AUDIO, language: "xx" },
      { ...AUDIO, audio_base64: "", language: "hi" },
      { ...AUDIO, audio_base64: "a".repeat(12_000_000), language: "hi" },
    ]) {
      await expect(transcribeViaAi(bad, call)).resolves.toEqual({ transcription_unavailable: true, reason: "invalid_request" });
    }
    for (const mime of [undefined, "video/x-matroska", "text/plain"]) {
      await expect(transcribeViaAi({ audio_base64: "ZmFrZQ==", language: "hi", mime_type: mime }, call)).resolves.toEqual({
        transcription_unavailable: true,
        reason: "unsupported_format",
      });
    }
    expect(call).not.toHaveBeenCalled();
  });

  it("forwards the language and format to the AI service", async () => {
    const call = vi.fn<AiCall>(async () => ({ transcript: "ਬੁਖਾਰ", translation_en: "fever" }));
    await transcribeViaAi({ ...AUDIO, language: "pa" }, call);
    expect(sentBody(call)).toEqual({ audio_base64: "ZmFrZQ==", language: "pa", mime_type: "audio/webm;codecs=opus" });
  });

  it("distinguishes validation failures from Whisper being unavailable", async () => {
    const cases: Array<[string, string]> = [
      ["empty_transcript", "empty"],
      ["invalid_audio", "invalid_audio"],
      ["audio_too_short", "too_short"],
      ["audio_too_long", "too_long"],
      ["unsupported_audio_format", "unsupported_format"],
      ["something_else", "invalid_request"],
    ];
    for (const [detail, reason] of cases) {
      await expect(transcribeViaAi({ ...AUDIO, language: "en" }, upstream(422, detail))).resolves.toEqual({
        transcription_unavailable: true,
        reason,
      });
    }
    await expect(transcribeViaAi({ ...AUDIO, language: "en" }, async () => ({ transcript: "x", translation_en: " " }))).resolves.toEqual({
      transcription_unavailable: true,
      reason: "empty",
    });
  });
});

describe("translateViaAi", () => {
  it("returns labelled machine English and forwards only text + source language", async () => {
    const call = vi.fn<AiCall>(async () => ({ translation_en: "the child has fever", engine: "argostranslate", engine_version: "1.11.0", severity: "RED" }));
    const out = await translateViaAi({ text: "बच्चे को बुखार है", source_language: "hi", age_months: 3 }, call);
    expect(out).toEqual({ translation_en: "the child has fever", source_language: "hi", engine: "argostranslate", engine_version: "1.11.0" });
    expect(sentBody(call)).toEqual({ text: "बच्चे को बुखार है", source_language: "hi" });
  });

  it("reports a missing language package honestly", async () => {
    await expect(
      translateViaAi({ text: "ਬੁਖਾਰ", source_language: "pa" }, upstream(503, { code: "translation_unavailable", reason: "language_not_installed" })),
    ).resolves.toEqual({ translation_unavailable: true, reason: "language_not_installed" });
  });

  it("refuses English, blank, oversized and unknown-language input without calling the AI", async () => {
    const call = vi.fn<AiCall>();
    for (const bad of [
      { text: "fever", source_language: "en" },
      { text: "  ", source_language: "hi" },
      { text: "a".repeat(4001), source_language: "hi" },
      { text: "x", source_language: "fr" },
      null,
    ]) {
      await expect(translateViaAi(bad, call)).resolves.toEqual({ translation_unavailable: true, reason: "invalid_request" });
    }
    expect(call).not.toHaveBeenCalled();
  });
});
