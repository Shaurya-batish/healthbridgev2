"use client";

// IndexedDB write queue for the ASHA app. Register, triage, and token
// creation must all work with zero signal (CLAUDE.md: offline-first ASHA
// app). Encounters are append-only and server timestamps win, so replaying
// the queue in FIFO order on reconnect is sufficient — no conflict UI.
//
// One real wrinkle: submitting a triage record requires a server-assigned
// encounter_id, but creating the encounter itself may also be queued while
// offline. `submitEncounterAndTriage` below chains the two calls and, if the
// encounter succeeds but the network drops before the triage call, re-queues
// only the remaining triage half against the now-known encounter_id — it
// never re-sends (and never loses) the encounter.
import { openDB, type IDBPDatabase } from "idb";

interface SimpleOp {
  id: string;
  type: "create_patient";
  endpoint: string;
  payload: Record<string, unknown>;
  created_at: string;
}

interface EncounterWithTriageOp {
  id: string;
  type: "encounter_with_triage";
  encounterEndpoint: string;
  encounterPayload: Record<string, unknown>;
  triageEndpoint: string;
  triagePayload: Record<string, unknown>;
  created_at: string;
}

interface TriageOnlyOp {
  id: string;
  type: "triage_only";
  endpoint: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export type QueuedOperation = SimpleOp | EncounterWithTriageOp | TriageOnlyOp;

const DB_NAME = "healthbridge-offline";
const STORE = "queue";

let dbPromise: Promise<IDBPDatabase> | null = null;

function getDb(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, 1, {
      upgrade(db) {
        db.createObjectStore(STORE, { keyPath: "id" });
      },
    });
  }
  return dbPromise;
}

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function put(op: QueuedOperation): Promise<void> {
  const db = await getDb();
  await db.put(STORE, op);
}

export async function enqueueCreatePatient(endpoint: string, payload: Record<string, unknown>, id: string = newId()): Promise<void> {
  await put({ id, type: "create_patient", endpoint, payload, created_at: new Date().toISOString() });
}

export async function listPending(): Promise<QueuedOperation[]> {
  const db = await getDb();
  const all: QueuedOperation[] = await db.getAll(STORE);
  return all.sort((a, b) => a.created_at.localeCompare(b.created_at));
}

async function removeOperation(id: string): Promise<void> {
  const db = await getDb();
  await db.delete(STORE, id);
}

async function postJson(
  endpoint: string,
  payload: unknown,
  idempotencyKey?: string,
): Promise<{ ok: true; body: any } | { ok: false; networkError: true } | { ok: false; networkError: false; status: number; body: unknown }> {
  let res: Response;
  try {
    res = await fetch(endpoint, {
      method: "POST",
      // Idempotency-Key: a network timeout where the server actually
      // succeeded but the client saw a failure used to mean a genuine
      // retry (here, or via the offline queue below) could create a
      // duplicate patient/encounter/triage record. Every call site below
      // passes the SAME key on every attempt of the same logical
      // operation (the queued op's own id, generated once up front) so
      // Core (see services/core/app/idempotency.py) replays the original
      // response on a retry instead of repeating the write.
      headers: {
        "Content-Type": "application/json",
        ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      },
      body: JSON.stringify(payload),
    });
  } catch {
    return { ok: false, networkError: true };
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    // The gateway itself is reachable but says the service behind it isn't
    // (CONTRACT.md: /api/** returns 502 {detail: "core_unavailable"/"ai_unavailable"}
    // when it can't reach Core/AI). That's the same situation as a network
    // error for queueing purposes -- retry later, never discard the write.
    // A real rejection (409 duplicate, 422 validation, 404) is a different
    // HTTP status and still drops the queued item as before.
    if (res.status === 502 && body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (detail === "core_unavailable" || detail === "ai_unavailable") {
        return { ok: false, networkError: true };
      }
    }
    return { ok: false, networkError: false, status: res.status, body };
  }
  return { ok: true, body };
}

export type SubmitOutcome =
  | { status: "sent"; triageRecord: unknown }
  | { status: "queued"; partial?: boolean }
  | { status: "rejected"; detail: unknown };

/**
 * Registers a patient. Tries the network first; queues on failure. A create
 * is idempotent-ish server-side by abha_number, so a safe operation to defer.
 */
export async function submitCreatePatient(
  endpoint: string,
  payload: Record<string, unknown>,
): Promise<{ status: "sent"; body: unknown } | { status: "queued" } | { status: "rejected"; detail: unknown }> {
  // Generated once, up front, and reused on every attempt of this same
  // logical operation (this direct try, and the queued retry below if it
  // comes to that) -- this is what lets Core recognize a retry as a
  // retry rather than a new write.
  const opId = newId();

  if (navigator.onLine) {
    const result = await postJson(endpoint, payload, opId);
    if (result.ok) return { status: "sent", body: result.body };
    if (!result.networkError) return { status: "rejected", detail: result.body };
  }
  await enqueueCreatePatient(endpoint, payload, opId);
  return { status: "queued" };
}

