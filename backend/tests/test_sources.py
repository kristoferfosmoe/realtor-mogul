"""HUD Fair Market Rents and Census ACS adapters: parsing and fetching (mocked HTTP)."""

from datetime import date
from pathlib import Path

import httpx
import pytest

from mogul.config import Settings
from mogul.ingest import missing_config
from mogul.ingest.base import US, RawFile, metro_name
from mogul.ingest.census import AcsSource
from mogul.ingest.hud import STATES, HudFmrSource

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Memphis, TN-MS-AR HUD Metro FMR Area", ("Memphis, TN", "TN")),
        ("Nashville-Davidson--Murfreesboro--Franklin, TN Metro Area", ("Nashville, TN", "TN")),
        ("Louisville/Jefferson County, KY-IN Metro Area", ("Louisville, KY", "KY")),
        ("Austin-Round Rock-San Marcos, TX MSA", ("Austin, TX", "TX")),
        ("Somewhere without a state", None),
    ],
)
def test_metro_name_matches_zillow_style(title: str, expected: tuple[str, str] | None) -> None:
    assert metro_name(title) == expected


# ---------------------------------------------------------------- HUD


def _hud_files() -> list[RawFile]:
    return [
        RawFile("2026_TN.json", _fixture("hud_statedata_tn_2026.json")),
        RawFile("2026_MS.json", _fixture("hud_statedata_ms_2026.json")),
        RawFile("2026_TX.json", _fixture("hud_statedata_tx_2026.json")),
        RawFile("2025_TN.json", _fixture("hud_statedata_tn_2025.json")),
    ]


def test_hud_parses_one_series_per_metro_and_bedroom() -> None:
    series = list(HudFmrSource("token").parse(_hud_files()))
    by_key = {s.source_key: s for s in series}
    names = {s.geography.name for s in series}
    assert names == {"Memphis, TN", "Nashville, TN", "Jackson, MS", "Austin, TX", "Fort Worth, TX"}

    memphis = by_key["fmr:METRO32820M32820:2br"]
    assert (memphis.metric, memphis.segment, memphis.unit) == ("fair_market_rent", "2br", "usd")
    assert memphis.frequency == "annual"
    # FY N takes effect October 1 of N-1; the metro appears in TN and MS but once here.
    assert memphis.observations == [(date(2024, 10, 1), 1185.0), (date(2025, 10, 1), 1229.0)]
    assert memphis.geography.state == "TN"
    assert memphis.geography.external_ids == {"hud_fmr": "METRO32820M32820", "cbsa": "32820"}
    assert sum(1 for s in series if s.geography.name == "Memphis, TN") == 5

    # Two areas shorten to "Austin, TX": the principal one (area code == CBSA) wins.
    austin = [s for s in series if s.geography.name == "Austin, TX"]
    assert {s.source_key.split(":")[1] for s in austin} == {"METRO12420M12420"}
    # Blank values are skipped, not zero.
    fort_worth = {s.segment for s in series if s.geography.name == "Fort Worth, TX"}
    assert fort_worth == {"0br", "1br", "2br", "3br"}


def test_hud_ignores_error_bodies() -> None:
    files = [RawFile("2027_TN.json", b'{"error": "no data"}'), RawFile("x.json", b"not json")]
    assert list(HudFmrSource("token").parse(files)) == []


def test_hud_fiscal_years() -> None:
    assert HudFmrSource("t", years=2, today=date(2026, 9, 25)).fiscal_years() == [2027, 2026, 2025]
    assert HudFmrSource("t", years=1, today=date(2026, 10, 1)).fiscal_years() == [2028, 2027]


def test_hud_fetch_skips_unpublished_year_and_retries_rate_limits() -> None:
    requests: list[httpx.Request] = []
    rate_limited = {"once": True}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer secret"
        state = request.url.path.rsplit("/", 1)[-1]
        year = request.url.params["year"]
        if year == "2027":
            return httpx.Response(200, json={"error": "No data for year 2027"})
        if state == "TN" and rate_limited.pop("once", False):
            return httpx.Response(429, headers={"Retry-After": "3"})
        if state == "TN":
            return httpx.Response(200, content=_fixture(f"hud_statedata_tn_{year}.json"))
        return httpx.Response(200, json={"data": {"year": year, "metroareas": []}})

    sleeps: list[float] = []
    source = HudFmrSource("secret", years=2, today=date(2026, 9, 25), sleep=sleeps.append)
    files = source.fetch(httpx.Client(transport=httpx.MockTransport(handler)))

    assert sleeps == [3.0]
    assert {f.name for f in files} == {f"{y}_{s}.json" for y in (2026, 2025) for s in STATES}
    # One probe for 2027, every state for 2026 and 2025, one retried call.
    assert len(requests) == 1 + 2 * len(STATES) + 1


