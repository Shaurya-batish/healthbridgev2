import { proxyPost } from "@/lib/gateway-proxy";

export async function POST(req: Request) {
  const body = await req.json();
  return proxyPost("/medicine-stock", body, 201);
}
