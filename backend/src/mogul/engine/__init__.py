"""Pure underwriting engine: no database, network or clock access.

Everything here is deterministic so it can be unit-tested and reused by the API,
background workers (scoring listings) and notebooks alike.
"""

from .financing import balance_after, monthly_payment
from .models import Analysis, Deal, Exit, Financing, Metrics, YearRow
from .proforma import analyze
from .returns import irr, npv, xirr, xnpv
from .sensitivity import NUMERIC_METRICS, SensitivityGrid, sensitivity, with_field

__all__ = [
    "NUMERIC_METRICS",
    "Analysis",
    "Deal",
    "Exit",
    "Financing",
    "Metrics",
    "SensitivityGrid",
    "YearRow",
    "analyze",
    "balance_after",
    "irr",
    "monthly_payment",
    "npv",
    "sensitivity",
    "with_field",
    "xirr",
    "xnpv",
]
