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

export async function enqueueCreatePatient(endpoint: string, payload: Record<string, unknown>): Promise<void> {
  await put({ id: newId(), type: "create_patient", endpoint, payload, created_at: new Date().toISOString() });
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

async function postJson(endpoint: string, payload: unknown): Promise<{ ok: true; body: any } | { ok: false; networkError: true } | { ok: false; networkError: false; status: number; body: unknown }> {
  let res: Response;
  try {
    res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    return { ok: false, networkError: true };
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) return { ok: false, networkError: false, status: res.status, body };
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
  if (navigator.onLine) {
    const result = await postJson(endpoint, payload);
    if (result.ok) return { status: "sent", body: result.body };
    if (!result.networkError) return { status: "rejected", detail: result.body };
  }
  await enqueueCreatePatient(endpoint, payload);
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
  if (!navigator.onLine) {
    await put({
      id: newId(),
      type: "encounter_with_triage",
      encounterEndpoint,
      encounterPayload,
      triageEndpoint,
      triagePayload,
      created_at: new Date().toISOString(),
    });
    return { status: "queued" };
  }

  const encounterResult = await postJson(encounterEndpoint, encounterPayload);
  if (!encounterResult.ok) {
    if (encounterResult.networkError) {
      await put({
        id: newId(),
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
  const triageResult = await postJson(triageEndpoint, resolvedTriagePayload);

  if (triageResult.ok) return { status: "sent", triageRecord: triageResult.body };

  if (triageResult.networkError) {
    await put({
      id: newId(),
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

/** Replays every queued operation in FIFO order. Stops at the first thing that still can't reach the network. */
export async function flushQueue(): Promise<FlushResult> {
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
