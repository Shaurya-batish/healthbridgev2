import { proxyPost } from "@/lib/gateway-proxy";

export async function POST(_req: Request, { params }: { params: { abha: string } }) {
  return proxyPost(`/patients/${encodeURIComponent(params.abha)}/verify-scheme`, {});
}
