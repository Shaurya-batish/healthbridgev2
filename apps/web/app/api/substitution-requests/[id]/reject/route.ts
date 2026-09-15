import { proxyPost } from "@/lib/gateway-proxy";

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const body = await req.json().catch(() => ({}));
  return proxyPost(`/substitution-requests/${encodeURIComponent(params.id)}/reject`, body);
}
