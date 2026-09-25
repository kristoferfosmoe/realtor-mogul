from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from mogul.db.models import SavedDeal
from mogul.db.session import get_session
from mogul.engine import Deal, Metrics, analyze

router = APIRouter(prefix="/deals", tags=["deals"])

DbSession = Annotated[Session, Depends(get_session)]
Status = Literal["watching", "offer", "owned", "passed"]


class DealIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(None, max_length=300)
    status: Status = "watching"
    inputs: Deal


class DealOut(DealIn):
    id: int
    created_at: datetime
    updated_at: datetime
    metrics: Metrics


def _to_out(row: SavedDeal) -> DealOut:
    inputs = Deal.model_validate(row.inputs)
    return DealOut(
        id=row.id,
        name=row.name,
        address=row.address,
        status=row.status,
        inputs=inputs,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metrics=analyze(inputs).metrics,
    )


def _get(db: Session, deal_id: int) -> SavedDeal:
    row = db.get(SavedDeal, deal_id)
    if row is None:
        raise HTTPException(404, detail="deal not found")
    return row


@router.get("")
def list_deals(db: DbSession) -> list[DealOut]:
    rows = db.scalars(select(SavedDeal).order_by(SavedDeal.updated_at.desc(), SavedDeal.id.desc()))
    return [_to_out(r) for r in rows]


@router.post("", status_code=201)
def create_deal(body: DealIn, db: DbSession) -> DealOut:
    row = SavedDeal(
        name=body.name, address=body.address, status=body.status, inputs=body.inputs.model_dump()
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("/{deal_id}")
def get_deal(deal_id: int, db: DbSession) -> DealOut:
    return _to_out(_get(db, deal_id))


@router.put("/{deal_id}")
def update_deal(deal_id: int, body: DealIn, db: DbSession) -> DealOut:
    row = _get(db, deal_id)
    row.name, row.address, row.status = body.name, body.address, body.status
    row.inputs = body.inputs.model_dump()
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/{deal_id}", status_code=204)
def delete_deal(deal_id: int, db: DbSession) -> Response:
    db.delete(_get(db, deal_id))
    db.commit()
    return Response(status_code=204)
