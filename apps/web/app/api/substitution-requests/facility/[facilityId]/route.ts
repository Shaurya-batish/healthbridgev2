import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(req: Request, { params }: { params: { facilityId: string } }) {
  const status = new URL(req.url).searchParams.get("status");
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return proxyGet(`/substitution-requests/facility/${encodeURIComponent(params.facilityId)}${query}`);
}
