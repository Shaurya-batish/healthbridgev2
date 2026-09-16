import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(req: Request, { params }: { params: { patientId: string } }) {
  const facilityId = new URL(req.url).searchParams.get("facility_id") ?? "";
  return proxyGet(`/medication-orders/patient/${encodeURIComponent(params.patientId)}?facility_id=${encodeURIComponent(facilityId)}`);
}
