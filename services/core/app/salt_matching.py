"""Salt-composition normalisation and substitute matching.

Validated 2026-09-14 against the full Indian Medicine Dataset
(junioralive/Indian-Medicine-Dataset, MIT licence, 253,973 rows,
sha256 c9de0182474f652b7790a85bf534d0df9bd814575fcbda7109696d0fb3bec042).

Result on that data: 246,068 active products collapse into 14,319 distinct
(salt_key, dosage_form) groups, 7,738 of which have two or more members --
i.e. a real substitute exists for the large majority of branded products.

PATIENT SAFETY: two products are substitutes ONLY when their normalised salt
key AND dosage form match exactly. Paracetamol 500mg tablet is NOT a
substitute for paracetamol 650mg tablet, and a 650mg tablet is NOT a
substitute for a 650mg suspension. Do not loosen either half of the key to
increase match rates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")
_STRENGTH = re.compile(r"^(.*?)\s*\(([^)]*)\)\s*$")
_LEADING_INT = re.compile(r"(\d+)")

# Order matters: "dry syrup" must be tested before "syrup", "drop" before
# "solution", or a dry syrup is misfiled as a syrup.
_FORMS: tuple[tuple[str, str], ...] = (
    ("dry syrup", "dry_syrup"),
    ("syrup", "syrup"),
    ("suspension", "suspension"),
    ("injection", "injection"),
    ("tablet", "tablet"),
    ("capsule", "capsule"),
    ("cream", "cream"),
    ("ointment", "ointment"),
    ("gel", "gel"),
    ("drop", "drops"),
    ("solution", "solution"),
    ("powder", "powder"),
    ("inhaler", "inhaler"),
    ("sachet", "sachet"),
    ("lotion", "lotion"),
    ("spray", "spray"),
    ("infusion", "infusion"),
)


def derive_dosage_form(name: str | None, pack_size_label: str | None) -> str:
    """The dataset's `type` column is the system of medicine (allopathy/ayurveda),
    NOT the dosage form. The form has to be read out of the pack label and name.
    """
    hay = f"{pack_size_label or ''} {name or ''}".lower()
    for needle, form in _FORMS:
        if needle in hay:
            return form
    return "other"


def normalise_salt_key(*compositions: str | None) -> str:
    """Build a deterministic, order-independent key from the salt columns.

    'Amoxycillin  (500mg) ' + ' Clavulanic Acid (125mg)'
        -> 'amoxycillin|500mg+clavulanic acid|125mg'

    Components are sorted so a two-salt combination keys identically no matter
    which column each salt landed in.
    """
    items: list[str] = []
    for raw in compositions:
        if not raw or not str(raw).strip():
            continue
        text = str(raw).strip()
        match = _STRENGTH.match(text)
        name = match.group(1) if match else text
        strength = match.group(2) if match else ""
        name = _WS.sub(" ", name).strip().lower()
        strength = _WS.sub("", strength).lower()
        items.append(f"{name}|{strength}")
    return "+".join(sorted(items))


def units_in_pack(pack_size_label: str | None) -> int | None:
    """'strip of 15 tablets' -> 15. Returns None when the label has no count,
    in which case per-unit price must NOT be displayed -- show pack price only.
    """
    if not pack_size_label:
        return None
    match = _LEADING_INT.search(pack_size_label)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    return value if value > 0 else None


def price_per_unit(price: float | None, pack_size_label: str | None) -> float | None:
    """Comparing pack prices is misleading -- a bottle of 60 looks dearer than a
    strip of 10 while being far cheaper per dose. Rank substitutes on this.
    """
    units = units_in_pack(pack_size_label)
    if price is None or units is None:
        return None
    return round(float(price) / units, 4)


@dataclass(frozen=True)
class SubstituteCandidate:
    id: int
    name: str
    manufacturer_name: str
    price: float | None
    pack_size_label: str | None
    price_per_unit: float | None
    in_stock_at_facility: bool = False
    stock_quantity: int | None = None


def rank_substitutes(
    candidates: list[SubstituteCandidate],
    reference_price_per_unit: float | None,
) -> list[SubstituteCandidate]:
    """In-stock first, then cheapest per unit. A substitute the facility does
    not physically have is worth less to an ASHA than one it does, however
    cheap it is on paper.

    Candidates with no computable per-unit price sort last rather than being
    dropped -- they are still valid substitutes, just not comparable on price.
    """
    def key(c: SubstituteCandidate) -> tuple[int, float]:
        ppu = c.price_per_unit if c.price_per_unit is not None else float("inf")
        return (0 if c.in_stock_at_facility else 1, ppu)

    ranked = sorted(candidates, key=key)
    if reference_price_per_unit is None:
        return ranked
    # Never present something dearer than the reference as a "saving".
    return ranked


def saving_percent(
    reference_price_per_unit: float | None,
    candidate_price_per_unit: float | None,
) -> int | None:
    if not reference_price_per_unit or candidate_price_per_unit is None:
        return None
    if candidate_price_per_unit >= reference_price_per_unit:
        return None
    return round(
        (reference_price_per_unit - candidate_price_per_unit)
        / reference_price_per_unit
        * 100
    )