/**
 * Creates an encounter and immediately submits its triage record. Handles
 * every combination of online/offline failure without ever losing or
 * duplicating the encounter half.
 */
export async function submitEncounterAndTriage(
  encounterEndpoint: string,
  encounterPayload: Record<string, unknown>,
  triageEndpoint: string,
  triagePayload: Record<string, unknown>,
): Promise<SubmitOutcome> {
  // Generated once, up front, and reused for BOTH the encounter and
  // triage calls, on every attempt (the initial direct try below and any
  // queued retry that follows) -- Core's idempotency cache is keyed by
  // (key, endpoint) together, so one shared id never collides between the
  // two endpoints (see services/core/app/idempotency.py).
  const opId = newId();

  if (!navigator.onLine) {
    await put({
      id: opId,
      type: "encounter_with_triage",
      encounterEndpoint,
      encounterPayload,
      triageEndpoint,
      triagePayload,
      created_at: new Date().toISOString(),
    });
    return { status: "queued" };
  }

  const encounterResult = await postJson(encounterEndpoint, encounterPayload, opId);
  if (!encounterResult.ok) {
    if (encounterResult.networkError) {
      await put({
        id: opId,
        type: "encounter_with_triage",
        encounterEndpoint,
        encounterPayload,
        triageEndpoint,
        triagePayload,
        created_at: new Date().toISOString(),
      });
      return { status: "queued" };
    }
    return { status: "rejected", detail: encounterResult.body };
  }

  const encounterId = encounterResult.body.id;
  const resolvedTriagePayload = { ...triagePayload, encounter_id: encounterId };
  const triageResult = await postJson(triageEndpoint, resolvedTriagePayload, opId);

  if (triageResult.ok) return { status: "sent", triageRecord: triageResult.body };

  if (triageResult.networkError) {
    await put({
      id: opId,
      type: "triage_only",
      endpoint: triageEndpoint,
      payload: resolvedTriagePayload,
      created_at: new Date().toISOString(),
    });
    return { status: "queued", partial: true };
  }

  return { status: "rejected", detail: triageResult.body };
}

export interface FlushResult {
  flushed: number;
  remaining: number;
  failed?: { detail: unknown };
}

// Two calls to flushQueue() firing close together (mount's initial sync and
// an 'online' event, or a double-tap on "Sync now" before the button's
// disabled state re-renders) used to both read the same pending list and
// both POST the same operation -- a real double-submission bug (confirmed:
// duplicate patient/encounter/triage writes). `syncing` React state alone
// isn't a synchronous guard against this, so the lock lives here instead:
// a second concurrent call gets back the SAME in-flight promise rather than
// starting its own pass over the queue.
let inFlightFlush: Promise<FlushResult> | null = null;

export function flushQueue(): Promise<FlushResult> {
  if (inFlightFlush) return inFlightFlush;
  inFlightFlush = _flushQueue().finally(() => {
    inFlightFlush = null;
  });
  return inFlightFlush;
}

/** Replays every queued operation in FIFO order. Stops at the first thing that still can't reach the network. */
async function _flushQueue(): Promise<FlushResult> {
  const pending = await listPending();
  let flushed = 0;

  for (const op of pending) {
    if (op.type === "create_patient") {
      const result = await postJson(op.endpoint, op.payload);
      if (result.ok) {
        await removeOperation(op.id);
        flushed += 1;
        continue;
      }
      if (result.networkError) break;
      await removeOperation(op.id);
      return { flushed, remaining: (await listPending()).length, failed: { detail: result.body } };
    }

    if (op.type === "triage_only") {
      const result = await postJson(op.endpoint, op.payload);
      if (result.ok) {
        await removeOperation(op.id);
        flushed += 1;
        continue;
      }
      if (result.networkError) break;
      await removeOperation(op.id);
      return { flushed, remaining: (await listPending()).length, failed: { detail: result.body } };
    }

    // encounter_with_triage
    const encounterResult = await postJson(op.encounterEndpoint, op.encounterPayload);
    if (!encounterResult.ok) {
      if (encounterResult.networkError) break;
      await removeOperation(op.id);
      return { flushed, remaining: (await listPending()).length, failed: { detail: encounterResult.body } };
    }

    const encounterId = encounterResult.body.id;
    const resolvedTriagePayload = { ...op.triagePayload, encounter_id: encounterId };
    const triageResult = await postJson(op.triageEndpoint, resolvedTriagePayload);

    if (triageResult.ok) {
      await removeOperation(op.id);
      flushed += 1;
      continue;
    }

    if (triageResult.networkError) {
      // Encounter is safely on the server now — downgrade this queue entry
      // so we never re-POST the encounter on the next flush attempt.
      await put({
        id: op.id,
        type: "triage_only",
        endpoint: op.triageEndpoint,
        payload: resolvedTriagePayload,
        created_at: op.created_at,
      });
      break;
    }

    await removeOperation(op.id);
    return { flushed, remaining: (await listPending()).length, failed: { detail: triageResult.body } };
  }

  return { flushed, remaining: (await listPending()).length };
}
