"use client";

// Offline voice captures: recorded audio waiting for transcription, stored in
// IndexedDB alongside (but separate from) the write queue in offline-queue.ts.
//
// Binding and isolation:
// - every capture carries the recording ASHA's user id, facility, the
//   patient's ABHA number, the selected language, capture time, and a
//   visitId that becomes the encounter's Idempotency-Key when the visit is
//   finally saved -- so a delayed capture can only ever produce ONE encounter,
//   for the patient it was recorded for;
// - every read/write is filtered by user id, so another ASHA signed in on the
//   same phone never sees, processes or deletes someone else's recordings.
//   This is application-level separation, NOT encryption: IndexedDB contents
//   are not encrypted by this app and are readable by anyone with access to
//   the unlocked device's browser profile.
//
// Retention: audio bytes are deleted as soon as transcription succeeds; a
// capture (with or without audio) is purged RETENTION_HOURS after recording,
// and immediately when the ASHA deletes it or its visit is saved.
//
// Delayed transcripts are never auto-submitted: a transcribed capture waits
// in "awaiting_confirmation" until the ASHA opens it, checks the patient and
// confirms the text in the normal review step.
import { openDB, type IDBPDatabase } from "idb";
import type { CaptureLanguage } from "./i18n/languages";

export type VoiceCaptureStatus = "pending_upload" | "transcribing" | "awaiting_confirmation" | "failed" | "completed";

export const RETENTION_HOURS = 72;
export const MAX_AUTO_ATTEMPTS = 5;
export const DEFAULT_ATTEMPT_TIMEOUT_MS = 120_000;
// An attempt can't legitimately run longer than its timeout, so a capture
// still "transcribing" past timeout + margin belongs to a page that was
// reloaded or navigated away mid-upload, and is safe to retry. A younger one
// may be in flight in another tab and is left alone.
const LEASE_MARGIN_MS = 15_000;

export interface VoiceTranscript {
  transcript: string;
  translation_en: string;
  engine: string;
  model: string;
  transcript_warnings?: string[];
  translation_warnings?: string[];
}

export interface QueuedVoiceCapture {
  id: string; // also the complaint_capture.client_capture_id
  visitId: string; // Idempotency-Key for the eventual encounter + triage
  userId: string;
  facilityId: string;
  abhaNumber: string;
  ageMonths: number | null;
  language: CaptureLanguage;
  capturedAt: string;
  consentConfirmedAt: string;
  mimeType: string;
  durationSeconds: number;
  sizeBytes: number;
  audioSha256: string;
  audioBytes: ArrayBuffer | null;
  status: VoiceCaptureStatus;
  attempts: number;
  lastError: string | null;
  nextAttemptAt: string | null;
  updatedAt: string;
  transcript: VoiceTranscript | null;
  expiresAt: string;
}

export type TranscribeAttempt =
  | { ok: true; transcript: VoiceTranscript }
  | { ok: false; retryable: boolean; error: string };

export type Transcriber = (capture: QueuedVoiceCapture) => Promise<TranscribeAttempt>;

const DB_NAME = "healthbridge-voice";
const STORE = "captures";
let dbPromise: Promise<IDBPDatabase> | null = null;

function getDb(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, 1, {
      upgrade(db) {
        const store = db.createObjectStore(STORE, { keyPath: "id" });
        store.createIndex("by_user", "userId");
      },
    });
  }
  return dbPromise;
}

/** Test hook: forget the cached connection after deleting the database. */
export function resetVoiceQueueConnection(): void {
  dbPromise = null;
}

const iso = (ms: number) => new Date(ms).toISOString();

export async function enqueueVoiceCapture(
  input: Omit<QueuedVoiceCapture, "status" | "attempts" | "lastError" | "nextAttemptAt" | "updatedAt" | "transcript" | "expiresAt">,
  nowMs = Date.now(),
): Promise<QueuedVoiceCapture> {
  const record: QueuedVoiceCapture = {
    ...input,
    status: "pending_upload",
    attempts: 0,
    lastError: null,
    nextAttemptAt: null,
    updatedAt: iso(nowMs),
    transcript: null,
    expiresAt: iso(Date.parse(input.capturedAt) + RETENTION_HOURS * 3600 * 1000),
  };
  const db = await getDb();
  await db.put(STORE, record);
  return record;
}

async function purgeExpired(userId: string, nowMs: number): Promise<void> {
  const db = await getDb();
  const all: QueuedVoiceCapture[] = await db.getAllFromIndex(STORE, "by_user", userId);
  for (const capture of all) {
    if (Date.parse(capture.expiresAt) <= nowMs) await db.delete(STORE, capture.id);
  }
}

export async function listVoiceCaptures(userId: string, nowMs = Date.now()): Promise<QueuedVoiceCapture[]> {
  if (!userId) return [];
  await purgeExpired(userId, nowMs);
  const db = await getDb();
  const mine: QueuedVoiceCapture[] = await db.getAllFromIndex(STORE, "by_user", userId);
  return mine.sort((a, b) => a.capturedAt.localeCompare(b.capturedAt));
}

