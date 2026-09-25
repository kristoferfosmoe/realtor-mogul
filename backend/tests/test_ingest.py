from collections.abc import Iterable, Iterator, Sequence
from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from mogul.db.models import Base, Geography, IngestionRun, MarketObservation, MarketSeries
from mogul.ingest.base import US, GeoRef, ParsedSeries, RawFile
from mogul.ingest.demo import DemoSource
from mogul.ingest.fred import FredSource, parse_csv
from mogul.ingest.pipeline import load_archive, run_source, store
from mogul.ingest.zillow import ZillowSource

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _zillow_files() -> list[RawFile]:
    return [RawFile("metro_zori.csv", (FIXTURES / "zillow_metro_zori.csv").read_bytes())]


def test_zillow_parses_country_and_top_metros() -> None:
    series = list(ZillowSource(max_metros=100).parse(_zillow_files()))
    by_name = {s.geography.name: s for s in series}
    assert set(by_name) == {"United States", "New York, NY", "Chicago, IL"}  # rank 500 cut

    ny = by_name["New York, NY"]
    assert ny.metric == "rent_index" and ny.unit == "usd" and ny.frequency == "monthly"
    assert ny.source_key == "zori:394913"
    assert ny.geography == GeoRef("msa", "New York, NY", "NY", 1, {"zillow": 394913})
    # Blank cells are skipped, not zero.
    assert ny.observations[0] == (date(2023, 11, 30), 3100.0)
    assert by_name["United States"].geography == US


def test_zillow_ignores_unknown_files() -> None:
    assert list(ZillowSource().parse([RawFile("other.csv", b"a,b\n1,2\n")])) == []


def test_fred_parses_current_header_and_missing_values() -> None:
    obs = parse_csv((FIXTURES / "fred_mortgage.csv").read_bytes(), "MORTGAGE30US")
    assert obs == [(date(2024, 10, 3), 6.12), (date(2024, 10, 17), 6.44)]


def test_fred_parses_legacy_header() -> None:
    obs = parse_csv((FIXTURES / "fred_cpi_legacy_header.csv").read_bytes(), "CUSR0000SEHA")
    assert obs[-1] == (date(2024, 10, 1), 421.9)


def test_fred_rejects_wrong_series() -> None:
    with pytest.raises(ValueError, match="unexpected FRED header"):
        parse_csv(b"observation_date,OTHER\n2024-01-01,1\n", "MORTGAGE30US")


def test_fred_converts_percent_to_decimal() -> None:
    files = [RawFile("MORTGAGE30US.csv", (FIXTURES / "fred_mortgage.csv").read_bytes())]
    [series] = FredSource().parse(files)
    assert series.metric == "mortgage_rate_30y" and series.unit == "rate"
    assert series.observations[0][1] == pytest.approx(0.0612)


class FakeSource:
    name = "fake"
    attribution = "test"

    def __init__(self, value: float = 1.0, fail: bool = False) -> None:
        self.value, self.fail = value, fail

    def fetch(self, client: httpx.Client) -> list[RawFile]:
        if self.fail:
            raise httpx.ConnectError("offline")
        return [RawFile("data.txt", b"payload")]

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedSeries]:
        geo = GeoRef("msa", "Austin, TX", "TX", 30, {"zillow": 1})
        yield ParsedSeries(
            "rent:austin",
            "rent_index",
            "monthly",
            geo,
            [(date(2024, 1, 31), 1500 * self.value), (date(2024, 2, 29), 1510 * self.value)],
        )


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_run_archives_stores_and_logs(session: Session, tmp_path: Path) -> None:
    run = run_source(session, FakeSource(), httpx.Client(), tmp_path)
    assert run.status == "ok" and run.error is None
    assert (run.series_count, run.observation_count) == (1, 2)
    assert run.raw_path and load_archive(Path(run.raw_path)) == [RawFile("data.txt", b"payload")]
    geo = session.scalars(select(Geography)).one()
    assert (geo.name, geo.state, geo.size_rank, geo.external_ids) == (
        "Austin, TX",
        "TX",
        30,
        {"zillow": 1},
    )
    assert _count(session, MarketObservation) == 2


def test_rerun_upserts_instead_of_duplicating(session: Session, tmp_path: Path) -> None:
    run_source(session, FakeSource(1.0), httpx.Client(), tmp_path)
    run_source(session, FakeSource(2.0), httpx.Client(), tmp_path)
    assert _count(session, MarketSeries) == 1
    assert _count(session, MarketObservation) == 2
    values = session.scalars(select(MarketObservation.value).order_by(MarketObservation.date))
    assert list(values) == [3000, 3020]
    assert _count(session, IngestionRun) == 2


def test_failed_fetch_is_recorded_and_keeps_existing_data(session: Session, tmp_path: Path) -> None:
    run_source(session, FakeSource(), httpx.Client(), tmp_path)
    run = run_source(session, FakeSource(fail=True), httpx.Client(), tmp_path)
    assert run.status == "error"
    assert run.error == "ConnectError: offline"
    assert run.finished_at is not None
    assert _count(session, MarketObservation) == 2


def test_real_run_purges_demo_data(session: Session, tmp_path: Path) -> None:
    run_source(session, DemoSource(end=date(2024, 12, 31)), httpx.Client(), tmp_path)
    assert session.scalar(select(func.count()).where(MarketSeries.source == "demo"))
    run_source(session, FakeSource(), httpx.Client(), tmp_path)
    assert list(session.scalars(select(MarketSeries.source).distinct())) == ["fake"]
    # Demo-only geographies are removed; the one with real data remains.
    assert list(session.scalars(select(Geography.name))) == ["Austin, TX"]


def test_demo_is_deterministic_and_complete() -> None:
    a = list(DemoSource(end=date(2024, 12, 31)).parse([]))
    b = list(DemoSource(end=date(2024, 12, 31)).parse([]))
    assert a == b
    metrics = {s.metric for s in a}
    assert metrics == {
        "rent_index",
        "home_value",
        "mortgage_rate_30y",
        "cpi_rent",
        "rental_vacancy",
    }
    rent = next(s for s in a if s.source_key == "rent:US")
    assert rent.observations[-1][0] == date(2024, 12, 31)


def test_store_merges_external_ids_across_sources(session: Session) -> None:
    geo_a = GeoRef("msa", "Austin, TX", external_ids={"zillow": 1})
    geo_b = GeoRef("msa", "Austin, TX", "TX", external_ids={"cbsa": "12420"})
    store(session, "a", [ParsedSeries("k", "rent_index", "monthly", geo_a, [])])
    store(session, "b", [ParsedSeries("k", "home_value", "monthly", geo_b, [])])
    geo = session.scalars(select(Geography)).one()
    assert geo.external_ids == {"zillow": 1, "cbsa": "12420"}
    assert geo.state == "TX"
