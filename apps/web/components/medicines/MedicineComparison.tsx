"use client";

import { useCallback, useEffect, useState } from "react";
import {
  formatMoney,
  formLabel,
  insufficientReasonLabel,
  priceBasisLabel,
  releaseLabel,
  routeLabel,
  stockLabel,
  strengthLabel,
  unitPriceLabel,
} from "@/lib/medicine-format";
import type { MedicineSummary, SubstitutesResponse } from "@/lib/types";
import { MedicineSearch, describeHttpFailure } from "./MedicineSearch";

type LoadState = { status: "idle" } | { status: "loading" } | { status: "done"; data: SubstitutesResponse } | { status: "error"; message: string };

interface OrderContext {
  orderId: string;
  medicineId: string;
  patientLabel?: string;
}

/**
 * Informational same-composition comparison with real facility stock. When
 * opened for a specific prescription (`order`), each candidate offers
 * "Request doctor review" -- which creates a pending request and changes
 * nothing about the prescription.
 */
export function MedicineComparison({ facilityId, order }: { facilityId: string; order?: OrderContext }) {
  const [state, setState] = useState<LoadState>({ status: "idle" });
  const [requestMessage, setRequestMessage] = useState<Record<string, { ok: boolean; text: string }>>({});

  const load = useCallback(
    async (medicineId: string) => {
      setState({ status: "loading" });
      setRequestMessage({});
      try {
        const res = await fetch(`/api/medicines/${encodeURIComponent(medicineId)}/substitutes?facility_id=${encodeURIComponent(facilityId)}`);
        if (!res.ok) return setState({ status: "error", message: res.status === 404 ? "That medicine no longer exists in the imported data." : describeHttpFailure(res.status) });
        setState({ status: "done", data: (await res.json()) as SubstitutesResponse });
      } catch {
        setState({ status: "error", message: describeHttpFailure(502) });
      }
    },
    [facilityId],
  );

  const orderMedicineId = order?.medicineId;
  useEffect(() => {
    if (orderMedicineId) void load(orderMedicineId);
  }, [orderMedicineId, load]);

  async function requestReview(candidate: MedicineSummary) {
    if (!order) return;
    const res = await fetch("/api/substitution-requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order_id: order.orderId, proposed_medicine_id: candidate.id }),
    }).catch(() => null);
    let text = "Couldn't send the request. Nothing was changed — try again.";
    let ok = false;
    if (res?.status === 201) {
      ok = true;
      text = "Review requested. The prescription is unchanged until a doctor approves.";
    } else if (res) {
      const body = await res.json().catch(() => ({}));
      if (body.detail === "substitution_request_already_pending") text = "A review for this option is already pending.";
      else if (body.detail === "prescription_not_active") text = "This prescription is no longer active.";
      else if (body.detail === "not_a_same_composition_match") text = "This product no longer matches the prescription's composition.";
      else if (res.status === 403) text = describeHttpFailure(403);
    }
    setRequestMessage((m) => ({ ...m, [candidate.id]: { ok, text } }));
  }

  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" role="note">
        <strong>Informational only.</strong> Same listed ingredients, strength, form, route and release type does not by itself make two
        products interchangeable for a patient. Any substitution needs a clinician&apos;s review and approval.
      </p>

      {!order && <MedicineSearch onSelect={(m) => void load(m.id)} />}
      {order?.patientLabel && <p className="text-sm text-slate-600">Prescription for {order.patientLabel}</p>}

      <div aria-live="polite">
        {state.status === "loading" && <p className="text-sm text-slate-500">Loading comparison…</p>}
        {state.status === "error" && <p className="text-sm text-severity-red">{state.message}</p>}
      </div>

      {state.status === "done" && (
        <>
          <section aria-labelledby="reference-title" className="rounded-lg border-2 border-teal-700 bg-white p-4">
            <h2 id="reference-title" className="text-xs font-semibold uppercase tracking-wide text-teal-800">
              {order ? "Prescribed product" : "Selected product"}
            </h2>
            <MedicineDetails medicine={state.data.reference} />
            <StockBadge stock={state.data.reference_stock} />
          </section>

          {!state.data.comparable && (
            <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">
              Not compared: {state.data.not_comparable_reasons.map(insufficientReasonLabel).join("; ")}. Matching fails closed when the
              source data is incomplete or ambiguous.
            </p>
          )}
          {state.data.comparable && state.data.candidates.length === 0 && (
            <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">No other imported product has exactly the same composition, form, route and release type.</p>
          )}
          {state.data.reference.release_type === "not_stated" && state.data.candidates.length > 0 && (
            <p className="text-sm text-slate-600">
              The source does not state a release type for these products. The clinician must confirm immediate vs modified release.
            </p>
          )}

          {state.data.candidates.length > 0 && (
            <section aria-labelledby="candidates-title">
              <h2 id="candidates-title" className="text-sm font-semibold text-slate-700">
                Same-composition products (showing {state.data.candidates.length} of {state.data.total_candidates}) — in-stock first, then lowest
                comparable unit price
              </h2>
              <ul className="mt-2 space-y-3">
                {state.data.candidates.map((c) => (
                  <li key={c.medicine.id} className="rounded-lg border border-slate-200 bg-white p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <MedicineDetails medicine={c.medicine} />
                      {c.saving_percent !== null && (
                        <span className="rounded-full bg-severity-green-bg px-3 py-1 text-sm font-bold text-severity-green">{c.saving_percent}% lower unit price</span>
                      )}
                    </div>
                    {!c.price_comparable && <p className="mt-1 text-xs text-slate-500">Unit price not comparable on the same basis.</p>}
                    <StockBadge stock={c.stock} />
                    {order && (
                      <div className="mt-3">
                        <button
                          type="button"
                          onClick={() => void requestReview(c.medicine)}
                          className="min-h-[44px] rounded-lg border-2 border-teal-700 px-4 text-sm font-semibold text-teal-800 hover:bg-teal-50"
                        >
                          Request doctor review
                        </button>
                        {requestMessage[c.medicine.id] && (
                          <p className={`mt-2 text-sm ${requestMessage[c.medicine.id].ok ? "text-severity-green" : "text-severity-red"}`} role="status">
                            {requestMessage[c.medicine.id].text}
                          </p>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p className="text-xs text-slate-500">
            Source: {state.data.reference.source.name} ({state.data.reference.source.license}), version {state.data.reference.source.source_version ?? "unknown"}
            {state.data.reference.source.source_updated_on ? `, last updated ${state.data.reference.source.source_updated_on}` : ""}. Prices are as listed by the
            source and may not match current local prices.
          </p>
        </>
      )}
    </div>
  );
}

export function MedicineDetails({ medicine }: { medicine: MedicineSummary }) {
  const unit = unitPriceLabel(medicine);
  return (
    <div className="min-w-0">
      <p className="text-base font-semibold text-slate-800">
        {medicine.brand_name}
        {medicine.is_discontinued && <span className="ml-2 text-xs font-normal text-severity-red">discontinued</span>}
      </p>
      {medicine.manufacturer && <p className="text-xs text-slate-500">{medicine.manufacturer}</p>}
      <p className="mt-1 text-sm text-slate-700">{medicine.ingredients.map(strengthLabel).join(" + ") || "No ingredients listed"}</p>
      <p className="text-xs text-slate-600">
        {formLabel(medicine.dosage_form)} · {routeLabel(medicine.route)} · {releaseLabel(medicine.release_type)}
      </p>
      <p className="mt-1 text-sm text-slate-700">
        {medicine.pack_label ?? "Pack size not stated"}
        {medicine.price !== null && (
          <>
            {" · "}
            <span className="font-semibold">{formatMoney(medicine.price, medicine.currency)}</span>{" "}
            <span className="text-xs text-slate-500">{priceBasisLabel(medicine.price_basis)}</span>
          </>
        )}
      </p>
      <p className="text-sm text-slate-700">{unit ? `Comparable unit price: ${unit}` : "No comparable unit price (pack size or price missing)"}</p>
    </div>
  );
}

function StockBadge({ stock }: { stock: SubstitutesResponse["reference_stock"] }) {
  const label = stockLabel(stock);
  return <span className={`mt-2 inline-block rounded-full px-3 py-1 text-xs font-semibold ${label.tone}`}>{label.text}</span>;
}
