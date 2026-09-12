import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

// Segment is named [id] (not [facilityId]) only because Next.js requires a
// single dynamic slug name per path position, and app/api/escalations/[id]/acknowledge
// also lives here. Semantically this is a facility id.
export async function GET(_req: Request, { params }: { params: { id: string } }) {
  try {
    const escalations = await coreRequest(`/escalations/${encodeURIComponent(params.id)}`, {
      headers: authHeader(getSessionToken()),
    });
    return NextResponse.json(escalations);
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "escalations_unavailable" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
