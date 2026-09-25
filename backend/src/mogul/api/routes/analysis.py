from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from mogul.engine import Analysis, Deal, SensitivityGrid, analyze, sensitivity

router = APIRouter(prefix="/analysis", tags=["analysis"])

# A plausible single-family rental, used to seed a blank analyzer.
TEMPLATE = Deal(
    purchase_price=325_000,
    monthly_rent=2_450,
    property_tax_annual=3_900,
    insurance_annual=1_600,
    rehab_cost=10_000,
)


@router.get("/template")
def template() -> Deal:
    return TEMPLATE


@router.post("")
def run_analysis(deal: Deal) -> Analysis:
    return analyze(deal)


class SensitivityRequest(BaseModel):
    deal: Deal
    x_field: str
    x_values: Annotated[list[float], Field(min_length=1, max_length=15)]
    y_field: str
    y_values: Annotated[list[float], Field(min_length=1, max_length=15)]
    metric: str = "levered_irr"


@router.post("/sensitivity")
def run_sensitivity(req: SensitivityRequest) -> SensitivityGrid:
    try:
        return sensitivity(
            req.deal, req.x_field, req.x_values, req.y_field, req.y_values, req.metric
        )
    except ValidationError as e:
        msg = e.errors()[0]["msg"]
        raise HTTPException(422, detail=f"a flexed value is out of range: {msg}") from e
    except ValueError as e:
        raise HTTPException(422, detail=str(e)) from e
