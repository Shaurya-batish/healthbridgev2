// Server-side fetch helpers used by BFF route handlers (app/api/**) to talk
// to the Core and AI services. Route handlers are the ONLY place these are
// used — client components never import this file, they call /api/** on
// this same Next.js app, per the architecture ("both clients talk only to
// the gateway").

const CORE_SERVICE_URL = process.env.CORE_SERVICE_URL ?? "http://localhost:8000";
const AI_SERVICE_URL = process.env.AI_SERVICE_URL ?? "http://localhost:8100";

export class UpstreamError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`Upstream service responded with ${status}`);
  }
}

async function request(baseUrl: string, path: string, init?: RequestInit): Promise<unknown> {
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });

  const text = await res.text();
  const body = text ? JSON.parse(text) : null;

  if (!res.ok) {
    throw new UpstreamError(res.status, body);
  }

  return body;
}

export function coreRequest(path: string, init?: RequestInit): Promise<unknown> {
  return request(CORE_SERVICE_URL, path, init);
}

export function aiRequest(path: string, init?: RequestInit): Promise<unknown> {
  return request(AI_SERVICE_URL, path, init);
}

export function authHeader(token: string | undefined): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}
