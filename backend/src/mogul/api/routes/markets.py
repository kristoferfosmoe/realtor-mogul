from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from mogul.db.models import Geography, IngestionRun, MarketSeries
from mogul.db.session import get_session
from mogul.ingest import ATTRIBUTIONS
from mogul.ingest.pipeline import DEMO_SOURCE
from mogul.markets.analytics import SeriesStats, gross_yield, shift_months, stats
from mogul.markets.queries import best_series, observations

router = APIRouter(prefix="/markets", tags=["markets"])
DbSession = Annotated[Session, Depends(get_session)]

LOCAL_METRICS = ("rent_index", "home_value")
INDICATORS = [
    ("rent_index", "US Rent"),
    ("home_value", "US Home Value"),
    ("mortgage_rate_30y", "30Y Mortgage"),
    ("cpi_rent", "CPI Rent"),
    ("rental_vacancy", "Rental Vacancy"),
]
SPARK_MONTHS = 24


class Point(BaseModel):
    date: date
    value: float


class GeographyOut(BaseModel):
    id: int
    kind: str
    name: str
    state: str | None
    size_rank: int | None


class MarketSummary(BaseModel):
    geography: GeographyOut
    rent: SeriesStats | None
    home_value: SeriesStats | None
    gross_yield: float | None
    rent_spark: list[float]
    sources: list[str]
    demo: bool


class SeriesOut(BaseModel):
    metric: str
    unit: str
    frequency: str
    source: str
    attribution: str
    stats: SeriesStats | None
    points: list[Point]


class MarketDetail(BaseModel):
    summary: MarketSummary
    series: list[SeriesOut]


class Indicator(BaseModel):
    metric: str
    label: str
    unit: str
    frequency: str
    source: str
    demo: bool
    stats: SeriesStats | None
    spark: list[Point]


class RunOut(BaseModel):
    id: int
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    series_count: int
    observation_count: int
    error: str | None


class SourcesOut(BaseModel):
    runs: list[RunOut]
    attributions: dict[str, str]


def _utc(dt: datetime) -> datetime:
    """SQLite drops time zones; everything is stored in UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _geo_out(g: Geography) -> GeographyOut:
    return GeographyOut(id=g.id, kind=g.kind, name=g.name, state=g.state, size_rank=g.size_rank)


def _summary(
    geo: Geography,
    rent: MarketSeries | None,
    value: MarketSeries | None,
    obs: dict[int, list[tuple[date, float]]],
) -> MarketSummary:
    rent_obs = obs.get(rent.id, []) if rent else []
    value_obs = obs.get(value.id, []) if value else []
    sources = sorted({s.source for s in (rent, value) if s})
    return MarketSummary(
        geography=_geo_out(geo),
        rent=stats(rent_obs),
        home_value=stats(value_obs),
        gross_yield=gross_yield(rent_obs, value_obs),
        rent_spark=[v for _, v in rent_obs[-SPARK_MONTHS:]],
        sources=sources,
        demo=DEMO_SOURCE in sources,
    )


@router.get("")
def list_markets(db: DbSession) -> list[MarketSummary]:
    """Every geography with rent or home-value data, largest first (country on top)."""
    chosen = best_series(db, LOCAL_METRICS)
    obs = observations(db, [s.id for s in chosen.values()])
    geos = {s.geography_id: s.geography for s in chosen.values()}
    out = [
        _summary(g, chosen.get((gid, "rent_index")), chosen.get((gid, "home_value")), obs)
        for gid, g in geos.items()
    ]
    out.sort(key=lambda m: (m.geography.kind != "country", m.geography.size_rank or 10**9))
    return out


@router.get("/indicators")
def indicators(db: DbSession) -> list[Indicator]:
    """National series for the ticker tape and macro panel."""
    us = db.scalar(select(Geography).where(Geography.kind == "country"))
    if us is None:
        return []
    chosen = best_series(db, [m for m, _ in INDICATORS], [us.id])
    obs = observations(db, [s.id for s in chosen.values()])
    out = []
    for metric, label in INDICATORS:
        s = chosen.get((us.id, metric))
        if s is None:
            continue
        points = obs.get(s.id, [])
        cutoff = shift_months(points[-1][0], -SPARK_MONTHS) if points else None
        out.append(
            Indicator(
                metric=metric,
                label=label,
                unit=s.unit,
                frequency=s.frequency,
                source=s.source,
                demo=s.source == DEMO_SOURCE,
                stats=stats(points),
                spark=[Point(date=d, value=v) for d, v in points if cutoff and d >= cutoff],
            )
        )
    return out


@router.get("/sources")
def sources(db: DbSession) -> SourcesOut:
    runs = db.scalars(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(20))
    return SourcesOut(
        runs=[
            RunOut(
                id=r.id,
                source=r.source,
                status=r.status,
                started_at=_utc(r.started_at),
                finished_at=_utc(r.finished_at) if r.finished_at else None,
                series_count=r.series_count,
                observation_count=r.observation_count,
                error=r.error,
            )
            for r in runs
        ],
        attributions=ATTRIBUTIONS,
    )


@router.get("/{geography_id}")
def market_detail(geography_id: int, db: DbSession) -> MarketDetail:
    geo = db.get(Geography, geography_id)
    if geo is None:
        raise HTTPException(404, detail="market not found")
    chosen = best_series(db, LOCAL_METRICS, [geo.id])
    obs = observations(db, [s.id for s in chosen.values()])
    rent, value = chosen.get((geo.id, "rent_index")), chosen.get((geo.id, "home_value"))
    return MarketDetail(
        summary=_summary(geo, rent, value, obs),
        series=[
            SeriesOut(
                metric=s.metric,
                unit=s.unit,
                frequency=s.frequency,
                source=s.source,
                attribution=ATTRIBUTIONS.get(s.source, s.source),
                stats=stats(obs.get(s.id, [])),
                points=[Point(date=d, value=v) for d, v in obs.get(s.id, [])],
            )
            for s in (rent, value)
            if s is not None
        ],
    )
