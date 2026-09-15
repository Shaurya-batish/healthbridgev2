"""Structured medicine identity, same-composition matching and comparable pricing.

Rebuilt 2026-09-15 against the real Indian Medicine Dataset
(junioralive/Indian-Medicine-Dataset, MIT, 253,973 rows, sha256
c9de0182474f652b7790a85bf534d0df9bd814575fcbda7109696d0fb3bec042 --
re-verified by download on 2026-09-15). The earlier version of this module
keyed on raw strength strings ("500mg" vs "0.5gm" never matched, "NA" did),
ignored route and release type entirely, and had a dead branch in
rank_substitutes.

PATIENT SAFETY -- every rule here FAILS CLOSED:

Two products are shown as comparable only when ALL of these match exactly:
  * the complete set of active ingredients (normalised name, no fuzzy match,
    so "Amlodipine" and "Amlodipine Besylate" are NOT merged -- different
    chemical salts are different ingredients),
  * every ingredient's strength after explicit unit normalisation
    (mcg/mg/g -> mg; mg per N ml -> mg/mL; IU and "Million IU"; percentage
    strengths only against the same w/w, w/v or v/v basis),
  * dosage form (a dispersible tablet is not a plain tablet; a soft gelatin
    capsule is not a hard capsule),
  * route (derived from the form; injections and bare "drops"/"solution"
    carry no route in the source and are therefore never matchable),
  * release type (SR/ER/CR/XL/MR/PR/DR/... must be identical; a product with
    no stated release marker only matches another with no stated marker, and
    the UI must say the source does not state release type).

Anything that can't be parsed -- "NA" strengths, spores/cells/LF/CFU units,
unknown pack forms, discontinued products -- is `insufficient_metadata` and
never appears as a candidate. Matching is informational: it never
authorises substitution. A clinician decides (routers/substitution_requests.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

MATCHABLE = "matchable"
INSUFFICIENT = "insufficient_metadata"

_WS = re.compile(r"\s+")
_COMPOSITION = re.compile(r"^\s*(.+?)\s*\(([^()]*)\)\s*$")
_NUMBER = r"(\d+(?:\.\d+)?|\.\d+)"

# --- strengths ----------------------------------------------------------------

_MASS_TO_MG = {"mcg": Decimal("0.001"), "µg": Decimal("0.001"), "ug": Decimal("0.001"), "mg": Decimal(1), "g": Decimal(1000), "gm": Decimal(1000)}
_MULTIPLIERS = {"": Decimal(1), "lac": Decimal(100_000), "lakh": Decimal(100_000), "million": Decimal(1_000_000)}

_RE_MASS = re.compile(rf"^{_NUMBER}(mcg|µg|ug|mg|gm|g)$")
_RE_MASS_PER_VOL = re.compile(rf"^{_NUMBER}(mcg|µg|ug|mg|gm|g)/{_NUMBER}?ml$")
_RE_MASS_PER_MASS = re.compile(rf"^{_NUMBER}(mcg|µg|ug|mg|gm|g)/{_NUMBER}?(gm|g)$")
_RE_PERCENT = re.compile(rf"^{_NUMBER}%(w/w|w/v|v/v)$")
_RE_IU = re.compile(rf"^{_NUMBER}(lac|lakh|million)?(iu|i\.u\.?)$")
_RE_IU_PER_VOL = re.compile(rf"^{_NUMBER}(iu|i\.u\.?)/{_NUMBER}?ml$")
_RE_UNITS = re.compile(rf"^{_NUMBER}(lac|lakh|million)?units$")


def _dec(text: str) -> Decimal:
    return Decimal(text if not text.startswith(".") else f"0{text}")


def _canon(value: Decimal) -> str:
    """Stable string for equality: 500, 500.0 and 0.5e3 all become '500'."""
    normalized = value.normalize()
    # Avoid scientific notation ('5E+2') in keys and in the UI.
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True)
class Strength:
    value: Decimal
    unit: str  # canonical: mg, mg/mL, mg/g, IU, IU/mL, units, %w/w, %w/v, %v/v

    @property
    def key(self) -> str:
        return f"{_canon(self.value)}{self.unit}"

    def display(self) -> str:
        return f"{_canon(self.value)} {self.unit}"


def parse_strength(raw: str | None) -> Strength | None:
    """Returns a normalised strength, or None when the text can't safely be
    interpreted (which makes the whole product non-matchable)."""
    if not raw:
        return None
    text = _WS.sub("", raw).lower()
    if not text or text == "na":
        return None
    try:
        if m := _RE_MASS.match(text):
            return Strength(_dec(m.group(1)) * _MASS_TO_MG[m.group(2)], "mg")
        if m := _RE_MASS_PER_VOL.match(text):
            per = _dec(m.group(3)) if m.group(3) else Decimal(1)
            if per <= 0:
                return None
            return Strength(_dec(m.group(1)) * _MASS_TO_MG[m.group(2)] / per, "mg/mL")
        if m := _RE_MASS_PER_MASS.match(text):
            per = _dec(m.group(3)) if m.group(3) else Decimal(1)
            if per <= 0:
                return None
            return Strength(_dec(m.group(1)) * _MASS_TO_MG[m.group(2)] / (per * 1000), "mg/mg")
        if m := _RE_PERCENT.match(text):
            return Strength(_dec(m.group(1)), f"%{m.group(2)}")
        if m := _RE_IU.match(text):
            return Strength(_dec(m.group(1)) * _MULTIPLIERS[m.group(2) or ""], "IU")
        if m := _RE_IU_PER_VOL.match(text):
            per = _dec(m.group(3)) if m.group(3) else Decimal(1)
            if per <= 0:
                return None
            return Strength(_dec(m.group(1)) / per, "IU/mL")
        if m := _RE_UNITS.match(text):
            # "units" is kept distinct from IU: not every labelled unit is an
            # International Unit, so they are never merged.
            return Strength(_dec(m.group(1)) * _MULTIPLIERS[m.group(2) or ""], "units")
    except (InvalidOperation, ZeroDivisionError):
        return None
    return None


@dataclass(frozen=True)
class Ingredient:
    name: str  # normalised, lower-case, single-spaced
    strength: Strength | None
    raw: str


def normalise_ingredient_name(name: str) -> str:
    return _WS.sub(" ", name).strip().lower()


def parse_composition(raw: str | None) -> Ingredient | None:
    """'Amoxycillin  (500mg) ' -> Ingredient('amoxycillin', 500 mg). A
    composition with no parenthesised strength keeps strength=None."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    m = _COMPOSITION.match(text)
    if not m:
        return Ingredient(normalise_ingredient_name(text), None, text)
    return Ingredient(normalise_ingredient_name(m.group(1)), parse_strength(m.group(2)), text)


