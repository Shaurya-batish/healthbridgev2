import { NextResponse } from "next/server";
import { aiRequest } from "@/lib/ai-service";
import { extractViaAi } from "@/lib/ai-gateway";
import { getSessionToken, verifySession } from "@/lib/auth";

// Proxies the AI service's LLM-extract-then-rule-evaluate step. Per
// CONTRACT.md, an unreachable/unavailable AI service must never surface as a
// generic error here — the client (ASHA app) needs a clean signal to fall
// back to the on-device structured checklist, per CLAUDE.md's offline
// degradation rule. All of that mapping lives in lib/ai-gateway.ts, where it
// is unit tested against a transport that behaves like a stopped service.
export async function POST(req: Request) {
  const token = getSessionToken();
  if (!token || !(await verifySession(token))) {
    return NextResponse.json({ detail: "missing_credentials" }, { status: 401 });
  }

  let payload: unknown;
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ ai_unavailable: true }, { status: 200 });
  }

  return NextResponse.json(await extractViaAi(payload, aiRequest), { status: 200 });
}
