from datetime import date

import pytest

from mogul.engine import irr, npv, xirr


def test_npv_discounts_from_time_zero() -> None:
    assert npv(0.1, [-100, 110]) == pytest.approx(0)
    assert npv(0.0, [-100, 30, 80]) == pytest.approx(10)


@pytest.mark.parametrize(
    ("flows", "expected"),
    [
        ([-100, 110], 0.10),
        ([-100, 39, 59, 55, 20], 0.2809484),  # numpy-financial docs example
        ([-1000, 0, 0, 1331], 0.10),
        ([-100, 50], -0.50),
    ],
)
def test_irr_known_values(flows: list[float], expected: float) -> None:
    assert irr(flows) == pytest.approx(expected, abs=1e-6)


def test_irr_zeroes_npv() -> None:
    flows = [-84_000, -628, 120, 900, 1_700, 250_000]
    rate = irr(flows)
    assert rate is not None
    assert npv(rate, flows) == pytest.approx(0, abs=1e-4)


@pytest.mark.parametrize("flows", [[100, 50], [-100, -50], [0, 0], []])
def test_irr_undefined_without_sign_change(flows: list[float]) -> None:
    assert irr(flows) is None


def test_xirr_matches_excel_documentation_example() -> None:
    flows = [
        (date(2008, 1, 1), -10_000),
        (date(2008, 3, 1), 2_750),
        (date(2008, 10, 30), 4_250),
        (date(2009, 2, 15), 3_250),
        (date(2009, 4, 1), 2_750),
    ]
    assert xirr(flows) == pytest.approx(0.373362535, abs=1e-6)


def test_xirr_equals_irr_for_annual_flows_on_365_day_years() -> None:
    flows = [(date(2021, 1, 1), -100.0), (date(2022, 1, 1), 110.0)]
    assert xirr(flows) == pytest.approx(0.10, abs=1e-9)
