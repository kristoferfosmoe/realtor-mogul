"""Ledger categories and the keyword rules that guess them from bank descriptions."""

from __future__ import annotations

import re
from decimal import Decimal
from enum import StrEnum
from typing import Literal


class Group(StrEnum):
    INCOME = "income"  # counts toward NOI
    OPERATING = "operating_expense"  # counts toward NOI
    CAPITAL = "capital_expense"  # below NOI, in cash flow
    DEBT = "debt_service"  # below NOI, in cash flow
    TRANSFER = "transfer"  # owner money in/out: not a property cash flow
    UNCATEGORIZED = "uncategorized"  # real cash, but kept out of NOI until labeled


CATEGORIES: dict[str, tuple[str, Group]] = {
    "rent": ("Rent", Group.INCOME),
    "other_income": ("Other income", Group.INCOME),
    "property_tax": ("Property tax", Group.OPERATING),
    "insurance": ("Insurance", Group.OPERATING),
    "hoa": ("HOA", Group.OPERATING),
    "utilities": ("Utilities", Group.OPERATING),
    "maintenance": ("Repairs & maintenance", Group.OPERATING),
    "management": ("Management", Group.OPERATING),
    "other_expense": ("Other expense", Group.OPERATING),
    "capex": ("Capital improvements", Group.CAPITAL),
    "debt_service": ("Mortgage payment", Group.DEBT),
    "transfer": ("Owner transfer", Group.TRANSFER),
    "uncategorized": ("Uncategorized", Group.UNCATEGORIZED),
}


CategoryId = Literal[
    "rent",
    "other_income",
    "property_tax",
    "insurance",
    "hoa",
    "utilities",
    "maintenance",
    "management",
    "other_expense",
    "capex",
    "debt_service",
    "transfer",
    "uncategorized",
]


def group_of(category: str) -> Group:
    return CATEGORIES[category][1]


# First match wins. (pattern, category, sign): sign +1 only matches money in, -1 money out.
_RULES: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(p, re.I), c, s)
    for p, c, s in [
        (r"\btransfer\b|owner (draw|contribution)|distribution", "transfer", 0),
        (r"mortgage|loan (pmt|payment)|\bescrow\b|servicing", "debt_service", -1),
        (r"property tax|county tax|tax collector|treasurer", "property_tax", -1),
        (r"insurance|\binsur", "insurance", -1),
        (r"\bhoa\b|homeowners assoc|association dues", "hoa", -1),
        (r"electric|\bwater\b|sewer|\bgas\b|trash|waste|utilit|energy|power co", "utilities", -1),
        (r"management fee|property management|\bmgmt\b", "management", -1),
        (r"\broof|renovat|remodel|replace|new (hvac|furnace|water heater)|appliance", "capex", -1),
        (
            r"repair|plumb|hvac|handyman|mainten|landscap|lawn|pest|home depot|lowe'?s",
            "maintenance",
            -1,
        ),
        (r"\brent\b|rental income|tenant|lease payment", "rent", 1),
        (r"late fee|pet fee|laundry|parking|application fee", "other_income", 1),
    ]
]


def guess_category(description: str, amount: Decimal) -> str:
    direction = 1 if amount > 0 else -1
    for pattern, category, sign in _RULES:
        if (sign == 0 or sign == direction) and pattern.search(description):
            return category
    return "uncategorized"
