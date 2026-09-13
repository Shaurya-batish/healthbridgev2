import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(_req: Request, { params }: { params: { patientId: string } }) {
  return proxyGet(`/follow-ups/patient/${encodeURIComponent(params.patientId)}`);
}
