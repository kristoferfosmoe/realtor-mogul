from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mogul.api.app import create_app
from mogul.api.routes import screener
from mogul.config import Settings
from mogul.db.models import Base, IngestionRun, Listing
from mogul.db.session import get_session
from mogul.ingest.base import RawFile
from mogul.ingest.census import AcsSource
from mogul.ingest.hud import HudFmrSource
from mogul.ingest.pipeline import store
from mogul.listings.comps import run_comps
from mogul.listings.sources import RentCastSource
from mogul.listings.store import store_listings
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


@pytest.fixture
def listings(db: Session) -> None:
    """Zillow/FRED-shaped markets, then RentCast listings in San Antonio and Memphis."""
    seed_markets(db)
    files = [RawFile("sale.json", (FIXTURES / "rentcast_sale.json").read_bytes())]
    store_listings(db, "rentcast", RentCastSource("key", ["x, TN"]).parse(files))
    db.commit()


def _benchmarks(db: Session) -> None:
    hud = [RawFile("2026_TN.json", (FIXTURES / "hud_statedata_tn_2026.json").read_bytes())]
    store(db, "hud", HudFmrSource("t").parse(hud))
    acs = [
        RawFile("2024_us.json", (FIXTURES / "acs_us_2024.json").read_bytes()),
        RawFile("2024_metro.json", (FIXTURES / "acs_metro_2024.json").read_bytes()),
        RawFile("2024_zip.json", (FIXTURES / "acs_zip_2024.json").read_bytes()),
    ]
    store(db, "census", AcsSource().parse(acs))
    db.commit()


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


def test_recommendations(client: TestClient, listings: None) -> None:
    box = client.get("/buy-boxes").json()[0]
    body = client.get(f"/buy-boxes/{box['id']}/recommendations").json()
    s = body["summary"]
    assert s["scanned"] == 2 and s["evaluated"] + s["filtered_out"] == 2
    assert s["evaluated"] >= 1
    assert "demo" not in s
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


def test_override_rent_and_add_to_watchlist(client: TestClient, listings: None) -> None:
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


def test_import_csv_and_alerts(client: TestClient, listings: None) -> None:
    box = client.get("/buy-boxes").json()[0]  # created (and "viewed") after the first load
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
    assert [r["source"] for r in sources["runs"]] == ["redfin", "redfin"]
    # Listing runs stay out of the Markets page's source list.
    assert client.get("/markets/sources").json()["runs"] == []


def test_bad_import_and_missing_rows(client: TestClient) -> None:
    assert client.post("/listings/import", json={"csv": "a,b\n"}).status_code == 422
    box = client.get("/buy-boxes").json()[0]
    assert client.get("/listings/99", params={"buy_box_id": box["id"]}).status_code == 404
    assert client.get("/buy-boxes/99/recommendations").status_code == 404


def test_rent_uses_zip_position_and_hud_rents_where_zillow_has_none(
    client: TestClient, db: Session
) -> None:
    seed_markets(db)
    _benchmarks(db)
    csv = (
        "Address,City,State,Zip,Price,Beds,Property Type\n"
        "4417 Walnut Grove Rd,Memphis,TN,38117,189000,3,Single Family\n"
        "1 Music Row,Nashville,TN,37203,300000,3,Single Family\n"
    )
    assert client.post("/listings/import", json={"csv": csv}).json()["new"] == 2
    box = client.get("/buy-boxes").json()[0]
    rows = client.get(f"/buy-boxes/{box['id']}/recommendations").json()["rows"]
    rent = {r["listing"]["city"]: r["rent"] for r in rows}

    # Memphis: Zillow typical rent, scaled by ZIP 38117 vs the metro (ACS 1374 / 1145).
    assert rent["Memphis"]["source"] == "model"
    assert "Memphis typical rent" in rent["Memphis"]["basis"]
    assert "ZIP 38117 ×1.20" in rent["Memphis"]["basis"]
    # Nashville has no Zillow data here, so HUD's 3-bedroom fair market rent is used.
    assert rent["Nashville"]["basis"].startswith("Nashville HUD fair market rent 3BR $2,195")
    assert rent["Nashville"]["monthly"] == 2200


class _RentCast:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["X-Api-Key"] == "key"
        return httpx.Response(200, content=(FIXTURES / "rentcast_rent_avm.json").read_bytes())

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def test_rent_comps_endpoint(
    client: TestClient,
    db: Session,
    listings: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    box = client.get("/buy-boxes").json()[0]
    multi = db.scalars(select(Listing).where(Listing.city == "Memphis")).one()
    url = f"/listings/{multi.id}/rent-comps?buy_box_id={box['id']}"

    monkeypatch.setattr(screener, "get_settings", lambda: Settings(rentcast_api_key=""))
    res = client.post(url)
    assert res.status_code == 422 and "MOGUL_RENTCAST_API_KEY" in res.json()["detail"]

    rentcast = _RentCast()
    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[screener.rentcast_client] = rentcast.client
    monkeypatch.setattr(
        screener,
        "get_settings",
        lambda: Settings(rentcast_api_key="key", raw_data_dir=str(tmp_path)),
    )
    detail = client.post(url).json()
    # A duplex with 4 beds is looked up as one 2-bed unit, then doubled.
    [request] = rentcast.requests
    assert request.url.params["bedrooms"] == "2"
    assert request.url.params["propertyType"] == "Multi-Family"
    assert request.url.params["address"] == "12 Oak St, Memphis, TN 38104"
    assert detail["rent"]["source"] == "comps" and detail["rent"]["confidence"] == "medium"
    assert detail["rent"]["monthly"] == 2900
    assert "from 2 comps" in detail["rent"]["basis"]
    comps = detail["listing"]["rent_comps"]
    assert comps["per_unit"] == 1450 and comps["units"] == 2
    assert comps["comps"][0]["address"] == "4401 Walnut Grove Rd, Memphis, TN 38117"
    assert list((tmp_path / "rentcast-avm").iterdir())  # raw response archived

    # An override still beats comps.
    client.patch(f"/listings/{multi.id}", json={"rent_override": 3000})
    again = client.get(f"/listings/{multi.id}", params={"buy_box_id": box["id"]}).json()
    assert again["rent"]["source"] == "override"


def test_rents_command_spends_lookups_on_candidates_only(
    client: TestClient, db: Session, listings: None, tmp_path: Path
) -> None:
    client.get("/buy-boxes")  # creates the default buy box
    rentcast = _RentCast()
    first = run_comps(db, rentcast.client(), "key", tmp_path, limit=1)
    assert (first.status, first.series_count) == ("ok", 1)
    assert len(rentcast.requests) == 1
    # The next run skips the listing whose comps are fresh.
    second = run_comps(db, rentcast.client(), "key", tmp_path, limit=5)
    assert second.series_count == 1 and len(rentcast.requests) == 2
    third = run_comps(db, rentcast.client(), "key", tmp_path, limit=5)
    assert third.series_count == 0 and len(rentcast.requests) == 2
    assert all(x.rent_comps for x in db.scalars(select(Listing)))

    failed = run_comps(db, rentcast.client(), "", tmp_path, limit=5)
    assert failed.status == "error" and "MOGUL_RENTCAST_API_KEY" in (failed.error or "")
    assert set(db.scalars(select(IngestionRun.source))) == {"rentcast-rents"}
    runs = client.get("/listings/sources").json()["runs"]
    assert runs[0]["source"] == "rentcast-rents" and runs[0]["status"] == "error"
