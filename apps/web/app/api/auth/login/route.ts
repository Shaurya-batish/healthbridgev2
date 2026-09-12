import { NextResponse } from "next/server";
import { coreRequest, UpstreamError } from "@/lib/api-client";
import { SESSION_COOKIE } from "@/lib/auth";

export async function POST(req: Request) {
  const body = await req.json();

  try {
    const result = (await coreRequest("/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    })) as { token: string; role: string; facility_id: string | null };

    const res = NextResponse.json({ role: result.role, facility_id: result.facility_id });
    res.cookies.set(SESSION_COOKIE, result.token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 12,
    });
    return res;
  } catch (err) {
    if (err instanceof UpstreamError) {
      return NextResponse.json(err.body ?? { detail: "login_failed" }, { status: err.status });
    }
    return NextResponse.json({ detail: "core_unavailable" }, { status: 502 });
  }
}
