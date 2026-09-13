// Safe wrapper around coreRequest for facility Server Components. Every
// facility list page used to call coreRequest directly with no try/catch,
// so any Core/Postgres outage crashed the whole page with Next's raw dev
// error overlay ("Error: fetch failed") — a real bug found during the
// 2026-09-13 technical hardening pass. This gives every facility page a
// typed, exhaustively-handled result instead, so the page can render a
// plain-language fallback (see <FacilityUnavailable/>) rather than crash.
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

export type FacilityUnavailableReason = "unavailable" | "not_found" | "unauthorized" | "server_error";

export type FacilityFetchResult<T> = { ok: true; data: T } | { ok: false; reason: FacilityUnavailableReason };

export async function safeCoreRequest<T>(path: string): Promise<FacilityFetchResult<T>> {
  try {
    const data = (await coreRequest(path, { headers: authHeader(getSessionToken()) })) as T;
    return { ok: true, data };
  } catch (err) {
    if (err instanceof UpstreamError) {
      if (err.status === 404) return { ok: false, reason: "not_found" };
      if (err.status === 401 || err.status === 403) return { ok: false, reason: "unauthorized" };
      return { ok: false, reason: "server_error" };
    }
    // Not an UpstreamError -> Core itself was unreachable (connection
    // refused, DNS failure, timeout) rather than Core returning an error
    // response.
    return { ok: false, reason: "unavailable" };
  }
}
