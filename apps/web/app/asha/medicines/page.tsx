import { authHeader, coreRequest, UpstreamError } from "@/lib/api-client";
import { getSessionToken, verifySession } from "@/lib/auth";
import { MedicineComparison } from "@/components/medicines/MedicineComparison";
import { IconAlertTriangle } from "@/components/asha/icons";
import type { MedicationOrder } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function AshaMedicinesPage({ searchParams }: { searchParams: { order?: string } }) {
  const token = getSessionToken();
  const session = token ? await verifySession(token) : null;
  if (!session?.facility_id) {
    return (
      <div className="flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-5 text-amber-900">
        <IconAlertTriangle className="mt-0.5 h-6 w-6 shrink-0" />
        <p className="text-lg">Your account has no facility assigned, so facility stock can&apos;t be shown.</p>
      </div>
    );
  }

  let order: MedicationOrder | null = null;
  let orderError: string | null = null;
  if (searchParams.order) {
    try {
      order = (await coreRequest(`/medication-orders/${encodeURIComponent(searchParams.order)}`, { headers: authHeader(token) })) as MedicationOrder;
    } catch (err) {
      orderError =
        err instanceof UpstreamError && err.status === 403
          ? "You don't have access to this prescription."
          : err instanceof UpstreamError && err.status === 404
            ? "Prescription not found."
            : "Couldn't load the prescription right now.";
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-800">Compare medicines</h1>
      {orderError && <p className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-amber-900">{orderError}</p>}
      {order && order.status !== "active" && (
        <p className="rounded-xl bg-slate-100 p-3 text-slate-700">
          This prescription is {order.status}. A review can only be requested for an active prescription.
        </p>
      )}
      <MedicineComparison
        facilityId={session.facility_id}
        order={order && order.status === "active" ? { orderId: order.id, medicineId: order.medicine.id } : undefined}
      />
    </div>
  );
}
