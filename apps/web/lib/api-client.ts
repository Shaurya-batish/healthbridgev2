// Server-side fetch helpers used by BFF route handlers (app/api/**) to talk
// to the Core and AI services. Route handlers are the ONLY place these are
// used — client components never import this file, they call /api/** on
// this same Next.js app, per the architecture ("both clients talk only to
// the gateway"). The AI transport lives in ai-service.ts, because its base
// URL is resolved per request rather than read once from the environment.

export const CORE_SERVICE_URL = process.env.CORE_SERVICE_URL ?? "http://localhost:8000";

export class UpstreamError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`Upstream service responded with ${status}`);
  }
}

export async function requestJson(baseUrl: string, path: string, init?: RequestInit): Promise<unknown> {
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });

  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    // A non-JSON body (an HTML error page from a proxy or a dead tunnel) is
    // an upstream failure, not a gateway crash.
    throw new UpstreamError(res.ok ? 502 : res.status, { detail: "non_json_upstream_response" });
  }

  if (!res.ok) {
    throw new UpstreamError(res.status, body);
  }

  return body;
}

export function coreRequest(path: string, init?: RequestInit): Promise<unknown> {
  return requestJson(CORE_SERVICE_URL, path, init);
}

export function authHeader(token: string | undefined): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Forwards a client-supplied Idempotency-Key straight through to Core --
 * see services/core/app/idempotency.py. Absent header -> no replay
 * protection for that request, never an error. */
export function idempotencyHeader(req: Request): Record<string, string> {
  const key = req.headers.get("Idempotency-Key");
  return key ? { "Idempotency-Key": key } : {};
}
