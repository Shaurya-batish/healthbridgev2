import { describe, expect, it } from "vitest";
import { AUDIO_MAX_BYTES, AUDIO_MAX_SECONDS, isAllowedAudioMime, pickRecorderMimeType, validateRecording } from "./audio-constraints";

describe("recorder format selection", () => {
  it("prefers webm/opus, falls back in order, and reports none when unsupported", () => {
    expect(pickRecorderMimeType((t) => t.startsWith("audio/webm"))).toBe("audio/webm;codecs=opus");
    expect(pickRecorderMimeType((t) => t === "audio/mp4")).toBe("audio/mp4");
    expect(pickRecorderMimeType(() => false)).toBeNull();
    expect(pickRecorderMimeType(undefined)).toBeNull();
  });

  it("allows only audio formats, with or without codec parameters", () => {
    expect(isAllowedAudioMime("audio/webm;codecs=opus")).toBe(true);
    expect(isAllowedAudioMime("AUDIO/OGG")).toBe(true);
    expect(isAllowedAudioMime("video/webm")).toBe(false);
    expect(isAllowedAudioMime("text/plain")).toBe(false);
    expect(isAllowedAudioMime(undefined)).toBe(false);
  });
});

describe("recording validation", () => {
  const ok = { bytes: 50_000, durationSeconds: 5, mimeType: "audio/webm" };

  it("accepts a normal recording", () => {
    expect(validateRecording(ok)).toBeNull();
  });

  it.each([
    [{ ...ok, bytes: 0 }, "empty"],
    [{ ...ok, durationSeconds: 0.4 }, "too_short"],
    [{ ...ok, durationSeconds: AUDIO_MAX_SECONDS + 5 }, "too_long"],
    [{ ...ok, bytes: AUDIO_MAX_BYTES + 1 }, "too_large"],
    [{ ...ok, mimeType: "video/mp4" }, "unsupported_format"],
  ])("rejects %o as %s", (input, problem) => {
    expect(validateRecording(input)).toBe(problem);
  });
});
