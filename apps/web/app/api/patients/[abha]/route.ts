import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

export async function GET(_req: Request, { params }: { params: { abha: string } }) {
  try {
    const patient = await coreRequest(`/patients/${encodeURIComponent(params.abha)}`, {
      headers: authHeader(getSessionToken()),
    });
    return NextResponse.json(patient);
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "not_found" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
