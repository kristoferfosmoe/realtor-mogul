"""Fixed-rate, fully amortizing mortgage math (monthly compounding)."""

from __future__ import annotations


def monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    """Level monthly principal-and-interest payment."""
    if principal <= 0:
        return 0.0
    n = years * 12
    r = annual_rate / 12
    if r == 0:
        return principal / n
    return principal * r / (1 - (1 + r) ** -n)


def balance_after(principal: float, annual_rate: float, years: int, months_paid: int) -> float:
    """Outstanding principal after `months_paid` level payments."""
    n = years * 12
    if principal <= 0 or months_paid >= n:
        return 0.0
    r = annual_rate / 12
    if r == 0:
        return principal * (1 - months_paid / n)
    pmt = monthly_payment(principal, annual_rate, years)
    growth = (1 + r) ** months_paid
    return principal * growth - pmt * (growth - 1) / r


def debt_service_in_year(principal: float, annual_rate: float, years: int, year: int) -> float:
    """Total payments made during loan year `year` (1-based); zero once paid off."""
    n = years * 12
    months = max(0, min(12, n - (year - 1) * 12))
    return monthly_payment(principal, annual_rate, years) * months
