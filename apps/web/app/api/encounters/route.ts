import { NextResponse } from "next/server";
import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

export async function POST(req: Request) {
  const body = await req.json();
  try {
    const encounter = await coreRequest("/encounters", {
      method: "POST",
      headers: authHeader(getSessionToken()),
      body: JSON.stringify(body),
    });
    return NextResponse.json(encounter, { status: 201 });
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "create_encounter_failed" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
