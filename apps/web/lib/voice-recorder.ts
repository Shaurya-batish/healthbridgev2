// Microphone capture with the real browser APIs (getUserMedia + MediaRecorder),
// written as a framework-free controller with injectable dependencies so its
// state machine -- including permission denial, cancellation and track
// release -- is unit tested without a browser. The React component only
// renders its state.
import { AUDIO_MAX_SECONDS, pickRecorderMimeType, validateRecording, type RecordingProblem } from "./audio-constraints";

export type RecorderError = "unsupported" | "insecure_context" | "permission_denied" | "no_microphone" | "recorder_failed" | RecordingProblem;

export type RecorderState =
  | { status: "idle" }
  | { status: "requesting" }
  | { status: "recording"; elapsedSeconds: number }
  | { status: "recorded"; blob: Blob; mimeType: string; durationSeconds: number; autoStopped: boolean }
  | { status: "error"; error: RecorderError };

interface MinimalRecorder {
  state: string;
  mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
  onerror: ((event: unknown) => void) | null;
  start(timeslice?: number): void;
  stop(): void;
}

export interface RecorderDeps {
  getUserMedia?: (constraints: MediaStreamConstraints) => Promise<MediaStream>;
  MediaRecorder?: { new (stream: MediaStream, options?: { mimeType?: string }): MinimalRecorder; isTypeSupported?: (type: string) => boolean };
  isSecureContext?: boolean;
  now: () => number;
  setInterval: (fn: () => void, ms: number) => unknown;
  clearInterval: (handle: unknown) => void;
  maxSeconds?: number;
}

export function browserRecorderDeps(): RecorderDeps {
  const nav = typeof navigator !== "undefined" ? navigator : undefined;
  return {
    getUserMedia: nav?.mediaDevices?.getUserMedia ? (c) => nav.mediaDevices.getUserMedia(c) : undefined,
    MediaRecorder: typeof MediaRecorder !== "undefined" ? (MediaRecorder as unknown as RecorderDeps["MediaRecorder"]) : undefined,
    isSecureContext: typeof window !== "undefined" ? window.isSecureContext : true,
    now: () => Date.now(),
    setInterval: (fn, ms) => window.setInterval(fn, ms),
    clearInterval: (h) => window.clearInterval(h as number),
  };
}

function classifyMediaError(err: unknown): RecorderError {
  const name = (err as { name?: string } | null)?.name;
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") return "permission_denied";
  if (name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError") return "no_microphone";
  return "recorder_failed";
}

export class VoiceRecorderController {
  private state: RecorderState = { status: "idle" };
  private stream: MediaStream | null = null;
  private recorder: MinimalRecorder | null = null;
  private chunks: Blob[] = [];
  private startedAt = 0;
  private ticker: unknown = null;
  private generation = 0; // invalidates late callbacks after cancel/dispose
  private autoStopped = false;

  constructor(
    private readonly deps: RecorderDeps,
    private readonly onChange: (state: RecorderState) => void,
  ) {}

  getState(): RecorderState {
    return this.state;
  }

  private set(next: RecorderState) {
    this.state = next;
    this.onChange(next);
  }

  async start(): Promise<void> {
    if (this.state.status === "requesting" || this.state.status === "recording") return;
    if (this.deps.isSecureContext === false) return this.set({ status: "error", error: "insecure_context" });
    if (!this.deps.getUserMedia || !this.deps.MediaRecorder) return this.set({ status: "error", error: "unsupported" });

    const generation = ++this.generation;
    this.set({ status: "requesting" });
    let stream: MediaStream;
    try {
      stream = await this.deps.getUserMedia({ audio: true });
    } catch (err) {
      if (generation === this.generation) this.set({ status: "error", error: classifyMediaError(err) });
      return;
    }
    if (generation !== this.generation) {
      // Cancelled (or unmounted) while the permission prompt was open.
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    this.stream = stream;

    const mimeType = pickRecorderMimeType(this.deps.MediaRecorder.isTypeSupported?.bind(this.deps.MediaRecorder));
    let recorder: MinimalRecorder;
    try {
      recorder = new this.deps.MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch {
      this.releaseTracks();
      return this.set({ status: "error", error: "unsupported" });
    }
    this.recorder = recorder;
    this.chunks = [];
    this.autoStopped = false;
    recorder.ondataavailable = (event) => {
      if (generation === this.generation && event.data && event.data.size > 0) this.chunks.push(event.data);
    };
    recorder.onerror = () => {
      if (generation !== this.generation) return;
      this.teardown();
      this.set({ status: "error", error: "recorder_failed" });
    };
    recorder.onstop = () => {
      if (generation !== this.generation) return;
      const durationSeconds = Math.round(((this.deps.now() - this.startedAt) / 1000) * 10) / 10;
      const type = recorder.mimeType || mimeType || "audio/webm";
      const blob = new Blob(this.chunks, { type });
      const autoStopped = this.autoStopped;
      this.teardown();
      const problem = validateRecording({ bytes: blob.size, durationSeconds, mimeType: type });
      if (problem) return this.set({ status: "error", error: problem });
      this.set({ status: "recorded", blob, mimeType: type, durationSeconds, autoStopped });
    };

    try {
      recorder.start(1000);
    } catch {
      this.teardown();
      return this.set({ status: "error", error: "recorder_failed" });
    }
    this.startedAt = this.deps.now();
    this.set({ status: "recording", elapsedSeconds: 0 });
    const max = this.deps.maxSeconds ?? AUDIO_MAX_SECONDS;
    this.ticker = this.deps.setInterval(() => {
      if (generation !== this.generation || this.state.status !== "recording") return;
      const elapsed = Math.floor((this.deps.now() - this.startedAt) / 1000);
      if (elapsed >= max) {
        this.autoStopped = true;
        this.stop();
        return;
      }
      this.set({ status: "recording", elapsedSeconds: elapsed });
    }, 250);
  }

  stop(): void {
    if (this.state.status !== "recording" || !this.recorder) return;
    if (this.ticker !== null) {
      this.deps.clearInterval(this.ticker);
      this.ticker = null;
    }
    try {
      if (this.recorder.state !== "inactive") this.recorder.stop();
    } catch {
      this.teardown();
      this.set({ status: "error", error: "recorder_failed" });
    }
  }

  /** Discards any audio and releases the microphone. Safe in every state. */
  cancel(): void {
    this.generation += 1;
    const recorder = this.recorder;
    this.teardown();
    try {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    } catch {
      /* already stopped */
    }
    this.chunks = [];
    this.set({ status: "idle" });
  }

  /** For unmount/navigation: like cancel, but without notifying a dead component. */
  dispose(): void {
    this.generation += 1;
    const recorder = this.recorder;
    this.teardown();
    try {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    } catch {
      /* already stopped */
    }
    this.chunks = [];
    this.state = { status: "idle" };
  }

  private teardown() {
    if (this.ticker !== null) {
      this.deps.clearInterval(this.ticker);
      this.ticker = null;
    }
    this.releaseTracks();
    this.recorder = null;
  }

  private releaseTracks() {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }
}

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

export function arrayBufferToBase64(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < view.length; i += chunk) {
    binary += String.fromCharCode(...view.subarray(i, i + chunk));
  }
  return btoa(binary);
}
