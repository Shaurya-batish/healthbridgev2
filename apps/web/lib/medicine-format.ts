// Display helpers for imported medicine data. Pure and tested. Values come
// from Core as strings; nothing here recomputes prices or savings -- Core owns
// those rules (services/core/app/salt_matching.py).
import type { FacilityStockInfo, MedicineIngredient, MedicineSummary } from "./types";

const CURRENCY_SYMBOL: Record<string, string> = { INR: "₹" };

export function formatMoney(amount: string | null, currency: string): string | null {
  if (amount === null || amount === "") return null;
  const symbol = CURRENCY_SYMBOL[currency] ?? `${currency} `;
  return `${symbol}${amount}`;
}

export function priceBasisLabel(basis: string): string {
  if (basis === "mrp") return "MRP";
  if (basis === "selling_price") return "Selling price";
  return "Listed price (source does not say MRP or selling price)";
}

const UNIT_WORD: Record<string, string> = { unit: "per tablet/capsule", mL: "per mL", g: "per g" };

export function unitPriceLabel(medicine: Pick<MedicineSummary, "unit_price" | "pack_unit" | "currency">): string | null {
  const money = formatMoney(medicine.unit_price, medicine.currency);
  if (!money || !medicine.pack_unit) return null;
  return `${money} ${UNIT_WORD[medicine.pack_unit] ?? ""}`.trim();
}

const FORM_LABEL: Record<string, string> = {
  tablet: "Tablet",
  tablet_dispersible: "Dispersible tablet",
  tablet_mouth_dissolving: "Mouth-dissolving tablet",
  tablet_chewable: "Chewable tablet",
  tablet_effervescent: "Effervescent tablet",
  capsule: "Capsule",
  capsule_soft_gelatin: "Soft gelatin capsule",
  syrup: "Syrup",
  dry_syrup: "Dry syrup",
  suspension: "Suspension",
  oral_solution: "Oral solution",
  oral_drops: "Oral drops",
  eye_drops: "Eye drops",
  eye_ointment: "Eye ointment",
  ear_drops: "Ear drops",
  nasal_drops: "Nasal drops",
  nasal_spray: "Nasal spray",
  cream: "Cream",
  ointment: "Ointment",
  gel: "Gel",
  lotion: "Lotion",
  injection: "Injection",
  drops: "Drops",
  solution: "Solution",
};

export function formLabel(form: string | null): string {
  return form ? (FORM_LABEL[form] ?? form) : "Form not stated";
}

export function routeLabel(route: string | null): string {
  return route ? route.charAt(0).toUpperCase() + route.slice(1) : "Route not stated";
}

export function releaseLabel(release: string): string {
  if (release === "not_stated") return "Release type not stated by source";
  return `${release.toUpperCase().split("+").join(" + ")} (modified release)`;
}

export function strengthLabel(ingredient: MedicineIngredient): string {
  const name = ingredient.name.replace(/\b\w/g, (c) => c.toUpperCase());
  return ingredient.strength_value ? `${name} ${ingredient.strength_value} ${ingredient.strength_unit ?? ""}`.trim() : `${name} (strength not stated)`;
}

export function stockLabel(stock: FacilityStockInfo): { text: string; tone: string } {
  switch (stock.status) {
    case "available":
      return { text: `In stock here (${stock.quantity_on_hand})`, tone: "bg-severity-green-bg text-severity-green" };
    case "unavailable":
      return { text: "Out of stock here", tone: "bg-severity-red-bg text-severity-red" };
    case "stale": {
      const when = stock.last_counted_at ? new Date(stock.last_counted_at).toLocaleDateString() : "unknown date";
      return { text: `Stock count out of date (last ${when})`, tone: "bg-amber-100 text-amber-900" };
    }
    default:
      return { text: "Stock unknown here", tone: "bg-slate-100 text-slate-600" };
  }
}

const REASON_LABEL: Record<string, string> = {
  no_active_ingredients: "no active ingredients listed",
  ingredient_strength_unparseable: "an ingredient strength is missing or not a recognised unit",
  duplicate_ingredient: "an ingredient is listed twice",
  dosage_form_unknown: "dosage form not stated",
  route_not_stated: "route of administration not stated",
  discontinued: "product is discontinued",
  insufficient_metadata: "not enough information",
};

export function insufficientReasonLabel(reason: string): string {
  return REASON_LABEL[reason] ?? reason;
}
