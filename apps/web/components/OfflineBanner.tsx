"use client";

import { useOffline } from "@/lib/OfflineSyncProvider";

export function OfflineBanner() {
  const { isOnline, pendingCount, syncing, syncNow, lastError } = useOffline();

  if (isOnline && pendingCount === 0 && !lastError) return null;

  return (
    <div
      className={`sticky top-0 z-10 flex items-center justify-between gap-3 px-4 py-3 text-base ${
        isOnline ? "bg-amber-100 text-amber-900" : "bg-slate-800 text-white"
      }`}
      role="status"
    >
      <span>
        {!isOnline && "Offline — your information is saved on this phone. "}
        {pendingCount > 0 && `${pendingCount} item${pendingCount === 1 ? "" : "s"} waiting to sync. `}
        {lastError && <span className="font-semibold">{lastError}</span>}
      </span>
      {isOnline && pendingCount > 0 && (
        <button
          onClick={() => syncNow()}
          disabled={syncing}
          className="min-h-[44px] whitespace-nowrap rounded-lg bg-amber-900/10 px-4 text-base font-semibold hover:bg-amber-900/20 disabled:opacity-50"
        >
          {syncing ? "Syncing..." : "Sync now"}
        </button>
      )}
    </div>
  );
}
