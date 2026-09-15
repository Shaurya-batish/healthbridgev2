import { NextResponse } from "next/server";
import { aiRequest } from "@/lib/ai-service";
import { translateViaAi } from "@/lib/ai-gateway";
import { getSessionToken, verifySession } from "@/lib/auth";

// Typed complaint (selected language) -> machine English for the ASHA to
// check and confirm. Always 200 with either a translation or a typed
// `translation_unavailable` reason, so the app can offer manual English
// entry, voice, or the checklist instead of a dead end.
export async function POST(req: Request) {
  const token = getSessionToken();
  if (!token || !(await verifySession(token))) {
    return NextResponse.json({ detail: "missing_credentials" }, { status: 401 });
  }

  let payload: unknown;
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ translation_unavailable: true, reason: "invalid_request" }, { status: 200 });
  }

  return NextResponse.json(await translateViaAi(payload, aiRequest), { status: 200 });
}
