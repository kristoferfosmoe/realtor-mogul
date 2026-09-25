"""Two-way sensitivity tables: flex two inputs, read one output metric."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from .models import Deal, Metrics
from .proforma import analyze

NUMERIC_METRICS = frozenset(
    name for name, f in Metrics.model_fields.items() if f.annotation in (float, float | None)
)


class SensitivityGrid(BaseModel):
    x_field: str
    x_values: list[float]
    y_field: str
    y_values: list[float]
    metric: str
    values: list[list[float | None]]  # values[row for y][column for x]


def with_field(deal: Deal, field: str, value: float) -> Deal:
    """Copy of `deal` with one input replaced; `financing.x` reaches into the loan terms.

    Re-validates, so an out-of-range value raises pydantic.ValidationError.
    """
    data: dict[str, Any] = deal.model_dump()
    head, _, tail = field.partition(".")
    if tail:
        if head != "financing" or data["financing"] is None or tail not in data["financing"]:
            raise ValueError(f"unknown input field: {field}")
        data["financing"][tail] = value
    else:
        if head not in data or head == "financing":
            raise ValueError(f"unknown input field: {field}")
        data[head] = value
    return Deal.model_validate(data)


def sensitivity(
    deal: Deal,
    x_field: str,
    x_values: Sequence[float],
    y_field: str,
    y_values: Sequence[float],
    metric: str = "levered_irr",
) -> SensitivityGrid:
    if metric not in NUMERIC_METRICS:
        raise ValueError(f"unknown metric: {metric}")
    rows = []
    for y in y_values:
        row: list[float | None] = []
        for x in x_values:
            flexed = with_field(with_field(deal, y_field, y), x_field, x)
            row.append(getattr(analyze(flexed).metrics, metric))
        rows.append(row)
    return SensitivityGrid(
        x_field=x_field,
        x_values=list(x_values),
        y_field=y_field,
        y_values=list(y_values),
        metric=metric,
        values=rows,
    )
