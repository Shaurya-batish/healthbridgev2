import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

export async function GET(_req: Request, { params }: { params: { facilityId: string } }) {
  try {
    const queue = await coreRequest(`/queue/${encodeURIComponent(params.facilityId)}`, {
      headers: authHeader(getSessionToken()),
    });
    return NextResponse.json(queue);
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "queue_unavailable" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
