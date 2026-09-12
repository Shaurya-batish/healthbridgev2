"use client";

import { createContext, useContext } from "react";
import { useOfflineSync, type OfflineSyncState } from "./useOfflineSync";

const OfflineSyncContext = createContext<OfflineSyncState | null>(null);

export function OfflineSyncProvider({ children }: { children: React.ReactNode }) {
  const state = useOfflineSync();
  return <OfflineSyncContext.Provider value={state}>{children}</OfflineSyncContext.Provider>;
}

export function useOffline(): OfflineSyncState {
  const ctx = useContext(OfflineSyncContext);
  if (!ctx) throw new Error("useOffline must be used within OfflineSyncProvider");
  return ctx;
}
