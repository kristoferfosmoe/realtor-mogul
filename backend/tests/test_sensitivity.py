import pytest
from pydantic import ValidationError

from mogul.engine import Deal, analyze, sensitivity, with_field

DEAL = Deal(purchase_price=300_000, monthly_rent=2_400, property_tax_annual=3_600)


def test_grid_shape_and_corner_values() -> None:
    grid = sensitivity(
        DEAL,
        "monthly_rent",
        [2_200, 2_400, 2_600],
        "financing.interest_rate",
        [0.06, 0.07],
        metric="cash_on_cash",
    )
    assert len(grid.values) == 2 and all(len(r) == 3 for r in grid.values)
    expected = analyze(
        with_field(with_field(DEAL, "monthly_rent", 2_600), "financing.interest_rate", 0.06)
    ).metrics.cash_on_cash
    assert grid.values[0][2] == pytest.approx(expected)


def test_higher_rent_raises_irr() -> None:
    grid = sensitivity(DEAL, "monthly_rent", [2_000, 3_000], "appreciation", [0.03])
    low, high = grid.values[0]
    assert low is not None and high is not None and high > low


@pytest.mark.parametrize("field", ["nope", "financing", "financing.nope", "metrics.roic"])
def test_unknown_field(field: str) -> None:
    with pytest.raises(ValueError, match="unknown input field"):
        with_field(DEAL, field, 1)


def test_unknown_metric() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        sensitivity(DEAL, "monthly_rent", [1], "appreciation", [0], metric="vibes")


def test_out_of_range_value_revalidates() -> None:
    with pytest.raises(ValidationError):
        with_field(DEAL, "vacancy_rate", 1.5)
