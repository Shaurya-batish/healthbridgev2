import { NextResponse } from "next/server";
import { aiRequest, UpstreamError } from "@/lib/api-client";

// Proxies the AI service's LLM-extract-then-rule-evaluate step. Per
// CONTRACT.md, an unreachable/unavailable AI service must never surface as a
// generic error here — the client (ASHA app) needs a clean signal to fall
// back to the on-device structured checklist, per CLAUDE.md's offline
// degradation rule.
export async function POST(req: Request) {
  const body = await req.json();

  try {
    const result = await aiRequest("/triage/extract", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof UpstreamError && err.status === 503) {
      return NextResponse.json({ ai_unavailable: true }, { status: 200 });
    }
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "extract_failed" }, { status: err.status });
    }
    // Network failure reaching the AI service (down, unreachable, timed out)
    // — same fallback signal as an explicit 503.
    return NextResponse.json({ ai_unavailable: true }, { status: 200 });
  }
}
