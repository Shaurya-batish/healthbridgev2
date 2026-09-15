import { describe, expect, it, vi } from "vitest";
import { createAiUrlResolver } from "./ai-service-url";

describe("createAiUrlResolver", () => {
  it("prefers the admin-set Redis override over the env default", async () => {
    const r = createAiUrlResolver({
      fetchOverride: async () => "https://abc.trycloudflare.com",
      envDefault: "http://localhost:8100",
      ttlMs: 10_000,
    });
    await expect(r.resolve()).resolves.toBe("https://abc.trycloudflare.com");
  });

  it("falls back to the env default when no override is set", async () => {
    const r = createAiUrlResolver({ fetchOverride: async () => null, envDefault: "http://localhost:8100", ttlMs: 10_000 });
    await expect(r.resolve()).resolves.toBe("http://localhost:8100");
  });

  it("falls back to the env default when Core is unreachable, without throwing", async () => {
    const r = createAiUrlResolver({
      fetchOverride: async () => {
        throw new Error("core down");
      },
      envDefault: "http://localhost:8100",
      ttlMs: 10_000,
    });
    await expect(r.resolve()).resolves.toBe("http://localhost:8100");
  });

  it("caches within the TTL, refetches after it, and invalidate() forces a refetch", async () => {
    let t = 0;
    let value = "https://one.trycloudflare.com";
    const fetchOverride = vi.fn(async () => value);
    const r = createAiUrlResolver({ fetchOverride, envDefault: "http://x", ttlMs: 1000, now: () => t });

    await r.resolve();
    value = "https://two.trycloudflare.com";
    t = 999;
    await expect(r.resolve()).resolves.toBe("https://one.trycloudflare.com");
    expect(fetchOverride).toHaveBeenCalledTimes(1);

    t = 1000;
    await expect(r.resolve()).resolves.toBe("https://two.trycloudflare.com");
    expect(fetchOverride).toHaveBeenCalledTimes(2);

    value = "https://three.trycloudflare.com";
    r.invalidate();
    await expect(r.resolve()).resolves.toBe("https://three.trycloudflare.com");
    expect(fetchOverride).toHaveBeenCalledTimes(3);
  });
});
