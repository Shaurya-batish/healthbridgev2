import { NextResponse } from "next/server";
import { authHeader, CORE_SERVICE_URL } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";

// Real file passthrough -- the multipart upload and the binary download
// both stream straight through to Core rather than being parsed/rebuilt
// here, so the bytes a doctor plays back are exactly the bytes the ASHA
// recorded (checksum-verified server-side in Core).

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const contentType = req.headers.get("content-type");
  if (!contentType) {
    return NextResponse.json({ detail: "missing_content_type" }, { status: 400 });
  }

  let res: Response;
  try {
    res = await fetch(`${CORE_SERVICE_URL}/teleconsults/${encodeURIComponent(params.id)}/media`, {
      method: "POST",
      headers: { "Content-Type": contentType, ...authHeader(getSessionToken()) },
      body: req.body,
      // @ts-expect-error -- required by Node's fetch when streaming a request body
      duplex: "half",
    });
  } catch {
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }

  const body = await res.text();
  return new NextResponse(body, { status: res.status, headers: { "Content-Type": "application/json" } });
}

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  let res: Response;
  try {
    res = await fetch(`${CORE_SERVICE_URL}/teleconsults/${encodeURIComponent(params.id)}/media`, {
      headers: authHeader(getSessionToken()),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }

  if (!res.ok) {
    const body = await res.text();
    return new NextResponse(body, { status: res.status, headers: { "Content-Type": "application/json" } });
  }

  return new NextResponse(res.body, {
    status: 200,
    headers: { "Content-Type": res.headers.get("content-type") ?? "application/octet-stream" },
  });
}
