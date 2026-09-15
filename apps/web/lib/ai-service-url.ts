// Resolves the AI service base URL at REQUEST time. The laptop's Cloudflare
// quick-tunnel URL changes on every restart, so a build-time env var can't
// be the source of truth: an admin repoints it through
// POST /api/admin/ai-service-url, which Core stores in Redis under
// `config:ai_service_url`. The AI_SERVICE_URL env var is only the fallback.
//
// Cached briefly so an ASHA's request doesn't cost an extra Core round trip
// every time. Each gateway instance caches independently, so a repoint can
// take up to `ttlMs` to reach every serverless instance.

export interface AiUrlResolverDeps {
  /** Returns the admin-set override, or null when none is set. May throw. */
  fetchOverride: () => Promise<string | null>;
  envDefault: string;
  ttlMs: number;
  now?: () => number;
}

export interface AiUrlResolver {
  resolve: () => Promise<string>;
  invalidate: () => void;
}

export function createAiUrlResolver(deps: AiUrlResolverDeps): AiUrlResolver {
  const now = deps.now ?? Date.now;
  let cached: { url: string; at: number } | null = null;

  return {
    async resolve() {
      if (cached && now() - cached.at < deps.ttlMs) return cached.url;
      let url = deps.envDefault;
      try {
        const override = await deps.fetchOverride();
        if (override) url = override;
      } catch {
        // Core or Redis unreachable: fall back to the env default rather than
        // blocking triage. The AI call itself then succeeds or degrades.
      }
      cached = { url, at: now() };
      return url;
    },
    invalidate() {
      cached = null;
    },
  };
}
