"use client";

import { useOffline } from "@/lib/OfflineSyncProvider";

export function OfflineBanner() {
  const { isOnline, pendingCount, syncing, syncNow, lastError } = useOffline();

  if (isOnline && pendingCount === 0 && !lastError) return null;

  return (
    <div
      className={`sticky top-0 z-10 flex items-center justify-between gap-3 px-4 py-2 text-sm ${
        isOnline ? "bg-amber-100 text-amber-900" : "bg-slate-800 text-white"
      }`}
    >
      <span>
        {!isOnline && "Offline — your work is saved on this device. "}
        {pendingCount > 0 && `${pendingCount} item${pendingCount === 1 ? "" : "s"} waiting to sync. `}
        {lastError && <span className="font-semibold">{lastError}</span>}
      </span>
      {isOnline && pendingCount > 0 && (
        <button
          onClick={() => syncNow()}
          disabled={syncing}
          className="whitespace-nowrap rounded bg-amber-900/10 px-2 py-1 text-xs font-semibold hover:bg-amber-900/20 disabled:opacity-50"
        >
          {syncing ? "Syncing..." : "Sync now"}
        </button>
      )}
    </div>
  );
}
