import type { Severity } from "@/lib/types";

const STYLES: Record<Severity, string> = {
  RED: "bg-severity-red-bg text-severity-red border-severity-red",
  YELLOW: "bg-severity-yellow-bg text-severity-yellow border-severity-yellow",
  GREEN: "bg-severity-green-bg text-severity-green border-severity-green",
};

export function SeverityBadge({ severity, className = "" }: { severity: Severity; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-semibold uppercase tracking-wide ${STYLES[severity]} ${className}`}
    >
      <span className="h-2 w-2 rounded-full bg-current" />
      {severity}
    </span>
  );
}
