"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { OfflineSyncProvider } from "@/lib/OfflineSyncProvider";
import { OfflineBanner } from "@/components/OfflineBanner";

export default function AshaLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  return (
    <OfflineSyncProvider>
      <div className="min-h-screen bg-slate-50 text-base">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-2 py-2">
          <Link href="/asha" className="flex min-h-[44px] items-center rounded-lg px-2 text-xl font-bold text-teal-800 active:bg-slate-100">
            HealthBridge
          </Link>
          <button
            onClick={logout}
            className="min-h-[44px] rounded-lg px-3 text-base font-semibold text-slate-600 active:bg-slate-100"
          >
            Sign out
          </button>
        </header>
        <OfflineBanner />
        <main className="mx-auto w-full max-w-md px-4 py-5 pb-16">{children}</main>
      </div>
    </OfflineSyncProvider>
  );
}