# --- dosage form, route, release ------------------------------------------------

# (pattern tested against the lower-cased pack label, then the name; form; route)
# Order matters: specific phrases before generic ones ("dry syrup" before
# "syrup", "eye drop" before "drop", "tablet dt" before "tablet").
_FORMS: tuple[tuple[re.Pattern[str], str, str | None], ...] = tuple(
    (re.compile(p), form, route)
    for p, form, route in (
        (r"\bdry syrup\b", "dry_syrup", "oral"),
        (r"\boral suspension\b", "suspension", "oral"),
        (r"\bsuspension\b", "suspension", "oral"),
        (r"\bsyrup\b", "syrup", "oral"),
        (r"\boral solution\b", "oral_solution", "oral"),
        (r"\boral drops?\b", "oral_drops", "oral"),
        (r"\bexpectorant\b", "syrup", "oral"),
        (r"\b(eye drops?|ophthalmic solution)\b", "eye_drops", "ophthalmic"),
        (r"\beye ointment\b", "eye_ointment", "ophthalmic"),
        (r"\bear drops?\b", "ear_drops", "otic"),
        (r"\bnasal drops?\b", "nasal_drops", "nasal"),
        (r"\bnasal spray\b", "nasal_spray", "nasal"),
        (r"\btablets? dt\b|\bdispersible tablet", "tablet_dispersible", "oral"),
        (r"\btablets? md\b|\bmouth dissolving\b", "tablet_mouth_dissolving", "oral"),
        (r"\bchewable tablet", "tablet_chewable", "oral"),
        (r"\beffervescent tablet", "tablet_effervescent", "oral"),
        (r"\bsoft gelatin capsules?\b", "capsule_soft_gelatin", "oral"),
        (r"\btablets?\b", "tablet", "oral"),
        (r"\bcapsules?\b", "capsule", "oral"),
        (r"\bcream\b", "cream", "topical"),
        (r"\bointment\b", "ointment", "topical"),
        (r"\bgel\b", "gel", "topical"),
        (r"\blotion\b", "lotion", "topical"),
        # Route is genuinely not stated for these in the source -> never matchable.
        (r"\b(injection|infusion)\b", "injection", None),
        (r"\bdrops?\b", "drops", None),
        (r"\bsolution\b", "solution", None),
    )
)

