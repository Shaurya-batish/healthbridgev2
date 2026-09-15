import { requireFacilitySession } from "@/lib/server-session";
import { safeCoreRequest } from "@/lib/facility-data";
import { FacilityUnavailable } from "@/components/FacilityUnavailable";
import { MedicineComparison } from "@/components/medicines/MedicineComparison";
import type { MedicationOrder } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function FacilityMedicinesPage({ searchParams }: { searchParams: { order?: string } }) {
  const session = await requireFacilitySession();
  const orderResult = searchParams.order ? await safeCoreRequest<MedicationOrder>(`/medication-orders/${encodeURIComponent(searchParams.order)}`) : null;
  const order = orderResult?.ok ? orderResult.data : null;

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-5">
      <h1 className="text-lg font-semibold text-slate-800">Same-composition medicine comparison</h1>
      {orderResult && !orderResult.ok && <FacilityUnavailable reason={orderResult.reason} />}
      {order && order.status !== "active" && (
        <p className="text-sm text-slate-600">This prescription is {order.status}; review requests are only possible for active prescriptions.</p>
      )}
      <MedicineComparison
        facilityId={session.facility_id}
        order={order && order.status === "active" ? { orderId: order.id, medicineId: order.medicine.id } : undefined}
      />
    </div>
  );
}
