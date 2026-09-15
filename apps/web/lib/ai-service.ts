// Server-only: the live AI transport used by the /api/triage/* and
// /api/ai/status route handlers. Resolves the AI base URL per request (see
// ai-service-url.ts) and attaches the shared secret the tunnelled AI
// service requires.
import { authHeader, coreRequest, requestJson } from "./api-client";
import { createAiUrlResolver } from "./ai-service-url";
import { getSessionToken } from "./auth";

const resolver = createAiUrlResolver({
  envDefault: process.env.AI_SERVICE_URL ?? "http://localhost:8100",
  ttlMs: 15_000,
  async fetchOverride() {
    const token = getSessionToken();
    if (!token) return null;
    const body = (await coreRequest("/config/ai-service-url", { headers: authHeader(token) })) as { url?: unknown };
    return typeof body?.url === "string" && body.url ? body.url : null;
  },
});

export function invalidateAiServiceUrl(): void {
  resolver.invalidate();
}

/** `timeoutMs` bounds how long an ASHA can be left waiting on a slow or
 * half-dead AI host before the gateway gives up and the client falls back
 * to the checklist. A timeout surfaces as a thrown (non-Upstream) error. */
export async function aiRequest(path: string, init?: RequestInit, timeoutMs = 45_000): Promise<unknown> {
  const baseUrl = await resolver.resolve();
  const secret = process.env.AI_SHARED_SECRET;
  return requestJson(baseUrl, path, {
    ...init,
    headers: { ...init?.headers, ...(secret ? { "X-AI-Key": secret } : {}) },
    signal: AbortSignal.timeout(timeoutMs),
  });
}
