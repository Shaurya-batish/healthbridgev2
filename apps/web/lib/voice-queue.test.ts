import "fake-indexeddb/auto";
import { openDB } from "idb";
import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_ATTEMPT_TIMEOUT_MS,
  MAX_AUTO_ATTEMPTS,
  RETENTION_HOURS,
  completeVoiceCapture,
  deleteVoiceCapture,
  enqueueVoiceCapture,
  getVoiceCapture,
  listVoiceCaptures,
  processVoiceQueue,
  retryVoiceCapture,
  type Transcriber,
} from "./voice-queue";

// fake-indexeddb is a real IndexedDB implementation; unique user ids keep
// tests independent without deleting the shared database.
let counter = 0;
const uid = () => `user-${Date.now()}-${counter++}`;
const T0 = Date.parse("2026-09-15T10:00:00.000Z");

function input(userId: string, overrides: Record<string, unknown> = {}) {
  const id = `cap-${userId}-${counter++}`;
  return {
    id,
    visitId: `visit-${id}`,
    userId,
    facilityId: "facility-1",
    abhaNumber: "91-1234-5678-9012",
    ageMonths: 14,
    language: "hi" as const,
    capturedAt: new Date(T0).toISOString(),
    consentConfirmedAt: new Date(T0).toISOString(),
    mimeType: "audio/webm;codecs=opus",
    durationSeconds: 6,
    sizeBytes: 3,
    audioSha256: "a".repeat(64),
    audioBytes: new Uint8Array([1, 2, 3]).buffer,
    ...overrides,
  };
}

const success: Transcriber = async () => ({
  ok: true,
  transcript: { transcript: "बुखार है", translation_en: "has fever", engine: "faster-whisper", model: "small" },
});

describe("binding and isolation", () => {
  it("keeps patient, language and capture time, and hides captures from other users", async () => {
    const alice = uid();
    const bob = uid();
    const capture = await enqueueVoiceCapture(input(alice, { abhaNumber: "91-0000-0000-0001", language: "ta" }), T0);
    expect(capture.status).toBe("pending_upload");

    const mine = await listVoiceCaptures(alice, T0);
    expect(mine.map((c) => [c.abhaNumber, c.language, c.capturedAt])).toEqual([["91-0000-0000-0001", "ta", new Date(T0).toISOString()]]);
    expect(await listVoiceCaptures(bob, T0)).toEqual([]);
    expect(await getVoiceCapture(bob, capture.id)).toBeNull();
    expect(await deleteVoiceCapture(bob, capture.id)).toBe(false);
    expect(await getVoiceCapture(alice, capture.id)).not.toBeNull();
  });

  it("only processes the signed-in user's recordings", async () => {
    const alice = uid();
    const bob = uid();
    await enqueueVoiceCapture(input(bob), T0);
    const transcribe = vi.fn(success);
    expect(await processVoiceQueue(alice, transcribe, T0)).toBe(0);
    expect(transcribe).not.toHaveBeenCalled();
  });
});