def test_hud_fetch_rejects_bad_token_and_missing_token() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(PermissionError, match="token"):
        HudFmrSource("bad", today=date(2026, 9, 25)).fetch(client)
    with pytest.raises(ValueError, match="MOGUL_HUD_API_TOKEN"):
        HudFmrSource("").fetch(client)


def test_missing_config_names_what_to_set() -> None:
    assert missing_config("hud", Settings(hud_api_token="")) is not None
    assert missing_config("hud", Settings(hud_api_token="x")) is None
    assert missing_config("census", Settings()) is None  # the key is optional


# ---------------------------------------------------------------- Census ACS


def _acs_files() -> list[RawFile]:
    return [
        RawFile("2024_us.json", _fixture("acs_us_2024.json")),
        RawFile("2024_metro.json", _fixture("acs_metro_2024.json")),
        RawFile("2023_metro.json", _fixture("acs_metro_2023.json")),
        RawFile("2024_zip.json", _fixture("acs_zip_2024.json")),
    ]


def test_acs_parses_us_metros_and_zips() -> None:
    series = {s.source_key: s for s in AcsSource().parse(_acs_files())}
    assert {s.metric for s in series.values()} == {"median_gross_rent"}

    us = series["acs:us"]
    assert us.geography == US and us.observations == [(date(2024, 12, 31), 1487.0)]

    memphis = series["acs:cbsa:32820"]
    assert memphis.geography.name == "Memphis, TN"
    assert memphis.geography.external_ids == {"cbsa": "32820"}
    assert memphis.observations == [(date(2023, 12, 31), 1098.0), (date(2024, 12, 31), 1145.0)]
    metros = {s.geography.name for s in series.values() if s.geography.kind == "msa"}
    # Micro areas and missing estimates (negative sentinels) are left out.
    assert metros == {
        "Memphis, TN",
        "Louisville, KY",
        "Nashville, TN",
        "Cleveland, TN",
        "Cleveland, OH",
    }

    zips = {s.geography.name: s for s in series.values() if s.geography.kind == "zip"}
    assert set(zips) == {"38104", "38117", "38103"}
    assert zips["38104"].observations == [(date(2024, 12, 31), 1260.0)]


def test_acs_fetch_finds_the_newest_published_vintages() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        year = int(request.url.path.split("/")[2])
        if year == 2025:
            return httpx.Response(404, text="unknown dataset")
        clause = request.url.params["for"]
        assert request.url.params["key"] == "k"
        if clause.startswith("zip"):
            return httpx.Response(200, content=_fixture("acs_zip_2024.json"))
        if clause.startswith("metro"):
            return httpx.Response(200, content=_fixture("acs_metro_2024.json"))
        return httpx.Response(200, content=_fixture("acs_us_2024.json"))

    files = AcsSource("k", years=2, today=date(2026, 9, 25)).fetch(
        httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert [f.name for f in files] == [
        "2024_us.json",
        "2024_metro.json",
        "2024_zip.json",
        "2023_us.json",
        "2023_metro.json",
        "2023_zip.json",
    ]
    assert len(requests) == 1 + 6


def test_acs_fetch_leaves_out_zips_before_2020() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert not request.url.params["for"].startswith("zip")
        return httpx.Response(200, content=_fixture("acs_us_2024.json"))

    files = AcsSource(years=1, today=date(2020, 3, 1)).fetch(
        httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert [f.name for f in files] == ["2019_us.json", "2019_metro.json"]


def test_acs_fetch_reports_a_bad_key() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>Invalid Key"))
    )
    with pytest.raises(ValueError, match="unexpected Census response"):
        AcsSource("bad", today=date(2026, 9, 25)).fetch(client)
