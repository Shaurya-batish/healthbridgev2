import { jwtVerify } from "jose";
import { cookies } from "next/headers";
import type { Role } from "./types";

export const SESSION_COOKIE = "healthbridge_session";

export interface SessionClaims {
  sub: string;
  role: Role;
  facility_id: string | null;
}

function getSecret(): Uint8Array {
  const secret = process.env.JWT_SECRET;
  if (!secret) {
    throw new Error("JWT_SECRET is not set");
  }
  return new TextEncoder().encode(secret);
}

/**
 * Verifies a JWT issued by the Core service. Used both in middleware (edge
 * runtime) and route handlers — jose works in both.
 */
export async function verifySession(token: string): Promise<SessionClaims | null> {
  try {
    const { payload } = await jwtVerify(token, getSecret());
    if (typeof payload.sub !== "string" || typeof payload.role !== "string") return null;
    return {
      sub: payload.sub,
      role: payload.role as Role,
      facility_id: (payload.facility_id as string) ?? null,
    };
  } catch {
    return null;
  }
}

/** Reads the raw session cookie in a route handler (server-only). */
export function getSessionToken(): string | undefined {
  return cookies().get(SESSION_COOKIE)?.value;
}