describe("processing", () => {
  it("moves to awaiting_confirmation, deletes audio, and never auto-submits", async () => {
    const user = uid();
    const capture = await enqueueVoiceCapture(input(user), T0);
    const transcribe = vi.fn(success);
    expect(await processVoiceQueue(user, transcribe, T0)).toBe(1);
    const after = await getVoiceCapture(user, capture.id);
    expect(after?.status).toBe("awaiting_confirmation");
    expect(after?.audioBytes).toBeNull();
    expect(after?.transcript?.translation_en).toBe("has fever");
    expect(after?.abhaNumber).toBe(capture.abhaNumber);

    // A second pass does not upload it again.
    await processVoiceQueue(user, transcribe, T0 + 60_000);
    expect(transcribe).toHaveBeenCalledTimes(1);
  });

  it("concurrent reconnect triggers upload each capture once", async () => {
    const user = uid();
    await enqueueVoiceCapture(input(user), T0);
    const transcribe = vi.fn<Transcriber>(async (c) => {
      await new Promise((r) => setTimeout(r, 20));
      return success(c);
    });
    await Promise.all([processVoiceQueue(user, transcribe, T0), processVoiceQueue(user, transcribe, T0)]);
    expect(transcribe).toHaveBeenCalledTimes(1);
  });

  it("retries transient failures with backoff and stops after the bounded number of attempts", async () => {
    const user = uid();
    const capture = await enqueueVoiceCapture(input(user), T0);
    const failing = vi.fn<Transcriber>(async () => ({ ok: false, retryable: true, error: "unavailable" }));

    let now = T0;
    await processVoiceQueue(user, failing, now);
    let state = await getVoiceCapture(user, capture.id);
    expect(state?.status).toBe("pending_upload");
    expect(state?.attempts).toBe(1);

    // Not retried before its backoff time.
    await processVoiceQueue(user, failing, now + 1000);
    expect(failing).toHaveBeenCalledTimes(1);

    for (let i = 0; i < MAX_AUTO_ATTEMPTS + 2; i++) {
      now += 60 * 60 * 1000;
      await processVoiceQueue(user, failing, now);
    }
    state = await getVoiceCapture(user, capture.id);
    expect(state?.status).toBe("failed");
    expect(failing).toHaveBeenCalledTimes(MAX_AUTO_ATTEMPTS);
    expect(state?.audioBytes).not.toBeNull(); // kept for a manual retry until retention expires

    await retryVoiceCapture(user, capture.id, now);
    const ok = vi.fn(success);
    await processVoiceQueue(user, ok, now);
    expect((await getVoiceCapture(user, capture.id))?.status).toBe("awaiting_confirmation");
  });

  it("invalid audio fails immediately without retrying", async () => {
    const user = uid();
    const capture = await enqueueVoiceCapture(input(user), T0);
    const invalid = vi.fn<Transcriber>(async () => ({ ok: false, retryable: false, error: "invalid_audio" }));
    await processVoiceQueue(user, invalid, T0);
    await processVoiceQueue(user, invalid, T0 + 3_600_000);
    expect(invalid).toHaveBeenCalledTimes(1);
    expect((await getVoiceCapture(user, capture.id))?.lastError).toBe("invalid_audio");
  });

  it("a hung upload times out, stays retryable, and does not block later passes", async () => {
    const user = uid();
    const capture = await enqueueVoiceCapture(input(user), T0);
    const hang = vi.fn<Transcriber>(() => new Promise(() => undefined));
    await processVoiceQueue(user, hang, T0, 20);
    const after = await getVoiceCapture(user, capture.id);
    expect(after?.status).toBe("pending_upload");
    expect(after?.lastError).toBe("timeout");

    const ok = vi.fn(success);
    await processVoiceQueue(user, ok, T0 + 60 * 60 * 1000);
    expect((await getVoiceCapture(user, capture.id))?.status).toBe("awaiting_confirmation");
  });

  it("recovers a capture left in 'transcribing' by a page that closed mid-upload", async () => {
    const user = uid();
    const capture = await enqueueVoiceCapture(input(user), T0);
    // What a crashed/reloaded tab leaves behind: status written, never finished.
    const db = await openDB("healthbridge-voice", 1);
    await db.put("captures", { ...capture, status: "transcribing", attempts: 1, updatedAt: new Date(T0).toISOString() });
    db.close();

    const ok = vi.fn(success);
    // Still within the attempt lease: may be in flight in another tab -- not re-uploaded.
    await processVoiceQueue(user, ok, T0 + 60 * 1000);
    expect(ok).not.toHaveBeenCalled();
    // Lease expired (timeout + margin): recovered and retried.
    await processVoiceQueue(user, ok, T0 + DEFAULT_ATTEMPT_TIMEOUT_MS + 16_000);
    expect(ok).toHaveBeenCalledTimes(1);
    expect((await getVoiceCapture(user, capture.id))?.status).toBe("awaiting_confirmation");
  });

  it("a capture deleted during upload is not resurrected", async () => {
    const user = uid();
    const capture = await enqueueVoiceCapture(input(user), T0);
    const slow: Transcriber = async (c) => {
      await deleteVoiceCapture(user, capture.id);
      return success(c);
    };
    await processVoiceQueue(user, slow, T0);
    expect(await getVoiceCapture(user, capture.id)).toBeNull();
  });
});

describe("retention", () => {
  it("purges captures after the retention window and strips content on completion", async () => {
    const user = uid();
    const old = await enqueueVoiceCapture(input(user), T0);
    const fresh = await enqueueVoiceCapture(input(user, { capturedAt: new Date(T0 + 70 * 3600 * 1000).toISOString() }), T0);

    const later = T0 + (RETENTION_HOURS + 1) * 3600 * 1000;
    const remaining = await listVoiceCaptures(user, later);
    expect(remaining.map((c) => c.id)).toEqual([fresh.id]);
    expect(await getVoiceCapture(user, old.id)).toBeNull();

    await completeVoiceCapture(user, fresh.id, later);
    const done = await getVoiceCapture(user, fresh.id);
    expect(done?.status).toBe("completed");
    expect(done?.audioBytes).toBeNull();
    expect(done?.transcript).toBeNull();
    expect(await listVoiceCaptures(user, later + 2 * 3600 * 1000)).toEqual([]);
  });
});
