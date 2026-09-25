"""Run a source end to end: fetch → archive raw files → parse → upsert → log the run."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from mogul.db.models import Geography, IngestionRun, MarketObservation, MarketSeries

from .base import GeoRef, ParsedSeries, RawFile, Source

DEMO_SOURCE = "demo"
_CHUNK = 500


def run_source(
    session: Session, source: Source, client: httpx.Client, raw_dir: Path
) -> IngestionRun:
    """Ingest one source. Failures are recorded on the run rather than raised."""
    run = IngestionRun(source=source.name, status="running", started_at=datetime.now(UTC))
    session.add(run)
    session.commit()
    run_id = run.id
    try:
        files = source.fetch(client)
        if files:
            run.raw_path = str(archive(raw_dir, source.name, run.started_at, files))
        run.series_count, run.observation_count = store(session, source.name, source.parse(files))
        if source.name != DEMO_SOURCE:
            purge_source(session, DEMO_SOURCE)  # real data supersedes demo data
        run.status = "ok"
        run.finished_at = datetime.now(UTC)
        session.commit()
    except Exception as e:  # noqa: BLE001 - any failure is reported on the run
        session.rollback()
        run = session.get_one(IngestionRun, run_id)
        run.status = "error"
        run.error = f"{type(e).__name__}: {e}"[:2000]
        run.finished_at = datetime.now(UTC)
        session.commit()
    return run


def archive(raw_dir: Path, source: str, at: datetime, files: Sequence[RawFile]) -> Path:
    folder = raw_dir / source / at.strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        (folder / f.name).write_bytes(f.content)
    return folder


def load_archive(folder: Path) -> list[RawFile]:
    return [RawFile(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()]


def store(session: Session, source: str, parsed: Iterable[ParsedSeries]) -> tuple[int, int]:
    """Upsert geographies, series and observations. Returns (series, observations)."""
    n_series = n_obs = 0
    geo_cache: dict[tuple[str, str], Geography] = {}
    for ps in parsed:
        geo = _upsert_geography(session, ps.geography, geo_cache)
        series = session.scalar(
            select(MarketSeries).where(
                MarketSeries.source == source, MarketSeries.source_key == ps.source_key
            )
        )
        if series is None:
            series = MarketSeries(source=source, source_key=ps.source_key)
            session.add(series)
        series.geography = geo
        series.metric = ps.metric
        series.segment = ps.segment
        series.unit = ps.unit
        series.frequency = ps.frequency
        series.updated_at = datetime.now(UTC)
        session.flush()
        _upsert_observations(session, series.id, ps.observations)
        n_series += 1
        n_obs += len(ps.observations)
    return n_series, n_obs


def purge_source(session: Session, source: str) -> None:
    session.execute(delete(MarketSeries).where(MarketSeries.source == source))
    # Geographies left without any series (only demo ones) go too.
    session.execute(
        delete(Geography).where(~Geography.id.in_(select(MarketSeries.geography_id).distinct()))
    )


def _upsert_geography(
    session: Session, ref: GeoRef, cache: dict[tuple[str, str], Geography]
) -> Geography:
    key = (ref.kind, ref.name)
    geo = cache.get(key) or session.scalar(
        select(Geography).where(Geography.kind == ref.kind, Geography.name == ref.name)
    )
    if geo is None:
        geo = Geography(kind=ref.kind, name=ref.name, external_ids={})
        session.add(geo)
    if ref.state is not None:
        geo.state = ref.state
    if ref.size_rank is not None:
        geo.size_rank = ref.size_rank
    if ref.external_ids:
        geo.external_ids = {**(geo.external_ids or {}), **ref.external_ids}
    cache[key] = geo
    return geo


def _upsert_observations(session: Session, series_id: int, observations: Sequence[Any]) -> None:
    rows = [{"series_id": series_id, "date": d, "value": v} for d, v in observations]
    dialect = session.get_bind().dialect.name
    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i : i + _CHUNK]
        if dialect == "postgresql":
            pg = postgresql.insert(MarketObservation).values(chunk)
            session.execute(
                pg.on_conflict_do_update(
                    index_elements=["series_id", "date"], set_={"value": pg.excluded.value}
                )
            )
        elif dialect == "sqlite":
            lite = sqlite.insert(MarketObservation).values(chunk)
            session.execute(
                lite.on_conflict_do_update(
                    index_elements=["series_id", "date"], set_={"value": lite.excluded.value}
                )
            )
        else:
            raise RuntimeError(f"no upsert support for {dialect}")
