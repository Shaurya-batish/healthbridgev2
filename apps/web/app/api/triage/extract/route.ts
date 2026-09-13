import { NextResponse } from "next/server";
import { aiRequest, UpstreamError } from "@/lib/api-client";

// Proxies the AI service's LLM-extract-then-rule-evaluate step. Per
// CONTRACT.md, an unreachable/unavailable AI service must never surface as a
// generic error here — the client (ASHA app) needs a clean signal to fall
// back to the on-device structured checklist, per CLAUDE.md's offline
// degradation rule.
//
// This is intentionally not narrowed to just 503: a 4xx from a malformed
// request (e.g. input over the length limit), a 422 the model's schema
// rejects, or any other AI-side failure are all "the LLM path didn't
// produce a usable result" from the ASHA's perspective, and the checklist
// fallback is always safe to fall back to (the deterministic rule engine
// still runs either way) — never let a client trust a response that
// doesn't actually carry a severity.
export async function POST(req: Request) {
  const body = await req.json();

  try {
    const result = await aiRequest("/triage/extract", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json({ ai_unavailable: true }, { status: 200 });
    }
    // Network failure reaching the AI service (down, unreachable, timed out).
    return NextResponse.json({ ai_unavailable: true }, { status: 200 });
  }
}
