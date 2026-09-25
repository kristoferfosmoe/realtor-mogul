"""A small, fixed market data set for API tests (shaped like Zillow and FRED data)."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from mogul.ingest.base import US, GeoRef, ParsedSeries
from mogul.ingest.pipeline import store

MEMPHIS = GeoRef("msa", "Memphis, TN", "TN", 42, {"zillow": 394870})
TAMPA = GeoRef("msa", "Tampa, FL", "FL", 18, {"zillow": 395148})


def month_ends(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        out.append(d)
        nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        d = date(nxt.year + (nxt.month == 12), nxt.month % 12 + 1, 1) - timedelta(days=1)
    return out


def _growing(start_value: float, rate: float, days: list[date]) -> list[tuple[date, float]]:
    return [(d, round(start_value * (1 + rate) ** (i / 12), 2)) for i, d in enumerate(days)]


def seed_markets(db: Session, end: date = date(2026, 8, 31)) -> None:
    """US, Memphis and Tampa rent and home values monthly since 2019, plus FRED rates."""
    days = month_ends(date(2019, 1, 31), end)
    series = []
    for key, geo, rent, value in [
        ("US", US, 1500, 300_000),
        ("394870", MEMPHIS, 1100, 150_000),
        ("395148", TAMPA, 1700, 280_000),
    ]:
        series.append(
            ParsedSeries(f"zori:{key}", "rent_index", "monthly", geo, _growing(rent, 0.035, days))
        )
        series.append(
            ParsedSeries(f"zhvi:{key}", "home_value", "monthly", geo, _growing(value, 0.04, days))
        )
    store(db, "zillow", series)
    store(
        db,
        "fred",
        [
            ParsedSeries("MORTGAGE30US", "mortgage_rate_30y", "weekly", US, [(end, 0.0621)]),
            ParsedSeries("CUSR0000SEHA", "cpi_rent", "monthly", US, _growing(400, 0.04, days)),
            ParsedSeries(
                "RRVRUSQ156N", "rental_vacancy", "quarterly", US, [(date(2026, 4, 1), 0.07)]
            ),
        ],
    )
    db.commit()
