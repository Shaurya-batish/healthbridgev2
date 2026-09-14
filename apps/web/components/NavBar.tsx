"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

export function NavBar({ title, links }: { title: string; links: Array<{ href: string; label: string }> }) {
  const router = useRouter();

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3">
      {/* flex-wrap on the inner row and the nav itself: the header wrapped, but
          the title+nav group inside it did not, so the nine facility links
          pushed the page 131px wider than a 768px tablet viewport. */}
      <div className="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-2">
        <span className="text-lg font-bold text-teal-800">{title}</span>
        <nav className="flex flex-wrap gap-x-4 gap-y-2 text-sm font-medium text-slate-600">
          {links.map((link) => (
            <Link key={link.href} href={link.href} className="hover:text-teal-700">
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
      <button onClick={logout} className="text-sm font-medium text-slate-500 hover:text-slate-800">
        Sign out
      </button>
    </header>
  );
}
