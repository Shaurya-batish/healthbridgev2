import { NextResponse } from "next/server";
import { proxyGet, proxyPost } from "@/lib/gateway-proxy";
import { invalidateAiServiceUrl } from "@/lib/ai-service";

// Repoint the AI service (e.g. a fresh Cloudflare quick-tunnel URL) without
// a redeploy. Core enforces admin-only and writes the audit_log row; this
// route only forwards and drops this instance's cached URL on success.
export async function GET() {
  return proxyGet("/config/ai-service-url");
}

export async function POST(req: Request) {
  let payload: unknown;
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ detail: "invalid_json" }, { status: 400 });
  }
  const res = await proxyPost("/config/ai-service-url", payload);
  if (res.ok) invalidateAiServiceUrl();
  return res;
}
