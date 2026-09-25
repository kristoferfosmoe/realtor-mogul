"""Parse bank or property-manager CSV exports into ledger rows.

Handles the common layouts: a signed "Amount" column, or separate Debit/Credit
columns; US or ISO dates; "$1,234.56" and "(12.00)" style numbers.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .categories import CATEGORIES, guess_category

_ALIASES = {
    "date": {"date", "transaction date", "posting date", "posted date", "trans date", "post date"},
    "amount": {"amount", "transaction amount", "net amount"},
    "debit": {"debit", "debits", "withdrawal", "withdrawals", "debit amount", "money out"},
    "credit": {"credit", "credits", "deposit", "deposits", "credit amount", "money in"},
    "description": {"description", "memo", "payee", "name", "details", "transaction"},
    "category": {"category"},
}
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%d-%b-%Y", "%b %d, %Y")


@dataclass(frozen=True)
class StatementRow:
    date: date
    amount: Decimal
    description: str
    category: str
    category_guessed: bool
    import_hash: str


def parse_statement(text: str) -> list[StatementRow]:
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(reader, None)
    if not header:
        raise ValueError("the file is empty")
    cols = _map_columns(header)
    if "date" not in cols:
        raise ValueError(f"no date column found in header: {header}")
    if "amount" not in cols and not ({"debit", "credit"} & cols.keys()):
        raise ValueError("need an Amount column, or Debit/Credit columns")

    rows: list[StatementRow] = []
    seen: dict[str, int] = {}
    for line_no, raw in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw):
            continue
        get = _Row(raw, cols)
        try:
            when = _parse_date(get("date"))
            if "amount" in cols and get("amount"):
                amount = _parse_money(get("amount"))
            else:
                amount = _parse_money(get("credit") or "0") - abs(_parse_money(get("debit") or "0"))
        except ValueError as e:
            raise ValueError(f"line {line_no}: {e}") from e
        description = get("description")
        given = get("category").lower().replace(" ", "_")
        category = given if given in CATEGORIES else guess_category(description, amount)
        # Identical lines on the same day (two $35 fees) stay distinct via their occurrence.
        key = f"{when.isoformat()}|{amount}|{description}"
        seen[key] = seen.get(key, 0) + 1
        digest = hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest()
        rows.append(
            StatementRow(when, amount, description, category, given not in CATEGORIES, digest)
        )
    return rows


class _Row:
    def __init__(self, cells: list[str], cols: dict[str, int]) -> None:
        self.cells, self.cols = cells, cols

    def __call__(self, key: str) -> str:
        i = self.cols.get(key)
        return self.cells[i].strip() if i is not None and i < len(self.cells) else ""


def _map_columns(header: list[str]) -> dict[str, int]:
    cols: dict[str, int] = {}
    for i, name in enumerate(header):
        norm = name.strip().lower()
        for key, aliases in _ALIASES.items():
            if norm in aliases and key not in cols:
                cols[key] = i
    return cols


def _parse_date(text: str) -> date:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date {text!r}")


def _parse_money(text: str) -> Decimal:
    cleaned = text.replace("$", "").replace(",", "").replace(" ", "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        value = Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation as e:
        raise ValueError(f"unrecognized amount {text!r}") from e
    return -value if negative else value
