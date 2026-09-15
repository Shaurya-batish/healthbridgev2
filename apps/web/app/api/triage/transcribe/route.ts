import { NextResponse } from "next/server";
import { aiRequest } from "@/lib/ai-service";
import { transcribeViaAi } from "@/lib/ai-gateway";
import { getSessionToken, verifySession } from "@/lib/auth";

// Speech -> editable text (original language + Whisper's English
// translation). Returns 200 with either a transcript or a typed
// `transcription_unavailable` signal; the ASHA app turns the latter into a
// plain-language message and the checklist, never a spinner or a raw 503.
export async function POST(req: Request) {
  const token = getSessionToken();
  if (!token || !(await verifySession(token))) {
    return NextResponse.json({ detail: "missing_credentials" }, { status: 401 });
  }

  let payload: unknown;
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ transcription_unavailable: true, reason: "invalid_request" }, { status: 200 });
  }

  return NextResponse.json(await transcribeViaAi(payload, aiRequest), { status: 200 });
}
