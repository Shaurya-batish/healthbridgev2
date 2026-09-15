"""Unit tests for the fail-closed identity/matching/pricing rules.

Product strings below are copied in the exact shape the real Indian Medicine
Dataset uses (pack labels, "Name (strength)" compositions); they are test
inputs, not claims about any real product's price.
"""
from decimal import Decimal

import pytest

from app import salt_matching as sm


def ident(name, pack, *comps, discontinued=False):
    return sm.build_identity(name=name, pack_size_label=pack, compositions=list(comps), is_discontinued=discontinued)


# --- strengths & unit normalisation -------------------------------------------


@pytest.mark.parametrize(
    "raw, key",
    [
        ("500mg", "500mg"),
        ("0.5gm", "500mg"),
        ("0.5 g", "500mg"),
        ("500000mcg", "500mg"),
        (".5gm", "500mg"),
        ("30mg/5ml", "6mg/mL"),
        ("6mg/ml", "6mg/mL"),
        ("1.2gm/200ml", "6mg/mL"),
        ("1500mcg/2ml", "0.75mg/mL"),
        ("0.10% w/w", "0.1%w/w"),
        ("25000IU", "25000IU"),
        ("3Million IU", "3000000IU"),
        ("75i.u", "75IU"),
        ("100IU/ml", "100IU/mL"),
        ("60000units", "60000units"),
    ],
)
def test_strength_normalisation(raw, key):
    parsed = sm.parse_strength(raw)
    assert parsed is not None
    assert parsed.key == key


@pytest.mark.parametrize("raw", ["NA", "", None, "60Million spores", "5LF", "2.5Billion CFU", "10ml", "50000 AU", "abc mg"])
def test_unparseable_or_non_mass_strengths_fail_closed(raw):
    assert sm.parse_strength(raw) is None


def test_percentage_bases_are_never_merged():
    assert sm.parse_strength("1% w/w").key != sm.parse_strength("1% w/v").key


def test_iu_and_units_are_never_merged():
    assert sm.parse_strength("1000IU").key != sm.parse_strength("1000units").key


# --- identity & matching -------------------------------------------------------


def test_same_salt_same_strength_same_form_matches_across_unit_spellings():
    a = ident("Brand A 500 Tablet", "strip of 10 tablets", "Paracetamol (500mg)")
    b = ident("Brand B Tablet", "strip of 15 tablets", "Paracetamol (0.5gm)")
    assert a.match_status == b.match_status == sm.MATCHABLE
    assert a.match_key == b.match_key


def test_500mg_does_not_match_650mg():
    a = ident("A Tablet", "strip of 10 tablets", "Paracetamol (500mg)")
    b = ident("B Tablet", "strip of 10 tablets", "Paracetamol (650mg)")
    assert a.match_key != b.match_key


def test_multi_ingredient_combination_is_order_independent_but_every_strength_must_match():
    a = ident("Combo A Tablet", "strip of 10 tablets", "Amoxycillin  (500mg) ", "  Clavulanic Acid (125mg)")
    b = ident("Combo B Tablet", "strip of 6 tablets", "Clavulanic Acid (125mg)", "Amoxycillin (0.5gm)")
    c = ident("Combo C Tablet", "strip of 6 tablets", "Clavulanic Acid (62.5mg)", "Amoxycillin (500mg)")
    assert a.match_key == b.match_key
    assert a.match_key != c.match_key


def test_a_subset_of_ingredients_is_not_a_match():
    combo = ident("Combo Tablet", "strip of 10 tablets", "Amoxycillin (500mg)", "Clavulanic Acid (125mg)")
    single = ident("Single Tablet", "strip of 10 tablets", "Amoxycillin (500mg)")
    assert combo.match_key != single.match_key


def test_different_chemical_salt_names_are_not_merged():
    a = ident("A Tablet", "strip of 10 tablets", "Metoprolol Succinate (50mg)")
    b = ident("B Tablet", "strip of 10 tablets", "Metoprolol Tartrate (50mg)")
    assert a.match_key != b.match_key


def test_tablet_does_not_match_suspension_or_dispersible_tablet():
    tab = ident("A Tablet", "strip of 10 tablets", "Azithromycin (200mg)")
    susp = ident("A Suspension", "bottle of 15 ml Oral Suspension", "Azithromycin (200mg/5ml)")
    dt = ident("A DT", "strip of 10 tablet dt", "Azithromycin (200mg)")
    assert len({tab.match_key, susp.match_key, dt.match_key}) == 3
    assert dt.dosage_form == "tablet_dispersible"


def test_release_types_must_match_exactly():
    ir = ident("Dolo 650 Tablet", "strip of 15 tablets", "Paracetamol (650mg)")
    sr = ident("Brand SR Tablet", "strip of 10 tablet sr", "Paracetamol (650mg)")
    er = ident("Brand ER Tablet", "strip of 10 tablet er", "Paracetamol (650mg)")
    assert ir.release_type == sm.RELEASE_NOT_STATED
    assert sr.release_type == "sr" and er.release_type == "er"
    assert len({ir.match_key, sr.match_key, er.match_key}) == 3


def test_release_marker_in_name_only_is_still_detected():
    sr = ident("Brand 500 SR Tablet", "strip of 10 tablets", "Metformin (500mg)")
    assert sr.release_type == "sr"


def test_syrup_concentrations_normalise_to_per_ml():
    a = ident("A Syrup", "bottle of 100 ml Syrup", "Ambroxol (30mg/5ml)", "Levosalbutamol (1mg/5ml)")
    b = ident("B Syrup", "bottle of 60 ml Syrup", "Levosalbutamol (0.2mg/ml)", "Ambroxol (6mg/ml)")
    assert a.match_key == b.match_key
    assert a.route == "oral"


