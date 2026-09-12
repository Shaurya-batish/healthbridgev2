import { getSessionToken, verifySession, type SessionClaims } from "./auth";

/** Reads and verifies the caller's session in a Server Component or route handler. */
export async function requireFacilitySession(): Promise<SessionClaims & { facility_id: string }> {
  const token = getSessionToken();
  const session = token ? await verifySession(token) : null;
  if (!session?.facility_id) {
    throw new Error("no_facility_session");
  }
  return session as SessionClaims & { facility_id: string };
}
