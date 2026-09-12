import type { SchemeStatus } from "@/lib/types";

const LABELS: Record<SchemeStatus, string> = {
  PMJAY: "PM-JAY",
  state: "State scheme",
  none: "No scheme on record",
};

const STYLES: Record<SchemeStatus, string> = {
  PMJAY: "bg-teal-100 text-teal-800 border-teal-300",
  state: "bg-indigo-100 text-indigo-800 border-indigo-300",
  none: "bg-slate-100 text-slate-600 border-slate-300",
};

// A status badge only — per CLAUDE.md, scheme verification is a convincing
// mock, not a verification engine. Do not add eligibility logic here.
export function SchemeBadge({ status }: { status: SchemeStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${STYLES[status]}`}>
      {LABELS[status]}
    </span>
  );
}