# Release markers as they appear in pack labels ("strip of 10 tablet sr") and
# product names ("Dolo 650 SR"). Each marker is kept distinct -- SR and ER are
# not merged, because the source gives no evidence they are pharmacokinetically
# equivalent for a given product.
_RELEASE_MARKERS = ("sr", "er", "xr", "xl", "cr", "mr", "pr", "dr", "la", "cd", "ec", "od", "retard")
_RE_RELEASE = re.compile(r"\b(" + "|".join(_RELEASE_MARKERS) + r"|prolonged release|sustained release|extended release|controlled release|modified release|delayed release)\b")
_RELEASE_WORDS = {
    "prolonged release": "pr",
    "sustained release": "sr",
    "extended release": "er",
    "controlled release": "cr",
    "modified release": "mr",
    "delayed release": "dr",
}
RELEASE_NOT_STATED = "not_stated"

# Liquid and semi-solid forms priced per mL / per g; unit-dose forms per unit.
_UNIT_DOSE_FORMS = {
    "tablet", "tablet_dispersible", "tablet_mouth_dissolving", "tablet_chewable",
    "tablet_effervescent", "capsule", "capsule_soft_gelatin",
}
_PER_ML_FORMS = {"syrup", "suspension", "oral_solution", "oral_drops", "eye_drops", "ear_drops", "nasal_drops", "nasal_spray"}
_PER_G_FORMS = {"cream", "ointment", "gel", "eye_ointment"}


def derive_form_and_route(name: str | None, pack_size_label: str | None) -> tuple[str | None, str | None]:
    """The dataset's `type` column is the system of medicine (always
    "allopathy"), NOT the dosage form -- form comes from the pack label first,
    then the product name. Returns (None, None) when nothing is recognised."""
    for hay in ((pack_size_label or "").lower(), (name or "").lower()):
        if not hay.strip():
            continue
        for pattern, form, route in _FORMS:
            if pattern.search(hay):
                return form, route
    return None, None


def derive_release_type(name: str | None, pack_size_label: str | None) -> str:
    markers = set()
    for hay in ((pack_size_label or "").lower(), (name or "").lower()):
        for found in _RE_RELEASE.findall(hay):
            markers.add(_RELEASE_WORDS.get(found, found))
    if not markers:
        return RELEASE_NOT_STATED
    # Two different markers on one product is contradictory -> keep both so it
    # can only ever match an identically-labelled product.
    return "+".join(sorted(markers))


# --- pack quantity & pricing ----------------------------------------------------

_RE_PACK_COUNT = re.compile(rf"\bof\s+{_NUMBER}\s+(tablets?|capsules?|soft gelatin capsules?)\b")
_RE_PACK_ML = re.compile(rf"\bof\s+{_NUMBER}\s*ml\b")
_RE_PACK_G = re.compile(rf"\bof\s+{_NUMBER}\s*(gm|g)\b")


@dataclass(frozen=True)
class PackQuantity:
    quantity: Decimal
    unit: str  # "unit" (tablet/capsule), "mL", "g"


def parse_pack_quantity(pack_size_label: str | None, dosage_form: str | None) -> PackQuantity | None:
    """'strip of 15 tablets' -> 15 unit; 'bottle of 100 ml Syrup' -> 100 mL.
    The pack unit must agree with the dosage form's pricing basis, otherwise
    None (a price per unit must never be computed on the wrong basis)."""
    label = (pack_size_label or "").lower()
    if not label or dosage_form is None:
        return None
    try:
        if dosage_form in _UNIT_DOSE_FORMS and (m := _RE_PACK_COUNT.search(label)):
            qty, unit = _dec(m.group(1)), "unit"
        elif dosage_form in _PER_ML_FORMS and (m := _RE_PACK_ML.search(label)):
            qty, unit = _dec(m.group(1)), "mL"
        elif dosage_form in _PER_G_FORMS and (m := _RE_PACK_G.search(label)):
            qty, unit = _dec(m.group(1)), "g"
        else:
            return None
    except InvalidOperation:
        return None
    if qty <= 0:
        return None
    return PackQuantity(qty, unit)


