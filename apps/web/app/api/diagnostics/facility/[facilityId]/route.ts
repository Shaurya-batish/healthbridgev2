import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(_req: Request, { params }: { params: { facilityId: string } }) {
  return proxyGet(`/diagnostics/facility/${encodeURIComponent(params.facilityId)}`);
}
