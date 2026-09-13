import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(_req: Request, { params }: { params: { facilityId: string } }) {
  return proxyGet(`/teleconsults/facility/${encodeURIComponent(params.facilityId)}`);
}
