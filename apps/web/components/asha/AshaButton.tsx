import Link from "next/link";
import type { ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "outline";

const VARIANT_STYLES: Record<Variant, string> = {
  primary: "bg-teal-700 text-white active:bg-teal-800 disabled:bg-teal-700/50",
  secondary: "bg-slate-100 text-slate-800 active:bg-slate-200 disabled:opacity-50",
  danger: "bg-red-700 text-white active:bg-red-800 disabled:opacity-50",
  outline: "border-2 border-slate-300 bg-white text-slate-800 active:bg-slate-50 disabled:opacity-50",
};

const sharedClasses =
  "flex min-h-[64px] w-full items-center justify-center gap-3 rounded-2xl px-5 text-lg font-semibold shadow-sm transition-colors";

interface AshaButtonProps {
  children: ReactNode;
  href?: string;
  onClick?: () => void;
  type?: "button" | "submit";
  variant?: Variant;
  disabled?: boolean;
  icon?: ReactNode;
}

/** Large, thumb-friendly action control shared across the ASHA app — never a small icon-only tap target. */
export function AshaButton({ children, href, onClick, type = "button", variant = "primary", disabled, icon }: AshaButtonProps) {
  const classes = `${sharedClasses} ${VARIANT_STYLES[variant]} ${disabled ? "pointer-events-none" : ""}`;

  if (href && !disabled) {
    return (
      <Link href={href} className={classes}>
        {icon}
        <span>{children}</span>
      </Link>
    );
  }

  return (
    <button type={type} onClick={onClick} disabled={disabled} className={classes}>
      {icon}
      <span>{children}</span>
    </button>
  );
}
