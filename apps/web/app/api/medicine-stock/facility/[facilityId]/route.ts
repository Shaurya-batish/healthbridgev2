import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(_req: Request, { params }: { params: { facilityId: string } }) {
  return proxyGet(`/medicine-stock/facility/${encodeURIComponent(params.facilityId)}`);
}
