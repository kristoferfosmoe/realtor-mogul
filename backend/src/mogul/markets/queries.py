"""Read market data out of the database, preferring real sources over demo data."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mogul.db.models import MarketObservation, MarketSeries
from mogul.ingest.pipeline import DEMO_SOURCE


def best_series(
    session: Session,
    metrics: Iterable[str],
    geography_ids: Iterable[int] | None = None,
) -> dict[tuple[int, str], MarketSeries]:
    """One series per (geography, metric); a real source wins over demo data."""
    q = (
        select(MarketSeries)
        .options(joinedload(MarketSeries.geography))
        .where(MarketSeries.metric.in_(list(metrics)))
    )
    if geography_ids is not None:
        q = q.where(MarketSeries.geography_id.in_(list(geography_ids)))
    chosen: dict[tuple[int, str], MarketSeries] = {}
    for s in session.scalars(q):
        key = (s.geography_id, s.metric)
        current = chosen.get(key)
        if current is None or (current.source == DEMO_SOURCE and s.source != DEMO_SOURCE):
            chosen[key] = s
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
