import { proxyPost } from "@/lib/gateway-proxy";

// Clinician authorisation is enforced by Core (doctor role + facility scope),
// not by this route or the UI.
export async function POST(req: Request, { params }: { params: { id: string } }) {
  const body = await req.json().catch(() => ({}));
  return proxyPost(`/substitution-requests/${encodeURIComponent(params.id)}/approve`, body);
}
