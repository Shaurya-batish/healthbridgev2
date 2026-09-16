import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  return proxyGet(`/medicines/${encodeURIComponent(params.id)}`);
}
