import { redirect } from "next/navigation";
import { getSessionToken, verifySession } from "@/lib/auth";

export default async function RootPage() {
  const token = getSessionToken();
  const session = token ? await verifySession(token) : null;

  if (!session) redirect("/login");
  if (session.role === "asha") redirect("/asha");
  redirect("/facility");
}
