import { NextResponse } from "next/server";
import { proxyPost } from "@/lib/gateway-proxy";

export async function POST(req: Request, { params }: { params: { id: string } }) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "invalid_json" }, { status: 400 });
  }
  return proxyPost(`/medicine-stock/${encodeURIComponent(params.id)}/link`, body);
}
