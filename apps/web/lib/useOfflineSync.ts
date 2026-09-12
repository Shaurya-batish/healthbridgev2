"use client";

import { useCallback, useEffect, useState } from "react";
import {
  flushQueue,
  listPending,
  submitCreatePatient,
  submitEncounterAndTriage,
  type SubmitOutcome,
} from "./offline-queue";

export interface OfflineSyncState {
  isOnline: boolean;
  pendingCount: number;
  syncing: boolean;
  lastError: string | null;
  submitCreatePatient: (
    endpoint: string,
    payload: Record<string, unknown>,
  ) => Promise<{ status: "sent"; body: unknown } | { status: "queued" } | { status: "rejected"; detail: unknown }>;
  submitEncounterAndTriage: (
    encounterEndpoint: string,
    encounterPayload: Record<string, unknown>,
    triageEndpoint: string,
    triagePayload: Record<string, unknown>,
  ) => Promise<SubmitOutcome>;
  syncNow: () => Promise<void>;
}

export function useOfflineSync(): OfflineSyncState {
  const [isOnline, setIsOnline] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  const refreshPendingCount = useCallback(async () => {
    setPendingCount((await listPending()).length);
  }, []);

  const syncNow = useCallback(async () => {
    if (!navigator.onLine) return;
    setSyncing(true);
    try {
      const result = await flushQueue();
      if (result.failed) {
        setLastError(`A queued item was rejected by the server and dropped: ${JSON.stringify(result.failed.detail)}`);
      }
      await refreshPendingCount();
    } finally {
      setSyncing(false);
    }
  }, [refreshPendingCount]);

  useEffect(() => {
    setIsOnline(navigator.onLine);
    refreshPendingCount();
    void syncNow();

    const handleOnline = () => {
      setIsOnline(true);
      void syncNow();
    };
    const handleOffline = () => setIsOnline(false);

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const wrappedSubmitCreatePatient = useCallback(
    async (endpoint: string, payload: Record<string, unknown>) => {
      const result = await submitCreatePatient(endpoint, payload);
      await refreshPendingCount();
      return result;
    },
    [refreshPendingCount],
  );

  const wrappedSubmitEncounterAndTriage = useCallback(
    async (
      encounterEndpoint: string,
      encounterPayload: Record<string, unknown>,
      triageEndpoint: string,
      triagePayload: Record<string, unknown>,
    ) => {
      const result = await submitEncounterAndTriage(encounterEndpoint, encounterPayload, triageEndpoint, triagePayload);
      await refreshPendingCount();
      return result;
    },
    [refreshPendingCount],
  );

  return {
    isOnline,
    pendingCount,
    syncing,
    lastError,
    submitCreatePatient: wrappedSubmitCreatePatient,
    submitEncounterAndTriage: wrappedSubmitEncounterAndTriage,
    syncNow,
  };
}
