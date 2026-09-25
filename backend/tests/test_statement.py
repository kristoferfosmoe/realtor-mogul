from datetime import date
from decimal import Decimal
from typing import get_args

import pytest

from mogul.portfolio.categories import CATEGORIES, CategoryId, guess_category
from mogul.portfolio.statement import parse_statement


def test_category_literal_matches_table() -> None:
    assert set(get_args(CategoryId)) == set(CATEGORIES)


def test_signed_amount_layout() -> None:
    rows = parse_statement(
        "Date,Description,Amount\n"
        '01/03/2025,Zelle from J Smith RENT JAN,"$2,450.00"\n'
        "01/05/2025,WELLS FARGO MORTGAGE PMT,(1612.40)\n"
        "1/9/25,HOME DEPOT #123,-84.19\n"
        "\n"
        "2025-01-10,Mystery charge,-12\n"
    )
    assert [(r.date, r.amount, r.category) for r in rows] == [
        (date(2025, 1, 3), Decimal("2450.00"), "rent"),
        (date(2025, 1, 5), Decimal("-1612.40"), "debt_service"),
        (date(2025, 1, 9), Decimal("-84.19"), "maintenance"),
        (date(2025, 1, 10), Decimal("-12.00"), "uncategorized"),
    ]
    assert all(r.category_guessed for r in rows)


def test_debit_credit_layout_and_given_category() -> None:
    rows = parse_statement(
        "Posting Date,Memo,Debit,Credit,Category\n"
        "2025-02-01,County Treasurer,3100.00,,Property Tax\n"
        "2025-02-02,Tenant payment,,1800.00,\n"
    )
    assert rows[0].amount == Decimal("-3100.00") and rows[0].category == "property_tax"
    assert not rows[0].category_guessed
    assert rows[1].amount == Decimal("1800.00") and rows[1].category == "rent"


def test_identical_lines_get_distinct_stable_hashes() -> None:
    text = "Date,Description,Amount\n2025-03-01,Fee,-35\n2025-03-01,Fee,-35\n"
    first, second = parse_statement(text), parse_statement(text)
    assert first[0].import_hash != first[1].import_hash
    assert [r.import_hash for r in first] == [r.import_hash for r in second]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("Description,Amount\nx,1\n", "no date column"),
        ("Date,Description\n2025-01-01,x\n", "Amount column"),
        ("Date,Amount\n2025-13-45,1\n", "line 2: unrecognized date"),
        ("Date,Amount\n2025-01-01,abc\n", "line 2: unrecognized amount"),
    ],
)
def test_errors(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_statement(text)


@pytest.mark.parametrize(
    ("description", "amount", "expected"),
    [
        ("Transfer to savings", "-500", "transfer"),
        ("State Farm Insurance", "-900", "insurance"),
        ("City Water Utility", "-60", "utilities"),
        ("ABC Property Management fee", "-200", "management"),
        ("Roof replacement - ABC Roofing", "-9000", "capex"),
        ("Pet fee", "50", "other_income"),
        ("Rent refund", "-100", "uncategorized"),  # rent rule only matches money in
    ],
)
def test_guess_category(description: str, amount: str, expected: str) -> None:
    assert guess_category(description, Decimal(amount)) == expected
