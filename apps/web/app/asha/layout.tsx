"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { OfflineSyncProvider } from "@/lib/OfflineSyncProvider";
import { OfflineBanner } from "@/components/OfflineBanner";
import { LanguageProvider, useI18n } from "@/lib/i18n/LanguageProvider";
import { languageLabel } from "@/lib/i18n/languages";
import { LanguageSelector } from "@/components/asha/LanguageSelector";

export default function AshaLayout({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      <OfflineSyncProvider>
        <AshaShell>{children}</AshaShell>
      </OfflineSyncProvider>
    </LanguageProvider>
  );
}

function AshaShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { t, language, setLanguage, uiReviewStatus } = useI18n();

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen bg-slate-50 text-base">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-2 py-2">
        <Link href="/asha" className="flex min-h-[44px] items-center rounded-lg px-2 text-xl font-bold text-teal-800 active:bg-slate-100">
          HealthBridge
        </Link>
        <div className="flex items-center gap-1">
          <LanguageSelector id="ui-language" label={t("language.uiLabel")} value={language} onChange={setLanguage} compact />
          <button onClick={logout} className="min-h-[44px] rounded-lg px-3 text-base font-semibold text-slate-600 active:bg-slate-100">
            Sign out
          </button>
        </div>
      </header>
      {uiReviewStatus === "unreviewed_draft" && (
        <p className="bg-slate-100 px-4 py-1.5 text-center text-sm text-slate-600">{t("i18n.draftNotice", { language: languageLabel(language) })}</p>
      )}
      <OfflineBanner />
      <main className="mx-auto w-full max-w-md px-4 py-5 pb-16">{children}</main>
    </div>
  );
}
