"""Command line: python -m mogul.ingest {run,demo,reparse,status}."""

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

from . import SOURCES
from .demo import DemoSource
from .pipeline import load_archive, purge_source, run_source, store

USER_AGENT = "RealtorMogul/0.1 (+https://github.com/kristoferfosmoe/realtor-mogul)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mogul.ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="download and store market data")
    run.add_argument("source", choices=[*SOURCES, "all"])
    sub.add_parser("demo", help="load synthetic demo data (no network needed)")
    reparse = sub.add_parser("reparse", help="re-store an archived raw download")
    reparse.add_argument("source", choices=list(SOURCES))
    reparse.add_argument("folder", type=Path)
    listings = sub.add_parser("listings", help="fetch for-sale listings")
    listings.add_argument("source", choices=["rentcast", "demo"])
    sub.add_parser("status", help="show recent ingestion runs")
    args = parser.parse_args(argv)

    settings = get_settings()
    with Session(get_engine()) as session:
        if args.cmd == "run":
            names = list(SOURCES) if args.source == "all" else [args.source]
            ok = True
            with httpx.Client(
                timeout=120, follow_redirects=True, headers={"User-Agent": USER_AGENT}
            ) as client:
                for name in names:
                    result = run_source(
                        session, SOURCES[name](settings), client, Path(settings.raw_data_dir)
                    )
                    print(_describe(result))
                    ok &= result.status == "ok"
            return 0 if ok else 1
        if args.cmd == "demo":
            purge_source(session, "demo")
            result = run_source(session, DemoSource(), httpx.Client(), Path(settings.raw_data_dir))
            print(_describe(result))
            return 0 if result.status == "ok" else 1
        if args.cmd == "listings":
            from mogul.listings.sources import DemoListingSource, ListingSource, RentCastSource
            from mogul.listings.store import run_listing_source

            try:
                src: ListingSource = (
                    DemoListingSource()
                    if args.source == "demo"
                    else RentCastSource(settings.rentcast_api_key, settings.listing_areas)
                )
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            with httpx.Client(
                timeout=120, follow_redirects=True, headers={"User-Agent": USER_AGENT}
            ) as client:
                result = run_listing_source(session, src, client, Path(settings.raw_data_dir))
            print(
                _describe(result)
                .replace("series", "listings")
                .replace("observations", "price changes")
            )
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


def _describe(r: IngestionRun) -> str:
    base = f"[{r.status.upper():5}] {r.source:7} {r.started_at:%Y-%m-%d %H:%M}"
    if r.status == "error":
        return f"{base}  {r.error}"
    return f"{base}  {r.series_count} series, {r.observation_count} observations"


if __name__ == "__main__":
    sys.exit(main())
