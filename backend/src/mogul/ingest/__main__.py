"""Command line: python -m mogul.ingest {run,listings,rents,reparse,status}."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from mogul.config import get_settings
from mogul.db.models import IngestionRun
from mogul.db.session import get_engine

from . import SOURCES, missing_config
from .base import Source
from .pipeline import load_archive, run_source, store

USER_AGENT = "RealtorMogul/0.1 (+https://github.com/kristoferfosmoe/realtor-mogul)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mogul.ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="download and store market data")
    run.add_argument(
        "source", choices=[*SOURCES, "all"], help="all = every source that is configured"
    )
    reparse = sub.add_parser("reparse", help="re-store an archived raw download")
    reparse.add_argument("source", choices=list(SOURCES))
    reparse.add_argument("folder", type=Path)
    listings = sub.add_parser("listings", help="fetch for-sale listings")
    listings.add_argument("source", choices=["rentcast"])
    rents = sub.add_parser(
        "rents", help="fetch RentCast rent comps for listings that pass a buy box's filters"
    )
    rents.add_argument("--limit", type=int, default=20, help="most lookups (API calls) to make")
    rents.add_argument("--max-age-days", type=int, default=90, help="refresh comps older than this")
    sub.add_parser("status", help="show recent ingestion runs")
    args = parser.parse_args(argv)

    settings = get_settings()
    with Session(get_engine()) as session:
        if args.cmd == "run":
            names = list(SOURCES) if args.source == "all" else [args.source]
            sources: list[Source] = []
            for name in names:
                missing = missing_config(name, settings)
                if missing is None:
                    sources.append(SOURCES[name](settings))
                elif args.source == "all":
                    print(f"[SKIP ] {name:7} not configured: {missing}")
                else:
                    print(f"error: {missing}", file=sys.stderr)
                    return 2
            ok = True
            with _client() as client:
                for source in sources:
                    result = run_source(session, source, client, Path(settings.raw_data_dir))
                    print(_describe(result))
                    ok &= result.status == "ok"
            return 0 if ok else 1
        if args.cmd == "listings":
            from mogul.listings.sources import RentCastSource
            from mogul.listings.store import run_listing_source

            try:
                src = RentCastSource(settings.rentcast_api_key, settings.listing_areas)
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            with _client() as client:
                result = run_listing_source(session, src, client, Path(settings.raw_data_dir))
            print(
                _describe(result)
                .replace("series", "listings")
                .replace("observations", "price changes")
            )
            return 0 if result.status == "ok" else 1
        if args.cmd == "rents":
            from mogul.listings.comps import run_comps

            with _client() as client:
                result = run_comps(
                    session,
                    client,
                    settings.rentcast_api_key,
                    Path(settings.raw_data_dir),
                    limit=args.limit,
                    max_age_days=args.max_age_days,
                )
            print(_describe(result).split("  ")[0] + f"  {result.series_count} listings updated")
            if result.error:
                print(f"error: {result.error}", file=sys.stderr)
            return 0 if result.status == "ok" else 1
        if args.cmd == "reparse":
            source = SOURCES[args.source](settings)
            n_series, n_obs = store(session, source.name, source.parse(load_archive(args.folder)))
            session.commit()
            print(f"{args.source}: re-stored {n_series} series, {n_obs} observations")
            return 0
        runs = session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(10))
        for r in runs:
            print(_describe(r))
        return 0


def _client() -> httpx.Client:
    return httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def _describe(r: IngestionRun) -> str:
    base = f"[{r.status.upper():5}] {r.source:7} {r.started_at:%Y-%m-%d %H:%M}"
    if r.status == "error":
        return f"{base}  {r.error}"
    return f"{base}  {r.series_count} series, {r.observation_count} observations"


if __name__ == "__main__":
    sys.exit(main())
