import { describe, expect, it } from "vitest";
import { formatMoney, formLabel, insufficientReasonLabel, priceBasisLabel, releaseLabel, stockLabel, strengthLabel, unitPriceLabel } from "./medicine-format";

describe("medicine display", () => {
  it("labels price basis honestly", () => {
    expect(priceBasisLabel("unspecified")).toMatch(/does not say MRP or selling price/);
    expect(priceBasisLabel("mrp")).toBe("MRP");
  });

  it("shows unit prices only on a known basis and never invents one", () => {
    expect(unitPriceLabel({ unit_price: "0.33", pack_unit: "unit", currency: "INR" })).toBe("₹0.33 per tablet/capsule");
    expect(unitPriceLabel({ unit_price: "1.18", pack_unit: "mL", currency: "INR" })).toBe("₹1.18 per mL");
    expect(unitPriceLabel({ unit_price: null, pack_unit: "unit", currency: "INR" })).toBeNull();
    expect(unitPriceLabel({ unit_price: "2", pack_unit: null, currency: "INR" })).toBeNull();
    expect(formatMoney(null, "INR")).toBeNull();
  });

  it("makes missing release/route/form information explicit", () => {
    expect(releaseLabel("not_stated")).toBe("Release type not stated by source");
    expect(releaseLabel("sr")).toBe("SR (modified release)");
    expect(formLabel(null)).toBe("Form not stated");
    expect(formLabel("tablet_dispersible")).toBe("Dispersible tablet");
    expect(insufficientReasonLabel("route_not_stated")).toBe("route of administration not stated");
  });

  it("formats ingredient strengths and missing strengths", () => {
    expect(strengthLabel({ name: "clavulanic acid", strength_value: "125", strength_unit: "mg", raw_text: "" })).toBe("Clavulanic Acid 125 mg");
    expect(strengthLabel({ name: "guaifenesin", strength_value: null, strength_unit: null, raw_text: "" })).toBe("Guaifenesin (strength not stated)");
  });

  it("distinguishes all four stock states", () => {
    expect(stockLabel({ status: "available", stock_id: "s", quantity_on_hand: 40, last_counted_at: null }).text).toBe("In stock here (40)");
    expect(stockLabel({ status: "unavailable", stock_id: "s", quantity_on_hand: 0, last_counted_at: null }).text).toBe("Out of stock here");
    expect(stockLabel({ status: "stale", stock_id: "s", quantity_on_hand: 9, last_counted_at: "2026-01-01T00:00:00Z" }).text).toMatch(/out of date/);
    expect(stockLabel({ status: "unknown", stock_id: null, quantity_on_hand: null, last_counted_at: null }).text).toBe("Stock unknown here");
  });
});
