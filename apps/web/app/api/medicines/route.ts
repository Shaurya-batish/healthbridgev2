import { proxyGet } from "@/lib/gateway-proxy";

// Only the documented query parameters are forwarded; Core validates them.
export async function GET(req: Request) {
  const incoming = new URL(req.url).searchParams;
  const params = new URLSearchParams();
  for (const key of ["q", "limit", "offset"]) {
    const value = incoming.get(key);
    if (value !== null) params.set(key, value);
  }
  return proxyGet(`/medicines?${params.toString()}`);
}
