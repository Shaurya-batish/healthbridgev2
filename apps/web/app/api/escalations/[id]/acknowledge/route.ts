import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

export async function POST(_req: Request, { params }: { params: { id: string } }) {
  try {
    const result = await coreRequest(`/escalations/${encodeURIComponent(params.id)}/acknowledge`, {
      method: "POST",
      headers: authHeader(getSessionToken()),
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "acknowledge_failed" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
