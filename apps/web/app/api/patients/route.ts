import { NextResponse } from "next/server";
import { authHeader, coreRequest, idempotencyHeader, UpstreamError } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

export async function POST(req: Request) {
  const body = await req.json();
  try {
    const patient = await coreRequest("/patients", {
      method: "POST",
      headers: { ...authHeader(getSessionToken()), ...idempotencyHeader(req) },
      body: JSON.stringify(body),
    });
    return NextResponse.json(patient, { status: 201 });
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "create_patient_failed" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
