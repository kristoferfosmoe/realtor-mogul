from collections.abc import Iterator
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mogul.api.app import create_app
from mogul.db.models import Base
from mogul.db.session import get_session
from mogul.ingest.base import RawFile
from mogul.ingest.census import AcsSource
from mogul.ingest.hud import HudFmrSource
from mogul.ingest.pipeline import run_source, store
from tests.market_data import seed_markets

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as c:
        yield c


def test_empty_database(client: TestClient) -> None:
    assert client.get("/markets").json() == []
    assert client.get("/markets/indicators").json() == []
    assert client.get("/markets/999").status_code == 404


def test_markets(client: TestClient, db: Session) -> None:
    seed_markets(db, end=date(2025, 6, 30))

    markets = client.get("/markets").json()
    assert markets[0]["geography"]["kind"] == "country"
    assert [m["geography"]["name"] for m in markets[1:]] == ["Tampa, FL", "Memphis, TN"]
    memphis = markets[2]
    assert memphis["sources"] == ["zillow"]
    assert "demo" not in memphis
    assert memphis["rent"]["latest_date"] == "2025-06-30"
    assert 0 < memphis["gross_yield"] < 0.2
    assert len(memphis["rent_spark"]) == 24

    detail = client.get(f"/markets/{memphis['geography']['id']}").json()
    assert {s["metric"] for s in detail["series"]} == {"rent_index", "home_value"}
    assert all(len(s["points"]) == 78 for s in detail["series"])
    assert detail["benchmarks"] == []

    indicators = client.get("/markets/indicators").json()
    assert [i["label"] for i in indicators] == [
        "US Rent",
        "US Home Value",
        "30Y Mortgage",
        "CPI Rent",
        "Rental Vacancy",
    ]
    assert all("demo" not in i for i in indicators)


def test_hud_and_census_benchmarks_join_zillow_metros(client: TestClient, db: Session) -> None:
    seed_markets(db)
    hud = [RawFile("2026_TN.json", (FIXTURES / "hud_statedata_tn_2026.json").read_bytes())]
    store(db, "hud", HudFmrSource("t").parse(hud))
    acs = [
        RawFile("2024_metro.json", (FIXTURES / "acs_metro_2024.json").read_bytes()),
        RawFile("2024_zip.json", (FIXTURES / "acs_zip_2024.json").read_bytes()),
    ]
    store(db, "census", AcsSource().parse(acs))
    db.commit()

    # HUD- and Census-only places (Nashville, ZIPs) have no rent index: not listed.
    markets = client.get("/markets").json()
    assert [m["geography"]["name"] for m in markets] == [
        "United States",
        "Tampa, FL",
        "Memphis, TN",
    ]
    memphis = markets[2]
    detail = client.get(f"/markets/{memphis['geography']['id']}").json()
    assert [(b["metric"], b["segment"], b["value"]) for b in detail["benchmarks"]] == [
        ("fair_market_rent", "0br", 1011),
        ("fair_market_rent", "1br", 1074),
        ("fair_market_rent", "2br", 1229),
        ("fair_market_rent", "3br", 1594),
        ("fair_market_rent", "4br", 1742),
        ("median_gross_rent", "all", 1145),
    ]
    assert detail["benchmarks"][0]["date"] == "2025-10-01"
    assert detail["benchmarks"][-1]["source"] == "census"


def test_sources_log_runs_with_attribution(client: TestClient, db: Session, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        clause = request.url.params["for"]
        name = "acs_us_2024.json" if clause.startswith("us") else "acs_metro_2024.json"
        if clause.startswith("zip"):
            name = "acs_zip_2024.json"
        return httpx.Response(200, content=(FIXTURES / name).read_bytes())

    source = AcsSource(years=1, today=date(2025, 9, 1))
    run = run_source(db, source, httpx.Client(transport=httpx.MockTransport(handler)), tmp_path)
    assert run.status == "ok", run.error

    body = client.get("/markets/sources").json()
    [latest] = body["runs"]
    assert latest["source"] == "census" and latest["status"] == "ok"
    assert latest["started_at"].endswith(("Z", "+00:00"))
    assert set(body["attributions"]) == {"zillow", "fred", "hud", "census"}
