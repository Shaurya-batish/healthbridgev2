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
      <div className="flex items-center gap-6">
        <span className="text-lg font-bold text-teal-800">{title}</span>
        <nav className="flex gap-4 text-sm font-medium text-slate-600">
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
