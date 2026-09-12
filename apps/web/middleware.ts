import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, verifySession } from "./lib/auth";

export const config = {
  matcher: ["/asha/:path*", "/facility/:path*"],
};

export async function middleware(req: NextRequest) {
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const session = token ? await verifySession(token) : null;

  if (!session) {
    const loginUrl = new URL("/login", req.url);
    loginUrl.searchParams.set("next", req.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (req.nextUrl.pathname.startsWith("/asha") && session.role !== "asha") {
    return NextResponse.redirect(new URL("/facility", req.url));
  }

  if (
    req.nextUrl.pathname.startsWith("/facility") &&
    session.role !== "doctor" &&
    session.role !== "admin"
  ) {
    return NextResponse.redirect(new URL("/asha", req.url));
  }

  return NextResponse.next();
}
