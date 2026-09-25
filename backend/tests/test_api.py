from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mogul.api.app import create_app
from mogul.db.models import Base
from mogul.db.session import get_session


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    make_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override() -> Iterator:  # type: ignore[type-arg]
        with make_session() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_template_round_trips_through_analysis(client: TestClient) -> None:
    deal = client.get("/analysis/template").json()
    res = client.post("/analysis", json=deal)
    assert res.status_code == 200
    body = res.json()
    assert len(body["years"]) == deal["hold_years"]
    assert body["metrics"]["levered_irr"] is not None


def test_analysis_rejects_bad_input(client: TestClient) -> None:
    res = client.post("/analysis", json={"purchase_price": -1, "monthly_rent": 1000})
    assert res.status_code == 422


def test_sensitivity_endpoint(client: TestClient) -> None:
    deal = client.get("/analysis/template").json()
    res = client.post(
        "/analysis/sensitivity",
        json={
            "deal": deal,
            "x_field": "monthly_rent",
            "x_values": [2000, 2500],
            "y_field": "purchase_price",
            "y_values": [300000, 325000, 350000],
        },
    )
    assert res.status_code == 200
    assert len(res.json()["values"]) == 3


def test_sensitivity_reports_bad_field(client: TestClient) -> None:
    deal = client.get("/analysis/template").json()
    res = client.post(
        "/analysis/sensitivity",
        json={
            "deal": deal,
            "x_field": "bogus",
            "x_values": [1],
            "y_field": "appreciation",
            "y_values": [0.03],
        },
    )
    assert res.status_code == 422
    assert "unknown input field" in res.json()["detail"]


def test_sensitivity_reports_out_of_range_flex(client: TestClient) -> None:
    deal = client.get("/analysis/template").json()
    res = client.post(
        "/analysis/sensitivity",
        json={
            "deal": deal,
            "x_field": "vacancy_rate",
            "x_values": [2],
            "y_field": "appreciation",
            "y_values": [0.03],
        },
    )
    assert res.status_code == 422


def test_deal_crud(client: TestClient) -> None:
    inputs = client.get("/analysis/template").json()
    created = client.post(
        "/deals", json={"name": "Maple St duplex", "address": "12 Maple St", "inputs": inputs}
    )
    assert created.status_code == 201
    deal = created.json()
    assert deal["status"] == "watching"
    assert deal["metrics"]["cap_rate"] > 0

    listed = client.get("/deals").json()
    assert [d["id"] for d in listed] == [deal["id"]]

    inputs["monthly_rent"] = 3_000
    updated = client.put(
        f"/deals/{deal['id']}", json={"name": "Maple St", "status": "offer", "inputs": inputs}
    ).json()
    assert updated["status"] == "offer"
    assert updated["metrics"]["noi_year1"] > deal["metrics"]["noi_year1"]

    assert client.delete(f"/deals/{deal['id']}").status_code == 204
    assert client.get(f"/deals/{deal['id']}").status_code == 404
    assert client.get("/deals").json() == []
