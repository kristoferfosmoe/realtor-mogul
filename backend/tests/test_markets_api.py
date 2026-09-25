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
from mogul.ingest.base import GeoRef, ParsedSeries
from mogul.ingest.demo import DemoSource
from mogul.ingest.pipeline import run_source, store


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


def test_demo_markets(client: TestClient, db: Session, tmp_path: Path) -> None:
    run_source(db, DemoSource(end=date(2025, 6, 30)), httpx.Client(), tmp_path)

    markets = client.get("/markets").json()
    assert markets[0]["geography"]["kind"] == "country"
    assert [m["geography"]["size_rank"] for m in markets[1:4]] == [1, 2, 3]
    ny = markets[1]
    assert ny["demo"] is True and ny["sources"] == ["demo"]
    assert ny["rent"]["latest_date"] == "2025-06-30"
    assert 0 < ny["gross_yield"] < 0.2
    assert len(ny["rent_spark"]) == 24

    detail = client.get(f"/markets/{ny['geography']['id']}").json()
    assert {s["metric"] for s in detail["series"]} == {"rent_index", "home_value"}
    assert all(len(s["points"]) == 126 for s in detail["series"])

    labels = [i["label"] for i in client.get("/markets/indicators").json()]
    assert labels == ["US Rent", "US Home Value", "30Y Mortgage", "CPI Rent", "Rental Vacancy"]

    runs = client.get("/markets/sources").json()
    assert runs["runs"][0]["status"] == "ok"
    assert runs["runs"][0]["started_at"].endswith(("Z", "+00:00"))
    assert "zillow" in runs["attributions"]


def test_real_series_preferred_over_demo(client: TestClient, db: Session) -> None:
    geo = GeoRef("msa", "Austin, TX", "TX", 9)
    store(db, "demo", [ParsedSeries("d", "rent_index", "monthly", geo, [(date(2024, 1, 31), 1.0)])])
    store(
        db, "zillow", [ParsedSeries("z", "rent_index", "monthly", geo, [(date(2024, 1, 31), 2.0)])]
    )
    db.commit()
    [austin] = client.get("/markets").json()
    assert austin["rent"]["latest"] == 2.0
    assert austin["demo"] is False
