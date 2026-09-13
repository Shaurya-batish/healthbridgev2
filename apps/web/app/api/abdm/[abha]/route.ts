import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

// Proxies Core's real AbdmGatewayClient-backed endpoint. Passes through
// Core's honest status codes as-is: 501 abdm_not_configured (no NHA
// credentials yet) or 502 abdm_unavailable (configured but the real call
// failed) — never fabricates a bundle. See docs/REAL-INTEGRATION-AUDIT.md.
export async function GET(_req: Request, { params }: { params: { abha: string } }) {
  try {
    const bundle = await coreRequest(`/abdm/patient/${encodeURIComponent(params.abha)}`, {
      headers: authHeader(getSessionToken()),
    });
    return NextResponse.json(bundle);
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "abdm_lookup_failed" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