def test_eye_drops_and_ear_drops_have_distinct_routes():
    eye = ident("A Eye Drop", "bottle of 5 ml Eye Drop", "Ciprofloxacin (0.3% w/v)")
    ear = ident("A Ear Drop", "bottle of 5 ml Ear Drop", "Ciprofloxacin (0.3% w/v)")
    assert (eye.route, ear.route) == ("ophthalmic", "otic")
    assert eye.match_key != ear.match_key


@pytest.mark.parametrize(
    "name, pack, comps, reason",
    [
        ("Inj", "vial of 1 injection", ["Ceftriaxone (1gm)"], "route_not_stated"),
        ("Drops", "packet of 10 ml drop", ["Something (1mg/ml)"], "route_not_stated"),
        ("Probiotic Capsule", "strip of 10 capsules", ["Lactobacillus (60Million spores)"], "ingredient_strength_unparseable"),
        ("Cough Syrup", "bottle of 100 ml Syrup", ["Guaifenesin (NA)"], "ingredient_strength_unparseable"),
        ("Mystery", "box of 1 kit", ["Paracetamol (500mg)"], "dosage_form_unknown"),
        ("Empty Tablet", "strip of 10 tablets", [], "no_active_ingredients"),
    ],
)
def test_missing_or_ambiguous_metadata_fails_closed(name, pack, comps, reason):
    identity = ident(name, pack, *comps)
    assert identity.match_status == sm.INSUFFICIENT
    assert identity.match_key is None
    assert reason in identity.insufficient_reasons


def test_discontinued_products_are_never_matchable():
    identity = ident("Old Tablet", "strip of 10 tablets", "Paracetamol (500mg)", discontinued=True)
    assert identity.match_status == sm.INSUFFICIENT
    assert "discontinued" in identity.insufficient_reasons


# --- pack quantity & pricing ---------------------------------------------------


def test_unit_price_is_per_tablet_and_per_ml_on_the_pack_basis():
    tab = ident("A Tablet", "strip of 15 tablets", "Paracetamol (650mg)")
    syr = ident("A Syrup", "bottle of 100 ml Syrup", "Ambroxol (30mg/5ml)")
    assert tab.pack == sm.PackQuantity(Decimal(15), "unit")
    assert syr.pack == sm.PackQuantity(Decimal(100), "mL")
    assert sm.comparable_unit_price(Decimal("34.27"), tab.pack) == Decimal("2.2847")
    assert sm.comparable_unit_price("118", syr.pack) == Decimal("1.1800")


@pytest.mark.parametrize(
    "pack, form",
    [
        ("strip of 0 tablets", "tablet"),
        ("strip of tablets", "tablet"),
        ("bottle of 100 ml Syrup", "tablet"),  # basis mismatch: never price a tablet per mL
        ("strip of 10 tablets", "syrup"),
        (None, "tablet"),
    ],
)
def test_zero_missing_or_mismatched_pack_sizes_give_no_unit_price(pack, form):
    assert sm.parse_pack_quantity(pack, form) is None


@pytest.mark.parametrize("price", [None, 0, "-5", "abc"])
def test_invalid_prices_give_no_unit_price(price):
    assert sm.comparable_unit_price(price, sm.PackQuantity(Decimal(10), "unit")) is None


def test_saving_is_only_reported_for_a_strictly_cheaper_candidate():
    assert sm.saving_percent(Decimal("2.2847"), Decimal("0.3310")) == 85
    assert sm.saving_percent(Decimal("1.00"), Decimal("1.00")) is None
    assert sm.saving_percent(Decimal("1.00"), Decimal("1.50")) is None
    assert sm.saving_percent(None, Decimal("1.00")) is None
    assert sm.saving_percent(Decimal("1.00"), None) is None
    # A saving that floors to 0% is not presented as a saving.
    assert sm.saving_percent(Decimal("1.0000"), Decimal("0.9999")) is None


# --- ranking -------------------------------------------------------------------


def test_ranking_puts_available_stock_first_then_comparable_price():
    C = sm.RankedCandidate
    ranked = sm.rank_candidates(
        [
            C("cheap-unknown", sm.STOCK_UNKNOWN, Decimal("0.10"), "unit"),
            C("dear-available", sm.STOCK_AVAILABLE, Decimal("2.00"), "unit"),
            C("cheap-available", sm.STOCK_AVAILABLE, Decimal("0.50"), "unit"),
            C("no-price-available", sm.STOCK_AVAILABLE, None, None),
            C("zero-stock", sm.STOCK_UNAVAILABLE, Decimal("0.01"), "unit"),
            C("stale", sm.STOCK_STALE, Decimal("0.20"), "unit"),
        ],
        reference_price_unit="unit",
    )
    assert [c.medicine_id for c in ranked] == [
        "cheap-available",
        "dear-available",
        "no-price-available",
        "stale",
        "cheap-unknown",
        "zero-stock",
    ]


def test_candidates_priced_on_a_different_basis_are_not_ranked_as_comparable():
    C = sm.RankedCandidate
    ranked = sm.rank_candidates(
        [C("per-ml", sm.STOCK_UNKNOWN, Decimal("0.01"), "mL"), C("per-unit", sm.STOCK_UNKNOWN, Decimal("5"), "unit")],
        reference_price_unit="unit",
    )
    assert [c.medicine_id for c in ranked] == ["per-unit", "per-ml"]
