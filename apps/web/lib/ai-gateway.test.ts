import { describe, expect, it, vi } from "vitest";
import { UpstreamError } from "./api-client";
import { aiStatus, extractViaAi, transcribeViaAi, type AiCall } from "./ai-gateway";
import { evaluateTriage } from "./rules-engine";

// What fetch actually does when nothing is listening on AI_SERVICE_URL
// (service stopped, or the laptop's tunnel closed).
const serviceStopped: AiCall = async () => {
  throw new TypeError("fetch failed: connect ECONNREFUSED 127.0.0.1:8100");
};
const upstream = (status: number, detail: string): AiCall => async () => {
  throw new UpstreamError(status, { detail });
};

function sentBody(call: ReturnType<typeof vi.fn<AiCall>>, index = 0): unknown {
  return JSON.parse(call.mock.calls[index][1]!.body as string);
}

describe("AI service stopped entirely", () => {
  it("extract returns a clean ai_unavailable signal, never throws", async () => {
    await expect(extractViaAi({ complaint_text: "fever 3 days", age_months: 24 }, serviceStopped)).resolves.toEqual({
      ai_unavailable: true,
    });
  });

  it("transcribe reports unavailable (not a raw error)", async () => {
    await expect(transcribeViaAi({ audio_base64: "ZmFrZQ==", language: "hi" }, serviceStopped)).resolves.toEqual({
      transcription_unavailable: true,
      reason: "unavailable",
    });
  });

  it("status reports everything false", async () => {
    await expect(aiStatus(serviceStopped)).resolves.toEqual({
      ai_reachable: false,
      ai_mode: null,
      whisper_available: false,
      ollama_reachable: false,
    });
  });

  it("the checklist fallback still reaches a rule-table severity with no AI at all", () => {
    // The safety property: the path the client falls back to is the same
    // versioned rule table, evaluated on-device.
    const result = evaluateTriage({ convulsions: true, age_months: 18 });
    expect(result.severity).toBe("RED");
    expect(result.rule_id).toBe("GDS-03");
  });
});

describe("AI_MODE=degraded and tunnel auth failures", () => {
  it("extract 503 maps to ai_unavailable", async () => {
    await expect(extractViaAi({ complaint_text: "fever" }, upstream(503, "ai_unavailable"))).resolves.toEqual({
      ai_unavailable: true,
    });
  });

  it("transcribe 503 maps to unavailable", async () => {
    const out = await transcribeViaAi({ audio_base64: "ZmFrZQ==", language: "ta" }, upstream(503, "transcription_unavailable"));
    expect(out).toEqual({ transcription_unavailable: true, reason: "unavailable" });
  });

  it("a 401 from a mis-keyed tunnel degrades the same way", async () => {
    const out = await transcribeViaAi({ audio_base64: "ZmFrZQ==", language: "hi" }, upstream(401, "invalid_ai_key"));
    expect(out).toEqual({ transcription_unavailable: true, reason: "unavailable" });
  });

  it("status passes the truthful health flags through", async () => {
    const call: AiCall = async () => ({ ai_mode: "degraded", whisper_available: false, ollama_reachable: false });
    await expect(aiStatus(call)).resolves.toEqual({
      ai_reachable: true,
      ai_mode: "degraded",
      whisper_available: false,
      ollama_reachable: false,
    });
  });
});

describe("extractViaAi", () => {
  it("passes a real rule decision through and sends only English text + age", async () => {
    const decision = { severity: "RED", rule_id: "GDS-03", rule_version: "v1", extracted_facts: { convulsions: true } };
    const call = vi.fn<AiCall>(async () => decision);
    const out = await extractViaAi({ complaint_text: "fits", language: "hi", age_months: 12 }, call);
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
  it("returns original transcript + English translation and never a severity", async () => {
    const out = await transcribeViaAi({ audio_base64: "ZmFrZQ==", language: "hi" }, async () => ({
      transcript: "बुखार है",
      translation_en: "has fever",
      language: "hi",
      severity: "RED",
    }));
    expect(out).toEqual({ transcript: "बुखार है", translation_en: "has fever", language: "hi" });
  });

  it("requires a supported language and non-empty, bounded audio", async () => {
    const call = vi.fn<AiCall>();
    for (const bad of [
      { audio_base64: "ZmFrZQ==" },
      { audio_base64: "ZmFrZQ==", language: "xx" },
      { audio_base64: "", language: "hi" },
      { audio_base64: "a".repeat(15_000_001), language: "hi" },
    ]) {
      await expect(transcribeViaAi(bad, call)).resolves.toEqual({ transcription_unavailable: true, reason: "invalid_request" });
    }
    expect(call).not.toHaveBeenCalled();
  });

  it("forwards the language to the AI service", async () => {
    const call = vi.fn<AiCall>(async () => ({ transcript: "ਬੁਖਾਰ", translation_en: "fever" }));
    await transcribeViaAi({ audio_base64: "ZmFrZQ==", language: "pa" }, call);
    expect(sentBody(call)).toEqual({ audio_base64: "ZmFrZQ==", language: "pa" });
  });

  it("maps an empty transcript to reason=empty", async () => {
    await expect(transcribeViaAi({ audio_base64: "ZmFrZQ==", language: "en" }, upstream(422, "empty_transcript"))).resolves.toEqual({
      transcription_unavailable: true,
      reason: "empty",
    });
    await expect(transcribeViaAi({ audio_base64: "ZmFrZQ==", language: "en" }, async () => ({ transcript: "x", translation_en: " " }))).resolves.toEqual({
      transcription_unavailable: true,
      reason: "empty",
    });
  });
});
