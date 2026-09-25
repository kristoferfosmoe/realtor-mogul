import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from mogul.db.models import Base, Geography, Listing
from mogul.ingest.base import RawFile
from mogul.listings.normalize import address_key, default_units, match_market, property_type
from mogul.listings.sources import (
    RentCastSource,
    parse_listing_csv,
    parse_rentcast,
)
from mogul.listings.store import price_cut, store_listings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all(
            [
                Geography(kind="msa", name="Memphis, TN", external_ids={}),
                Geography(
                    kind="msa", name="Miami-Fort Lauderdale-West Palm Beach, FL", external_ids={}
                ),
            ]
        )
        s.commit()
        yield s


def test_address_key_matches_formatting_variants() -> None:
    a = address_key("500 Harbor Way #4B", "Tampa", "FL", "33602-1234")
    b = address_key("500 HARBOR WAY, Apt 4B", "tampa", "fl", "33602")
    assert a == b == "500 harbor way unit 4b tampa fl 33602"
    assert address_key("12 North Oak Street", "X", "TN", None) == "12 n oak st x tn"


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ("Single Family Residential", "single_family"),
        ("Multi-Family (2-4 Unit)", "multi_2_4"),
        ("Multi-Family (5+ Unit)", "multifamily"),
        ("Condo/Co-op", "condo"),
        ("Townhouse", "condo"),
        ("Vacant Land", "land"),
        ("Duplex", "multi_2_4"),
        (None, "single_family"),
    ],
)
def test_property_type(raw: str | None, kind: str) -> None:
    assert property_type(raw) == kind


def test_default_units() -> None:
    assert default_units("multi_2_4", "Triplex") == (3, False)
    assert default_units("multi_2_4", "Multi-Family") == (2, True)
    assert default_units("single_family") == (1, False)


def test_match_market_principal_cities_only() -> None:
    metros = [(1, "Memphis, TN"), (2, "Miami-Fort Lauderdale-West Palm Beach, FL")]
    assert match_market("Memphis", "TN", metros) == 1
    assert match_market("fort lauderdale", "fl", metros) == 2
    assert match_market("Memphis", "FL", metros) is None
    assert match_market("Germantown", "TN", metros) is None


def test_parse_rentcast() -> None:
    items = json.loads((FIXTURES / "rentcast_sale.json").read_text())
    sa = parse_rentcast(items[0])
    assert sa is not None
    assert (sa.address, sa.city, sa.state, sa.zip) == (
        "5500 Grand Lake Dr",
        "San Antonio",
        "TX",
        "78244",
    )
    assert (sa.beds, sa.sqft, sa.hoa_monthly, sa.price) == (3, 1878, 175.0, 229900.0)
    assert sa.listed_date == date(2024, 6, 24)
    assert sa.history == (
        (date(2024, 6, 24), "listed", 234900),
        (date(2024, 8, 10), "price_change", 229900),
    )
    multi = parse_rentcast(items[1])
    assert multi is not None and (multi.property_type, multi.units, multi.units_inferred) == (
        "multi_2_4",
        2,
        True,
    )
    assert parse_rentcast(items[2]) is None


def test_rentcast_requires_configuration() -> None:
    with pytest.raises(ValueError, match="RENTCAST_API_KEY"):
        RentCastSource("", ["Memphis, TN"])
    with pytest.raises(ValueError, match="LISTING_AREAS"):
        RentCastSource("key", [])
    files = [RawFile("x.json", (FIXTURES / "rentcast_sale.json").read_bytes())]
    assert len(list(RentCastSource("key", ["Memphis, TN"]).parse(files))) == 2


def test_parse_redfin_export() -> None:
    source, rows = parse_listing_csv((FIXTURES / "redfin_export.csv").read_text())
    assert source == "redfin"
    assert len(rows) == 3  # disclaimer row skipped
    sfr, multi, condo = rows
    assert (sfr.source_id, sfr.price, sfr.beds, sfr.sqft, sfr.days_on_market) == (
        "10180001",
        189000,
        3,
        1540,
        12,
    )
    assert sfr.url and sfr.url.startswith("https://www.redfin.com/")
    assert (multi.property_type, multi.units, multi.units_inferred) == ("multi_2_4", 2, True)
    assert (condo.property_type, condo.hoa_monthly, condo.status) == ("condo", 410, "pending")


def test_parse_generic_csv_with_rent_and_units() -> None:
    source, [row] = parse_listing_csv(
        "Address,City,State,Price,Units,Gross Rent,Property Type\n"
        '"12 Elm St",Columbus,OH,"$410,000",4,"$4,200",Fourplex\n'
    )
    assert source == "csv"
    assert (row.units, row.units_inferred, row.stated_rent, row.price) == (4, False, 4200, 410000)
    assert len(row.source_id) == 24  # hash of the address when there's no MLS number


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("City,State\nx,y\n", "Address and Price"),
        ("Address,Price\nx,abc\n", "line 2"),
    ],
)
def test_csv_errors(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_listing_csv(text)


def test_store_tracks_price_changes_and_delistings(session: Session) -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    _, rows = parse_listing_csv((FIXTURES / "redfin_export.csv").read_text())
    first = store_listings(session, "redfin", rows, now=t0)
    assert (first.new, first.updated) == (3, 0)
    sfr = session.scalars(select(Listing).where(Listing.source_id == "10180001")).one()
    assert sfr.market_id == 1  # Memphis
    assert [e.event for e in sfr.events] == ["listed"]

    cut = [
        r if r.source_id != "10180001" else type(r)(**{**r.__dict__, "price": 179000.0})
        for r in rows
    ]
    second = store_listings(session, "redfin", cut[:2], full_sweep=True, now=t0 + timedelta(days=3))
    assert (second.new, second.updated, second.price_changes, second.delisted) == (0, 2, 1, 0)
    session.flush()
    assert [e.event for e in sfr.events] == ["listed", "price_change"]
    assert price_cut(sfr) == pytest.approx(179000 / 189000 - 1)
    condo = session.scalars(select(Listing).where(Listing.property_type == "condo")).one()
    assert condo.status == "pending"  # not active, so the sweep leaves it alone

    # A sweep that no longer returns an active listing marks it off-market.
    third = store_listings(session, "redfin", cut[:1], full_sweep=True, now=t0 + timedelta(days=4))
    assert third.delisted == 1
    multi = session.scalars(select(Listing).where(Listing.property_type == "multi_2_4")).one()
    assert multi.status == "off_market" and multi.events[-1].event == "delisted"
