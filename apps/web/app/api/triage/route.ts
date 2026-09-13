import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

// Persists a triage decision — used both for the LLM path (after
// /api/triage/extract) and the offline checklist path where the client
// already ran the on-device rules-engine. Core is the only writer.
//
// The audit log's actor is derived by Core itself from the verified
// Authorization header (see services/core/app/routers/triage.py), never
// from anything in this request body — that's what actually prevents an
// actor-spoofing audit entry, not client-side omission.
export async function POST(req: Request) {
  const body = await req.json();
  const token = getSessionToken();

  try {
    const result = await coreRequest("/triage", {
      method: "POST",
      headers: authHeader(token),
      body: JSON.stringify(body),
    });
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "triage_save_failed" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
