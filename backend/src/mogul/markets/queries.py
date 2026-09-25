"""Read market data out of the database."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from mogul.db.models import Geography, MarketObservation, MarketSeries


def best_series(
    session: Session,
    metrics: Iterable[str],
    geography_ids: Iterable[int] | None = None,
) -> dict[tuple[int, str], MarketSeries]:
    """One series per (geography, metric) for the overall ("all") segment.

    Metrics are source-specific (ZORI is `rent_index`, HUD is `fair_market_rent`), so
    two sources rarely collide; when they do, the series stored first wins.
    """
    q = (
        select(MarketSeries)
        .options(joinedload(MarketSeries.geography))
        .where(MarketSeries.metric.in_(list(metrics)), MarketSeries.segment == "all")
        .order_by(MarketSeries.id)
    )
    if geography_ids is not None:
        q = q.where(MarketSeries.geography_id.in_(list(geography_ids)))
    chosen: dict[tuple[int, str], MarketSeries] = {}
    for s in session.scalars(q):
        chosen.setdefault((s.geography_id, s.metric), s)
    return chosen


def observations(
    session: Session, series_ids: Iterable[int], since: date | None = None
) -> dict[int, list[tuple[date, float]]]:
    ids = list(series_ids)
    out: dict[int, list[tuple[date, float]]] = defaultdict(list)
    if not ids:
        return out
    q = select(MarketObservation.series_id, MarketObservation.date, MarketObservation.value).where(
        MarketObservation.series_id.in_(ids)
    )
    if since is not None:
        q = q.where(MarketObservation.date >= since)
    for sid, d, v in session.execute(
        q.order_by(MarketObservation.series_id, MarketObservation.date)
    ):
        out[sid].append((d, v))
    return out


@dataclass(frozen=True)
class Latest:
    geography: Geography
    metric: str
    source: str
    segment: str
    date: date
    value: float


def latest_values(
    session: Session,
    metric: str | Iterable[str],
    *,
    kind: str | None = None,
    names: Iterable[str] | None = None,
) -> list[Latest]:
    """The newest observation of every series of `metric` (one or several), optionally
    limited to one kind of geography and to some geography names."""
    series = (
        select(MarketSeries.id)
        .join(Geography, MarketSeries.geography_id == Geography.id)
        .where(MarketSeries.metric.in_([metric] if isinstance(metric, str) else list(metric)))
    )
    if kind is not None:
        series = series.where(Geography.kind == kind)
    if names is not None:
        series = series.where(Geography.name.in_(list(names)))
    newest = (
        select(MarketObservation.series_id, func.max(MarketObservation.date).label("d"))
        .where(MarketObservation.series_id.in_(series))
        .group_by(MarketObservation.series_id)
        .subquery()
    )
    q = (
        select(MarketSeries, MarketObservation.date, MarketObservation.value)
        .options(joinedload(MarketSeries.geography))
        .join(newest, newest.c.series_id == MarketSeries.id)
        .join(
            MarketObservation,
            (MarketObservation.series_id == newest.c.series_id)
            & (MarketObservation.date == newest.c.d),
        )
        .order_by(MarketSeries.id)
    )
    return [
        Latest(s.geography, s.metric, s.source, s.segment, d, v) for s, d, v in session.execute(q)
    ]
