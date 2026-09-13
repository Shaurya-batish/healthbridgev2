import { RefreshButton } from "@/components/RefreshButton";
import type { FacilityUnavailableReason } from "@/lib/facility-data";

const MESSAGES: Record<FacilityUnavailableReason, string> = {
  unavailable: "We can't reach the server right now. Please check your connection and try again.",
  server_error: "Something went wrong loading this page. Please try again in a moment.",
  unauthorized: "Your session isn't valid for this page. Try signing out and back in.",
  not_found: "Nothing found.",
};

/** Plain-language fallback for any facility page whose Core call failed — never a raw stack trace or HTTP status. */
export function FacilityUnavailable({ reason }: { reason: FacilityUnavailableReason }) {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-5 text-sm text-amber-900">
      <div className="flex items-center justify-between gap-3">
        <p>{MESSAGES[reason]}</p>
        <RefreshButton />
      </div>
    </div>
  );
}
