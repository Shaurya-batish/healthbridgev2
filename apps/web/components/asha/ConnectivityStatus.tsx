"use client";

import { useOffline } from "@/lib/OfflineSyncProvider";
import { IconWifiOff, IconCloudSync, IconCloudCheck } from "./icons";

/**
 * Always-visible, plain-language connectivity status for the ASHA home
 * screen (CLAUDE.md ASHA UX rule 6/9: obvious sync status, never a silent
 * failure). Icon + text + color, never color alone.
 */
export function ConnectivityStatus() {
  const { isOnline, pendingCount, syncing, syncNow } = useOffline();

  if (!isOnline) {
    return (
      <Banner tone="offline" icon={<IconWifiOff />}>
        <p className="font-semibold">Offline</p>
        <p className="text-sm opacity-90">Your information is saved on this phone. It will sync when you&apos;re back online.</p>
      </Banner>
    );
  }

  if (pendingCount > 0) {
    return (
      <Banner tone="pending" icon={<IconCloudSync className="h-6 w-6" />}>
        <p className="font-semibold">
          {syncing ? "Syncing..." : `Waiting to sync (${pendingCount})`}
        </p>
        <p className="text-sm opacity-90">
          {syncing ? "Sending saved information now." : "You're online. Tap to send saved information now."}
        </p>
        {!syncing && (
          <button
            onClick={() => syncNow()}
            className="mt-2 min-h-[44px] rounded-lg bg-amber-900/10 px-4 text-base font-semibold hover:bg-amber-900/20"
          >
            Sync now
          </button>
        )}
      </Banner>
    );
  }

  return (
    <Banner tone="synced" icon={<IconCloudCheck />}>
      <p className="font-semibold">All information synced</p>
    </Banner>
  );
}

function Banner({ tone, icon, children }: { tone: "offline" | "pending" | "synced"; icon: React.ReactNode; children: React.ReactNode }) {
  const toneClasses = {
    offline: "bg-slate-800 text-white",
    pending: "bg-amber-100 text-amber-900",
    synced: "bg-teal-50 text-teal-800",
  }[tone];

  return (
    <div className={`flex items-start gap-3 rounded-xl px-4 py-3 ${toneClasses}`} role="status">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div>{children}</div>
    </div>
  );
}
