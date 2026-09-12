import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken, verifySession } from "@/lib/auth";

// Persists a triage decision — used both for the LLM path (after
// /api/triage/extract) and the offline checklist path where the client
// already ran the on-device rules-engine. Core is the only writer.
export async function POST(req: Request) {
  const body = await req.json();

  // actor_user_id for the audit log must come from the verified session, never
  // from client-supplied JSON — the client already omits it, but this closes
  // off spoofing a different actor even if a future form starts sending one.
  const token = getSessionToken();
  const session = token ? await verifySession(token) : null;
  const payload = { ...body, actor_user_id: session?.sub ?? null };

  try {
    const result = await coreRequest("/triage", {
      method: "POST",
      headers: authHeader(token),
      body: JSON.stringify(payload),
    });
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "triage_save_failed" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
