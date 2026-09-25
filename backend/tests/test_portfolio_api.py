from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mogul.api.app import create_app
from mogul.db.models import Base
from mogul.db.session import get_session

TODAY = date.today()
BOUGHT = TODAY - timedelta(days=400)


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine, expire_on_commit=False)

    def override() -> Iterator[Session]:
        with make() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c


def _property(client: TestClient, **over: object) -> dict:  # type: ignore[type-arg]
    body = {
        "name": "Birch Ave",
        "units": 2,
        "purchase_date": BOUGHT.isoformat(),
        "purchase_price": 250000,
        "closing_costs": "7500.004",
        "loan": {
            "original_amount": 187500,
            "interest_rate": 0.065,
            "amortization_years": 30,
            "start_date": BOUGHT.isoformat(),
        },
        **over,
    }
    res = client.post("/portfolio/properties", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_empty_portfolio(client: TestClient) -> None:
    body = client.get("/portfolio").json()
    assert body["holdings"] == [] and body["totals"]["properties"] == 0
    assert body["totals"]["irr"] is None


def test_create_and_read_property(client: TestClient) -> None:
    detail = _property(client)
    prop = detail["property"]
    assert prop["closing_costs"] == 7500.0  # rounded to cents, returned as a number
    assert prop["loan"]["monthly_payment"] == pytest.approx(1185.13, abs=0.01)
    perf = detail["performance"]
    assert perf["cost_basis"] == 257500 and perf["equity_invested"] == 70000
    assert perf["debt_service_imputed"] is True
    assert len(detail["monthly"]) >= 13
    assert detail["pro_forma"] is None


def test_validation(client: TestClient) -> None:
    base = {"name": "x", "purchase_date": "2024-01-01", "purchase_price": 1}
    bad_sale = client.post("/portfolio/properties", json={**base, "sale_date": "2024-06-01"})
    assert bad_sale.status_code == 422
    bad_market = client.post("/portfolio/properties", json={**base, "market_id": 99})
    assert bad_market.status_code == 422 and "market_id" in bad_market.json()["detail"]
    assert client.get("/portfolio/properties/5").status_code == 404


def test_leases_ledger_valuations(client: TestClient) -> None:
    pid = _property(client)["property"]["id"]

    lease = client.post(
        f"/portfolio/properties/{pid}/leases",
        json={"unit": "A", "start_date": BOUGHT.isoformat(), "monthly_rent": 1400},
    ).json()
    assert lease["active"] is True
    client.post(
        f"/portfolio/properties/{pid}/leases",
        json={"unit": "B", "start_date": BOUGHT.isoformat(), "monthly_rent": 1350},
    )

    rent_day = (TODAY - timedelta(days=20)).isoformat()
    tx = client.post(
        f"/portfolio/properties/{pid}/transactions",
        json={"date": rent_day, "amount": 2750, "category": "rent", "description": "Jan rent"},
    ).json()
    assert tx["group"] == "income" and tx["imported"] is False

    csv = f"Date,Description,Amount\n{rent_day},MORTGAGE PMT,-1185.13\n{rent_day},Odd charge,-20\n"
    first = client.post(f"/portfolio/properties/{pid}/transactions/import", json={"csv": csv})
    assert first.json() == {
        "imported": 2,
        "skipped_duplicates": 0,
        "guessed": 1,
        "uncategorized": 1,
    }
    again = client.post(f"/portfolio/properties/{pid}/transactions/import", json={"csv": csv})
    assert again.json()["imported"] == 0 and again.json()["skipped_duplicates"] == 2
    bad = client.post(f"/portfolio/properties/{pid}/transactions/import", json={"csv": "x,y\n"})
    assert bad.status_code == 422

    txs = client.get(f"/portfolio/properties/{pid}/transactions").json()
    odd = next(t for t in txs if t["description"] == "Odd charge")
    patched = client.patch(
        f"/portfolio/transactions/{odd['id']}", json={"category": "other_expense"}
    )
    assert patched.json()["group"] == "operating_expense"
    assert (
        client.patch(f"/portfolio/transactions/{odd['id']}", json={"category": "nope"}).status_code
        == 422
    )

    client.post(
        f"/portfolio/properties/{pid}/valuations",
        json={"date": TODAY.isoformat(), "value": 290000, "note": "BPO"},
    )
    detail = client.get(f"/portfolio/properties/{pid}").json()
    perf = detail["performance"]
    assert perf["value"] == 290000 and perf["value_source"] == "valuation"
    assert perf["occupied_units"] == 2 and perf["scheduled_rent"] == 2750
    assert perf["debt_service_imputed"] is False
    assert perf["t12"]["income"] == 2750 and perf["t12"]["operating_expenses"] == 20

    assert client.delete(f"/portfolio/leases/{lease['id']}").status_code == 204
    assert client.delete(f"/portfolio/transactions/{tx['id']}").status_code == 204
    assert (
        client.delete(f"/portfolio/valuations/{detail['valuations'][0]['id']}").status_code == 204
    )
    after = client.get(f"/portfolio/properties/{pid}").json()
    assert after["performance"]["occupied_units"] == 1 and after["valuations"] == []

    assert client.delete(f"/portfolio/properties/{pid}").status_code == 204
    assert client.get("/portfolio").json()["holdings"] == []


def test_update_property_removes_loan(client: TestClient) -> None:
    detail = _property(client)
    prop = detail["property"]
    body = {k: v for k, v in prop.items() if k not in ("id", "market_name")}
    body["loan"] = None
    updated = client.put(f"/portfolio/properties/{prop['id']}", json=body).json()
    assert updated["property"]["loan"] is None
    assert updated["performance"]["loan_balance"] == 0


def test_from_deal_links_projection(client: TestClient) -> None:
    inputs = client.get("/analysis/template").json()
    deal = client.post("/deals", json={"name": "Maple", "inputs": inputs}).json()
    res = client.post(
        f"/portfolio/properties/from-deal/{deal['id']}",
        params={"purchase_date": BOUGHT.isoformat()},
    )
    assert res.status_code == 201, res.text
    detail = res.json()
    assert detail["property"]["deal_id"] == deal["id"]
    assert detail["property"]["purchase_price"] == inputs["purchase_price"]
    assert detail["property"]["loan"]["original_amount"] == inputs["purchase_price"] * 0.75
    comparison = detail["pro_forma"]
    assert comparison["projection_year"] == 2
    assert [r["label"] for r in comparison["rows"]][0] == "Income"
    assert client.get(f"/deals/{deal['id']}").json()["status"] == "owned"


def test_portfolio_totals(client: TestClient) -> None:
    _property(client, name="A")
    _property(client, name="B", loan=None, property_type="condo", units=1)
    body = client.get("/portfolio").json()
    t = body["totals"]
    assert t["properties"] == 2 and t["units"] == 3
    assert t["value"] == 500000
    assert t["equity"] == pytest.approx(t["value"] - t["loan_balance"])
    assert t["irr"] is not None
    assert {s["label"] for s in body["by_type"]} == {"single_family", "condo"}
    assert body["months"][-1]["month"] == TODAY.isoformat()
    assert body["months"][-1]["value"] == pytest.approx(500000)
