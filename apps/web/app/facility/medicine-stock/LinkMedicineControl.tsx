"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { MedicineSearch } from "@/components/medicines/MedicineSearch";
import { postAction } from "@/lib/action-result";
import type { MedicineSummary } from "@/lib/types";

/** Links an existing stock row to an imported medicine identity, so the
 * comparison can report this facility's real stock for it. */
export function LinkMedicineControl({ stockId, linkedLabel }: { stockId: string; linkedLabel: string | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function link(medicine: MedicineSummary | null) {
    setError(null);
    const failure = await postAction(`/api/medicine-stock/${stockId}/link`, { medicine_id: medicine?.id ?? null });
    if (failure) return setError(failure);
    setOpen(false);
    router.refresh();
  }

  return (
    <div className="mt-1 text-xs">
      {linkedLabel ? (
        <span className="text-slate-600">
          Linked to <span className="font-semibold">{linkedLabel}</span>{" "}
          <button onClick={() => void link(null)} className="font-semibold text-teal-800 hover:underline">
            Unlink
          </button>
        </span>
      ) : (
        !open && (
          <button onClick={() => setOpen(true)} className="font-semibold text-teal-800 hover:underline">
            Link to reference medicine
          </button>
        )
      )}
      {open && (
        <div className="mt-2 w-full max-w-md">
          <MedicineSearch onSelect={(m) => void link(m)} compact />
          <button onClick={() => setOpen(false)} className="mt-1 text-slate-500 hover:underline">
            Cancel
          </button>
        </div>
      )}
      {error && <p className="text-severity-red">{error}</p>}
    </div>
  );
}
