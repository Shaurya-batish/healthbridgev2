import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { enqueueCreatePatient, flushQueue, listPending } from "./offline-queue";

/**
 * Regression coverage for the offline-first write queue -- see CLAUDE.md's
 * offline-first requirement and the 2026-09-13 technical hardening pass
 * (section 8: offline data safety is HIGH PRIORITY). fake-indexeddb gives
 * these tests a real IndexedDB implementation to run against, so this is
 * genuine coverage of the actual persistence/sync logic, not a mock of it.
 */

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(async () => {
  // Fresh IndexedDB per test -- delete and let offline-queue.ts reopen it.
  indexedDB.deleteDatabase("healthbridge-offline");
  vi.restoreAllMocks();
});

describe("concurrent flushQueue calls", () => {
  it("does not double-submit the same queued operation when called concurrently", async () => {
    await enqueueCreatePatient("/api/patients", { abha_number: "12-3456-7890-1234", name: "Test Patient" });

    let callCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        callCount += 1;
        // A small delay is what actually opens the race window between
        // two concurrent flushQueue() calls reading the same pending list
        // before either has removed the entry.
        await new Promise((resolve) => setTimeout(resolve, 20));
        return jsonResponse(201, { id: "new-patient-id" });
      }),
    );

    // Simulates the real trigger: mount's initial syncNow() and an
    // 'online' event firing in quick succession both call flushQueue().
    await Promise.all([flushQueue(), flushQueue()]);

    expect(callCount).toBe(1);
    expect(await listPending()).toHaveLength(0);
  });

  it("a second concurrent call still resolves cleanly (no throw) once the first has emptied the queue", async () => {
    await enqueueCreatePatient("/api/patients", { abha_number: "11-1111-1111-1111", name: "Another Patient" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        await new Promise((resolve) => setTimeout(resolve, 10));
        return jsonResponse(201, { id: "id" });
      }),
    );

    const [first, second] = await Promise.all([flushQueue(), flushQueue()]);
    expect(first.remaining).toBe(0);
    expect(second.remaining).toBe(0);
  });
});
