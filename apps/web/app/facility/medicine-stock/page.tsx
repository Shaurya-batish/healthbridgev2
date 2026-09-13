import { authHeader, coreRequest } from "@/lib/api-client";
import { getSessionToken } from "@/lib/auth";
import { requireFacilitySession } from "@/lib/server-session";
import { RefreshButton } from "@/components/RefreshButton";
import type { MedicineStock } from "@/lib/types";
import { AddMedicineForm } from "./AddMedicineForm";
import { AdjustStockControl } from "./AdjustStockControl";

export const dynamic = "force-dynamic";

export default async function MedicineStockPage() {
  const session = await requireFacilitySession();
  const items = (await coreRequest(`/medicine-stock/facility/${session.facility_id}`, {
    headers: authHeader(getSessionToken()),
  })) as MedicineStock[];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">Medicine stock</h1>
        <RefreshButton />
      </div>

      {items.length === 0 && <p className="mt-3 text-sm text-slate-400">No medicines stocked yet.</p>}

      <ul className="mt-3 divide-y divide-slate-100">
        {items.map((item) => {
          const low = item.quantity_on_hand <= item.reorder_threshold;
          return (
            <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <p className="text-sm font-semibold text-slate-800">{item.medicine_name}</p>
                <p className={`text-xs ${low ? "font-semibold text-severity-red" : "text-slate-400"}`}>
                  {item.quantity_on_hand} {item.unit} on hand
                  {low && " · below reorder threshold"}
                </p>
              </div>
              <AdjustStockControl stockId={item.id} />
            </li>
          );
        })}
      </ul>

      <AddMedicineForm facilityId={session.facility_id} />
    </div>
  );
}