def comparable_unit_price(price: Decimal | float | str | None, pack: PackQuantity | None) -> Decimal | None:
    """Pack price / pack quantity on the pack's own basis (per tablet, per mL,
    per g). None for a missing, zero or negative price or pack size."""
    if price is None or pack is None:
        return None
    try:
        amount = Decimal(str(price))
    except InvalidOperation:
        return None
    if amount <= 0 or pack.quantity <= 0:
        return None
    return (amount / pack.quantity).quantize(Decimal("0.0001"))


def saving_percent(reference_unit_price: Decimal | None, candidate_unit_price: Decimal | None) -> int | None:
    """Only a strictly cheaper candidate on the same basis is a saving. Equal
    or dearer -> None, never a zero/negative "saving"."""
    if reference_unit_price is None or candidate_unit_price is None:
        return None
    if reference_unit_price <= 0 or candidate_unit_price >= reference_unit_price:
        return None
    pct = int(((reference_unit_price - candidate_unit_price) / reference_unit_price * 100).to_integral_value(rounding="ROUND_FLOOR"))
    return pct if pct > 0 else None


# --- identity -------------------------------------------------------------------


@dataclass(frozen=True)
class MedicineIdentity:
    ingredients: tuple[Ingredient, ...]
    dosage_form: str | None
    route: str | None
    release_type: str
    pack: PackQuantity | None
    match_status: str
    match_key: str | None
    insufficient_reasons: tuple[str, ...] = field(default_factory=tuple)


def build_identity(
    *,
    name: str | None,
    pack_size_label: str | None,
    compositions: list[str | None],
    is_discontinued: bool = False,
) -> MedicineIdentity:
    ingredients = tuple(i for i in (parse_composition(c) for c in compositions) if i is not None)
    form, route = derive_form_and_route(name, pack_size_label)
    release = derive_release_type(name, pack_size_label)
    pack = parse_pack_quantity(pack_size_label, form)

    reasons: list[str] = []
    if not ingredients:
        reasons.append("no_active_ingredients")
    if any(i.strength is None for i in ingredients):
        reasons.append("ingredient_strength_unparseable")
    names = [i.name for i in ingredients]
    if len(set(names)) != len(names):
        reasons.append("duplicate_ingredient")
    if form is None:
        reasons.append("dosage_form_unknown")
    if route is None:
        reasons.append("route_not_stated")
    if is_discontinued:
        reasons.append("discontinued")

    if reasons:
        return MedicineIdentity(ingredients, form, route, release, pack, INSUFFICIENT, None, tuple(reasons))

    parts = sorted(f"{i.name}|{i.strength.key}" for i in ingredients)  # type: ignore[union-attr]
    key = f"{form}|{route}|{release}|" + "+".join(parts)
    return MedicineIdentity(ingredients, form, route, release, pack, MATCHABLE, key, ())


# --- ranking --------------------------------------------------------------------

STOCK_AVAILABLE = "available"
STOCK_UNAVAILABLE = "unavailable"
STOCK_STALE = "stale"
STOCK_UNKNOWN = "unknown"


@dataclass(frozen=True)
class RankedCandidate:
    medicine_id: object
    stock_status: str
    unit_price: Decimal | None
    price_unit: str | None


def rank_candidates(candidates: list[RankedCandidate], reference_price_unit: str | None) -> list[RankedCandidate]:
    """Verified available stock first, then by comparable unit price.

    A candidate whose price is on a different basis from the reference (or
    has no computable price) sorts after every comparable one -- it is still a
    valid same-composition product, just not comparable on price.
    """
    stock_order = {STOCK_AVAILABLE: 0, STOCK_STALE: 1, STOCK_UNKNOWN: 2, STOCK_UNAVAILABLE: 3}

    def key(c: RankedCandidate) -> tuple[int, int, Decimal]:
        comparable = c.unit_price is not None and reference_price_unit is not None and c.price_unit == reference_price_unit
        return (
            stock_order.get(c.stock_status, 2),
            0 if comparable else 1,
            c.unit_price if comparable and c.unit_price is not None else Decimal("Infinity"),
        )

    return sorted(candidates, key=key)