export async function getVoiceCapture(userId: string, id: string): Promise<QueuedVoiceCapture | null> {
  const db = await getDb();
  const capture: QueuedVoiceCapture | undefined = await db.get(STORE, id);
  return capture && capture.userId === userId ? capture : null;
}

export async function deleteVoiceCapture(userId: string, id: string): Promise<boolean> {
  const capture = await getVoiceCapture(userId, id);
  if (!capture) return false;
  const db = await getDb();
  await db.delete(STORE, id);
  return true;
}

async function save(capture: QueuedVoiceCapture): Promise<void> {
  const db = await getDb();
  await db.put(STORE, capture);
}

/** The visit was saved (or queued) with this capture: nothing more to keep. */
export async function completeVoiceCapture(userId: string, id: string, nowMs = Date.now()): Promise<void> {
  const capture = await getVoiceCapture(userId, id);
  if (!capture) return;
  await save({
    ...capture,
    status: "completed",
    audioBytes: null,
    transcript: null,
    updatedAt: iso(nowMs),
    // Keep a content-free "completed" marker briefly so the list can show it.
    expiresAt: iso(Math.min(Date.parse(capture.expiresAt), nowMs + 60 * 60 * 1000)),
  });
}

export async function retryVoiceCapture(userId: string, id: string, nowMs = Date.now()): Promise<void> {
  const capture = await getVoiceCapture(userId, id);
  if (!capture || capture.status !== "failed" || !capture.audioBytes) return;
  // A manual retry grants one more attempt even past the automatic limit.
  await save({ ...capture, status: "pending_upload", nextAttemptAt: null, lastError: null, attempts: Math.min(capture.attempts, MAX_AUTO_ATTEMPTS - 1), updatedAt: iso(nowMs) });
}

function backoffMs(attempts: number): number {
  return Math.min(30 * 60 * 1000, 30 * 1000 * 2 ** Math.max(0, attempts - 1));
}

let inFlight: Promise<number> | null = null;

/**
 * Uploads eligible captures for THIS user only. Returns how many became
 * awaiting_confirmation. Concurrent calls share one pass (no double upload).
 */
export function processVoiceQueue(
  userId: string,
  transcribe: Transcriber,
  nowMs = Date.now(),
  attemptTimeoutMs = DEFAULT_ATTEMPT_TIMEOUT_MS,
): Promise<number> {
  if (inFlight) return inFlight;
  inFlight = runQueue(userId, transcribe, nowMs, attemptTimeoutMs).finally(() => {
    inFlight = null;
  });
  return inFlight;
}

/** A hung upload must never hold the queue lock forever. */
async function withTimeout(attempt: Promise<TranscribeAttempt>, ms: number): Promise<TranscribeAttempt> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<TranscribeAttempt>((resolve) => {
    timer = setTimeout(() => resolve({ ok: false, retryable: true, error: "timeout" }), ms);
  });
  try {
    return await Promise.race([attempt, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

async function runQueue(userId: string, transcribe: Transcriber, nowMs: number, attemptTimeoutMs: number): Promise<number> {
  let ready = 0;
  for (const capture of await listVoiceCaptures(userId, nowMs)) {
    let current = capture;
    // Recovery after a reload/navigation/crash mid-upload.
    if (current.status === "transcribing" && nowMs - Date.parse(current.updatedAt) > attemptTimeoutMs + LEASE_MARGIN_MS) {
      current = { ...current, status: "pending_upload" };
    }
    if (current.status !== "pending_upload" || !current.audioBytes) continue;
    if (current.nextAttemptAt && Date.parse(current.nextAttemptAt) > nowMs) continue;

    const attempt = current.attempts + 1;
    await save({ ...current, status: "transcribing", attempts: attempt, updatedAt: iso(nowMs) });
    let outcome: TranscribeAttempt;
    try {
      outcome = await withTimeout(transcribe(current), attemptTimeoutMs);
    } catch {
      outcome = { ok: false, retryable: true, error: "network" };
    }

    const latest = await getVoiceCapture(userId, current.id);
    if (!latest) continue; // deleted by the ASHA while uploading

    if (outcome.ok) {
      await save({ ...latest, status: "awaiting_confirmation", transcript: outcome.transcript, audioBytes: null, lastError: null, nextAttemptAt: null, updatedAt: iso(nowMs) });
      ready += 1;
    } else if (outcome.retryable && attempt < MAX_AUTO_ATTEMPTS) {
      await save({ ...latest, status: "pending_upload", lastError: outcome.error, nextAttemptAt: iso(nowMs + backoffMs(attempt)), updatedAt: iso(nowMs) });
    } else {
      await save({ ...latest, status: "failed", lastError: outcome.error, nextAttemptAt: null, updatedAt: iso(nowMs) });
    }
  }
  return ready;
}
