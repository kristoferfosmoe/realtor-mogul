"""Address keys, property-type mapping and metro matching for listings."""

from __future__ import annotations

import re
from collections.abc import Iterable

_SUFFIXES = {
    "street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "lane": "ln",
    "court": "ct", "boulevard": "blvd", "place": "pl", "terrace": "ter", "circle": "cir",
    "highway": "hwy", "parkway": "pkwy", "trail": "trl", "square": "sq",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "apartment": "unit", "apt": "unit", "suite": "unit", "ste": "unit",
}  # fmt: skip


def address_key(address: str, city: str | None, state: str | None, zip_code: str | None) -> str:
    """Lowercase, punctuation-free, abbreviated form used to match the same property."""
    text = f"{address} {city or ''} {state or ''} {(zip_code or '')[:5]}".lower()
    text = text.replace("#", " unit ")
    words = re.sub(r"[^a-z0-9 ]", " ", text).split()
    return " ".join(_SUFFIXES.get(w, w) for w in words)


_TYPE_PATTERNS = [
    (r"multi.*(5\+|5 \+|apartment)|apartment|5\+ unit", "multifamily"),
    (r"multi|duplex|triplex|fourplex|quadplex|2-4|2 - 4", "multi_2_4"),
    (r"condo|co-op|coop|townho", "condo"),
    (r"land|lot", "land"),
    (r"commercial|retail|office|industrial|mixed", "commercial"),
    (r"single|residential|house|manufactured|mobile", "single_family"),
]


def property_type(raw: str | None) -> str:
    text = (raw or "").lower()
    for pattern, kind in _TYPE_PATTERNS:
        if re.search(pattern, text):
            return kind
    return "single_family"


def default_units(kind: str, raw: str | None = None) -> tuple[int, bool]:
    """(units, inferred). Listings rarely state unit counts; guess from the type name."""
    text = (raw or "").lower()
    for word, n in (("duplex", 2), ("triplex", 3), ("fourplex", 4), ("quadplex", 4)):
        if word in text:
            return n, False
    if kind == "multi_2_4":
        return 2, True
    if kind == "multifamily":
        return 5, True
    return 1, False


def match_market(
    city: str | None, state: str | None, metros: Iterable[tuple[int, str]]
) -> int | None:
    """Metro id whose name lists this city and state ("Miami-Fort Lauderdale-..., FL").

    Only principal cities named in the metro title match; suburbs need a ZIP→CBSA
    crosswalk, which is a later improvement.
    """
    if not city or not state:
        return None
    c, s = city.strip().lower(), state.strip().lower()
    for metro_id, name in metros:
        cities, _, states = name.lower().rpartition(", ")
        if s in re.split(r"[-/]", states) and c in [x.strip() for x in re.split(r"[-/]", cities)]:
            return metro_id
    return None
