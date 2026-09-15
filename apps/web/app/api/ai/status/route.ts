import { NextResponse } from "next/server";
import { aiRequest } from "@/lib/ai-service";
import { aiStatus } from "@/lib/ai-gateway";
import { getSessionToken, verifySession } from "@/lib/auth";

// Lets the ASHA app decide up front whether to offer voice capture, so a
// hosted build with the laptop off (or AI_MODE=degraded) says "voice isn't
// available here" before anyone records, instead of after. Exposes only
// capability booleans -- never the AI service URL.
export const dynamic = "force-dynamic";

export async function GET() {
  const token = getSessionToken();
  if (!token || !(await verifySession(token))) {
    return NextResponse.json({ detail: "missing_credentials" }, { status: 401 });
  }
  return NextResponse.json(await aiStatus(aiRequest));
}
