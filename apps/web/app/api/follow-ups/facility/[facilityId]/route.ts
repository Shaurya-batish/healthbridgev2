import { proxyGet } from "@/lib/gateway-proxy";

export async function GET(req: Request, { params }: { params: { facilityId: string } }) {
  const dueBy = new URL(req.url).searchParams.get("due_by");
  const query = dueBy ? `?due_by=${encodeURIComponent(dueBy)}` : "";
  return proxyGet(`/follow-ups/facility/${encodeURIComponent(params.facilityId)}${query}`);
}
