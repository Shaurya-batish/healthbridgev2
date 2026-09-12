import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

// Proxies Core's MockAbdmClient-backed endpoint. Real ABDM gateway swap-in
// happens behind that adapter later — nothing here changes when it does.
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
