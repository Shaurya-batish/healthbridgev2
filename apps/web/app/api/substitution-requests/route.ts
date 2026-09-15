import { NextResponse } from "next/server";
import { proxyPost } from "@/lib/gateway-proxy";

// A request only asks for review; Core guarantees it changes no prescription.
export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "invalid_json" }, { status: 400 });
  }
  return proxyPost("/substitution-requests", body, 201);
}
