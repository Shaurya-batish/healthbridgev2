import { describe, expect, it } from "vitest";
import { VoiceRecorderController, type RecorderDeps, type RecorderState } from "./voice-recorder";

// Fakes model the browser contracts the controller relies on. They are test
// doubles, not evidence that a physical microphone works (see docs).
class FakeTrack {
  stopped = false;
  stop() {
    this.stopped = true;
  }
}

class FakeStream {
  tracks = [new FakeTrack()];
  getTracks() {
    return this.tracks;
  }
}

class FakeRecorder {
  static instances: FakeRecorder[] = [];
  static isTypeSupported = (t: string) => t === "audio/webm;codecs=opus";
  state = "inactive";
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  constructor(_stream: unknown, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? "";
    FakeRecorder.instances.push(this);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    if (this.state === "inactive") return;
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob([new Uint8Array(20_000)], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function harness(overrides: Partial<RecorderDeps> = {}) {
  let now = 1_000_000;
  const tickers: Array<() => void> = [];
  const stream = new FakeStream();
  const states: RecorderState[] = [];
  const deps: RecorderDeps = {
    getUserMedia: async () => stream as unknown as MediaStream,
    MediaRecorder: FakeRecorder as unknown as RecorderDeps["MediaRecorder"],
    isSecureContext: true,
    now: () => now,
    setInterval: (fn) => {
      tickers.push(fn);
      return tickers.length;
    },
    clearInterval: () => undefined,
    ...overrides,
  };
  const controller = new VoiceRecorderController(deps, (s) => states.push(s));
  return {
    controller,
    stream,
    states,
    advance(seconds: number) {
      now += seconds * 1000;
      tickers.forEach((t) => t());
    },
  };
}

describe("VoiceRecorderController", () => {
  it("records, stops, validates and releases the microphone", async () => {
    const h = harness();
    await h.controller.start();
    expect(h.controller.getState()).toEqual({ status: "recording", elapsedSeconds: 0 });
    h.advance(4);
    expect(h.controller.getState()).toEqual({ status: "recording", elapsedSeconds: 4 });
    h.controller.stop();
    const state = h.controller.getState();
    expect(state.status).toBe("recorded");
    if (state.status === "recorded") {
      expect(state.mimeType).toBe("audio/webm;codecs=opus");
      expect(state.durationSeconds).toBe(4);
      expect(state.blob.size).toBe(20_000);
    }
    expect(h.stream.tracks.every((t) => t.stopped)).toBe(true);
    expect(h.states.map((s) => s.status)).toEqual(["requesting", "recording", "recording", "recorded"]);
  });

  it("reports permission denial and missing hardware distinctly, holding no tracks", async () => {
    const denied = harness({ getUserMedia: async () => Promise.reject(Object.assign(new Error("no"), { name: "NotAllowedError" })) });
    await denied.controller.start();
    expect(denied.controller.getState()).toEqual({ status: "error", error: "permission_denied" });

    const missing = harness({ getUserMedia: async () => Promise.reject(Object.assign(new Error("none"), { name: "NotFoundError" })) });
    await missing.controller.start();
    expect(missing.controller.getState()).toEqual({ status: "error", error: "no_microphone" });
  });

  it("reports unsupported browsers and insecure contexts without prompting", async () => {
    const noRecorder = harness({ MediaRecorder: undefined });
    await noRecorder.controller.start();
    expect(noRecorder.controller.getState()).toEqual({ status: "error", error: "unsupported" });

    const insecure = harness({ isSecureContext: false });
    await insecure.controller.start();
    expect(insecure.controller.getState()).toEqual({ status: "error", error: "insecure_context" });
  });

  it("cancel during recording discards audio and releases tracks", async () => {
    const h = harness();
    await h.controller.start();
    h.advance(3);
    h.controller.cancel();
    expect(h.controller.getState()).toEqual({ status: "idle" });
    expect(h.stream.tracks.every((t) => t.stopped)).toBe(true);
    expect(h.states.some((s) => s.status === "recorded")).toBe(false);
  });

  it("cancel while the permission prompt is open releases the stream when it arrives", async () => {
    let grant!: (s: MediaStream) => void;
    const stream = new FakeStream();
    const h = harness({ getUserMedia: () => new Promise((resolve) => (grant = resolve)) });
    const starting = h.controller.start();
    expect(h.controller.getState()).toEqual({ status: "requesting" });
    h.controller.cancel();
    grant(stream as unknown as MediaStream);
    await starting;
    expect(stream.tracks.every((t) => t.stopped)).toBe(true);
    expect(h.controller.getState()).toEqual({ status: "idle" });
  });

  it("dispose (unmount/navigation) releases tracks without emitting", async () => {
    const h = harness();
    await h.controller.start();
    const emitted = h.states.length;
    h.controller.dispose();
    expect(h.stream.tracks.every((t) => t.stopped)).toBe(true);
    expect(h.states.length).toBe(emitted);
  });

  it("rejects a too-short recording and auto-stops at the maximum duration", async () => {
    const short = harness();
    await short.controller.start();
    short.advance(0.5);
    short.controller.stop();
    expect(short.controller.getState()).toEqual({ status: "error", error: "too_short" });

    const long = harness({ maxSeconds: 10 });
    await long.controller.start();
    long.advance(10);
    const state = long.controller.getState();
    expect(state.status).toBe("recorded");
    if (state.status === "recorded") expect(state.autoStopped).toBe(true);
    expect(long.stream.tracks.every((t) => t.stopped)).toBe(true);
  });
});
