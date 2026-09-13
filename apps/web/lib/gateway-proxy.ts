// Shared plumbing for the many thin BFF routes that just proxy Core with
// the caller's session forwarded. Both client surfaces call only these
// gateway routes, never Core directly (architecture: "both clients talk
// only to the gateway").
import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

function upstreamErrorResponse(err: unknown): NextResponse {
  if (err instanceof UpstreamError) {
    return NextResponse.json(err.body ?? { detail: "upstream_error" }, { status: err.status });
  }
  return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
}

export async function proxyGet(path: string): Promise<NextResponse> {
  try {
    const body = await coreRequest(path, { headers: authHeader(getSessionToken()) });
    return NextResponse.json(body);
  } catch (err) {
    return upstreamErrorResponse(err);
  }
}

export async function proxyPost(path: string, payload: unknown, successStatus = 200): Promise<NextResponse> {
  try {
    const body = await coreRequest(path, {
      method: "POST",
      headers: authHeader(getSessionToken()),
      body: JSON.stringify(payload),
    });
    return NextResponse.json(body, { status: successStatus });
  } catch (err) {
    return upstreamErrorResponse(err);
  }
}
