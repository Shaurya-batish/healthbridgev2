import { proxyGet } from "@/lib/gateway-proxy";

// Core enforces that the caller may access facility_id.
export async function GET(req: Request, { params }: { params: { id: string } }) {
  const facilityId = new URL(req.url).searchParams.get("facility_id") ?? "";
  return proxyGet(`/medicines/${encodeURIComponent(params.id)}/substitutes?facility_id=${encodeURIComponent(facilityId)}`);
}
