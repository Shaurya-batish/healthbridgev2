import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  return proxyGet(`/medicine-stock/${encodeURIComponent(params.id)}/movements`);
}
