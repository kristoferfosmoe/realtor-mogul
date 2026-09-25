"""Time-value-of-money helpers: NPV, IRR and XIRR.

IRR is solved by bracketing a sign change of NPV and bisecting, which is slower
than Newton's method but never diverges on the lumpy cash flows real-estate
deals produce (large outflow, small inflows, large sale proceeds).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date

_MIN_RATE = -0.9999
_MAX_RATE = 100.0
_TOLERANCE = 1e-10
_MAX_ITERATIONS = 200


def npv(rate: float, cash_flows: Sequence[float]) -> float:
    """Net present value of evenly spaced cash flows, the first at t=0."""
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))


def irr(cash_flows: Sequence[float]) -> float | None:
    """Internal rate of return of evenly spaced (e.g. annual) cash flows.

    Returns None when the flows never change sign, since no rate can zero them.
    When several roots exist, the lowest one above -100% is returned.
    """
    return _solve(lambda r: npv(r, cash_flows), cash_flows)


def xnpv(rate: float, cash_flows: Sequence[tuple[date, float]]) -> float:
    """Net present value of dated cash flows (Actual/365, like Excel's XNPV)."""
    if not cash_flows:
        return 0.0
    start = min(d for d, _ in cash_flows)
    return float(sum(cf / (1 + rate) ** ((d - start).days / 365) for d, cf in cash_flows))


def xirr(cash_flows: Sequence[tuple[date, float]]) -> float | None:
    """Internal rate of return of irregularly dated cash flows (like Excel's XIRR)."""
    return _solve(lambda r: xnpv(r, cash_flows), [cf for _, cf in cash_flows])


def _solve(f: Callable[[float], float], amounts: Sequence[float]) -> float | None:
    if not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)):
        return None

    # Scan outward on a geometric grid for the first sign change.
    grid = [_MIN_RATE, -0.99, -0.9, -0.75, -0.5, -0.25, -0.1, 0.0]
    step = 0.05
    while grid[-1] < _MAX_RATE:
        grid.append(grid[-1] + step)
        step *= 1.25

    lo, f_lo = grid[0], f(grid[0])
    for hi in grid[1:]:
        f_hi = f(hi)
        if f_lo == 0:
            return lo
        if f_lo * f_hi < 0:
            return _bisect(f, lo, hi, f_lo)
        lo, f_lo = hi, f_hi
    return None


def _bisect(f: Callable[[float], float], lo: float, hi: float, f_lo: float) -> float:
    for _ in range(_MAX_ITERATIONS):
        mid = (lo + hi) / 2
        f_mid = f(mid)
        if f_mid == 0 or (hi - lo) / 2 < _TOLERANCE:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2
