import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(_req: Request, { params }: { params: { patientId: string } }) {
  return proxyGet(`/referrals/patient/${encodeURIComponent(params.patientId)}`);
}
