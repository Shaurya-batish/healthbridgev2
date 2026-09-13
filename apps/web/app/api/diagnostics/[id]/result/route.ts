import { proxyPost } from "@/lib/gateway-proxy";

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const body = await req.json();
  return proxyPost(`/diagnostics/${encodeURIComponent(params.id)}/result`, body);
}
