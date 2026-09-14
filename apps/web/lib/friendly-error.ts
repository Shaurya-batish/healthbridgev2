// Translates raw API error payloads into plain-language sentences an ASHA
// can act on. CLAUDE.md ASHA UX rule 10: never show HTTP codes, DB errors,
// or JWT/validation internals — always say what happened and what to do.
const KNOWN_MESSAGES: Record<string, string> = {
  abha_number_already_registered: "A patient with this ABHA number is already registered. Try Find Patient instead.",
  patient_not_found: "No patient found with this ABHA number. Check the number, or register a new patient.",
  facility_not_found: "Your account isn't linked to a facility. Ask an admin to fix this before continuing.",
  // Sign-in failures reach the very first screen an ASHA sees, so the raw
  // code from Core must never be the visible text (CLAUDE.md ASHA UX rule 10).
  invalid_credentials: "That username or password isn't right. Check them and try again.",
  login_failed: "Sign-in didn't work. Check your username and password and try again.",
  missing_credentials: "Enter your username and password to sign in.",
  // These codes only ever reach friendlyErrorMessage on a REJECTED submit
  // (offline-queue.ts already handles the "queued for later" case separately
  // and never calls this function for it) -- so wording here must not claim
  // the data was saved, since it wasn't. CLAUDE.md rule 10: never mislead.
  core_unavailable: "We couldn't reach the server just now. Nothing was saved — please try again in a moment.",
  ai_unavailable: "We couldn't reach the server just now. Nothing was saved — please try again in a moment.",
  queue_unavailable: "We couldn't load the queue right now. Your saved information is safe — try again in a moment.",
};

function extractCode(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "detail" in detail) {
    const inner = (detail as { detail: unknown }).detail;
    if (typeof inner === "string") return inner;
  }
  return null;
}

/** Turns any error payload from our API routes into one plain sentence, safe to show an ASHA. */
export function friendlyErrorMessage(detail: unknown, fallback = "Something went wrong. Your information is safe — please try again."): string {
  const code = extractCode(detail);
  if (code && KNOWN_MESSAGES[code]) return KNOWN_MESSAGES[code];

  // FastAPI 422 validation errors: {detail: [{loc, msg, type}, ...]}
  const inner = detail && typeof detail === "object" && "detail" in detail ? (detail as { detail: unknown }).detail : detail;
  if (Array.isArray(inner) && inner.length > 0 && typeof inner[0] === "object" && inner[0] && "msg" in inner[0]) {
    return "Please check the information you entered and try again.";
  }

  return fallback;
}
