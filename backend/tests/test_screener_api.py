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
from mogul.ingest.demo import DemoSource
from mogul.ingest.pipeline import run_source
from mogul.listings.sources import DemoListingSource
from mogul.listings.store import run_listing_source

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


@pytest.fixture
def demo(db: Session, tmp_path: Path) -> None:
    run_source(db, DemoSource(end=date.today()), httpx.Client(), tmp_path)
    run_listing_source(db, DemoListingSource(), httpx.Client(), tmp_path)


def test_default_buy_box_created(client: TestClient) -> None:
    boxes = client.get("/buy-boxes").json()
    assert len(boxes) == 1 and boxes[0]["criteria"]["min_levered_irr"] == 0.12
    assert client.get("/buy-boxes").json() == boxes  # not duplicated


def test_buy_box_crud_and_validation(client: TestClient) -> None:
    created = client.post(
        "/buy-boxes", json={"name": "Duplexes", "criteria": {"property_types": ["multi_2_4"]}}
    )
    assert created.status_code == 201
    box = created.json()
    box["criteria"]["max_price"] = 350000
    updated = client.put(f"/buy-boxes/{box['id']}", json=box).json()
    assert updated["criteria"]["max_price"] == 350000
    bad = client.post("/buy-boxes", json={"name": "x", "criteria": {"property_types": ["castle"]}})
    assert bad.status_code == 422
    assert client.delete(f"/buy-boxes/{box['id']}").status_code == 204


def test_recommendations_with_demo_data(client: TestClient, demo: None) -> None:
    box = client.get("/buy-boxes").json()[0]
    body = client.get(f"/buy-boxes/{box['id']}/recommendations").json()
    s = body["summary"]
    assert s["scanned"] == 75 and s["evaluated"] + s["filtered_out"] == 75
    assert s["demo"] is True
    assert s["interest_rate"] == pytest.approx(0.0621 + 0.0075, abs=0.002)
    scores = [r["evaluation"]["score"] for r in body["rows"]]
    assert scores == sorted(scores, reverse=True)
    top = body["rows"][0]
    assert top["listing"]["price"] <= 500000
    assert top["evaluation"]["reasons"] and top["rent"]["monthly"] > 0
    assert {r["evaluation"]["signal"] for r in body["rows"]} <= {
        "STRONG BUY",
        "BUY",
        "WATCH",
        "PASS",
    }


def test_override_rent_and_add_to_watchlist(client: TestClient, demo: None) -> None:
    box = client.get("/buy-boxes").json()[0]
    row = client.get(f"/buy-boxes/{box['id']}/recommendations").json()["rows"][-1]
    lid = row["listing"]["id"]
    patched = client.patch(f"/listings/{lid}", json={"rent_override": 9999}).json()
    assert patched["rent_override"] == 9999
    detail = client.get(f"/listings/{lid}", params={"buy_box_id": box["id"]}).json()
    assert detail["rent"]["source"] == "override" and detail["rent"]["monthly"] == 9999
    assert detail["events"][0]["event"] == "listed"
    cleared = client.patch(f"/listings/{lid}", json={"rent_override": None}).json()
    assert cleared["rent_override"] is None

    res = client.post(f"/listings/{lid}/watchlist", params={"buy_box_id": box["id"]})
    assert res.status_code == 201
    deal = client.get(f"/deals/{res.json()['deal_id']}").json()
    assert deal["inputs"]["purchase_price"] == row["listing"]["price"]
    assert deal["metrics"]["levered_irr"] == pytest.approx(
        row["evaluation"]["metrics"]["levered_irr"]
    )


def test_import_csv_and_alerts(client: TestClient, demo: None) -> None:
    box = client.get("/buy-boxes").json()[0]  # created (and "viewed") after the demo load
    res = client.post(
        "/listings/import", json={"csv": (FIXTURES / "redfin_export.csv").read_text()}
    )
    assert res.json() == {"source": "redfin", "new": 3, "updated": 0, "price_changes": 0}
    again = client.post(
        "/listings/import", json={"csv": (FIXTURES / "redfin_export.csv").read_text()}
    )
    assert again.json()["new"] == 0 and again.json()["updated"] == 3

    recs = client.get(f"/buy-boxes/{box['id']}/recommendations").json()
    new_rows = [r for r in recs["rows"] if r["is_new"]]
    assert {r["listing"]["source"] for r in new_rows} == {"redfin"}
    alerts = client.get("/screener/alerts").json()
    assert alerts["total_new"] == recs["summary"]["new_matches"]

    assert client.post(f"/buy-boxes/{box['id']}/seen").status_code == 204
    assert client.get("/screener/alerts").json()["total_new"] == 0

    sources = client.get("/listings/sources").json()
    assert sources["rentcast_configured"] is False
    assert {r["source"] for r in sources["runs"]} >= {"redfin", "demo-listings"}
    # Listing runs stay out of the Markets page's source list.
    assert {r["source"] for r in client.get("/markets/sources").json()["runs"]} == {"demo"}


def test_bad_import_and_missing_rows(client: TestClient) -> None:
    assert client.post("/listings/import", json={"csv": "a,b\n"}).status_code == 422
    box = client.get("/buy-boxes").json()[0]
    assert client.get("/listings/99", params={"buy_box_id": box["id"]}).status_code == 404
    assert client.get("/buy-boxes/99/recommendations").status_code == 404
