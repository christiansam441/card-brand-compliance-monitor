import pytest
from fastapi.testclient import TestClient

from app import analysis, rules
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def df():
    return analysis.load_data()


def test_shape_and_determinism(df):
    assert df["merchant_id"].nunique() == 40
    assert df["month"].nunique() == 7           # 1 baseline + 6 evaluated
    assert len(df) == 280
    from scripts.generate_data import generate
    assert generate().equals(generate())         # seeded


def test_expected_columns(df):
    cols = {"merchant_id", "name", "vertical", "month", "visa_cnp_sales_count", "visa_tc40_fraud",
            "visa_tc15_disputes", "mc_sales_count", "mc_chargebacks", "mc_fraud_count",
            "mc_fraud_dollars", "mc_sales_dollars", "mc_chargeback_dollars"}
    assert cols <= set(df.columns)


def _by_id(df):
    return {m["id"]: m for m in analysis.portfolio(df)["merchants"]}


def test_six_planted_scenarios(df):
    m = _by_id(df)
    assert m["M001"]["worst"] == rules.SAFE                                    # 1. clean
    assert m["M002"]["visa"]["status"] == rules.BREACH                         # 2. Visa only
    assert m["M002"]["mc"]["status"] == rules.SAFE
    assert m["M003"]["mc"]["tier"] == rules.ECM                                # 3. MC only
    assert m["M003"]["visa"]["events"] < 1500 / 10 and m["M003"]["visa"]["status"] == rules.SAFE
    assert m["M004"]["mc"]["tier"] == rules.ECM                                # 4. growth-inflated
    assert m["M004"]["mc"]["same_month_ratio"] < 0.015 <= m["M004"]["mc"]["ratio"]
    assert m["M005"]["mc"]["tier"] == rules.ECM and m["M005"]["mc"]["near_hecm"]  # 5. toward HECM
    assert m["M005"]["mc"]["chargebacks"] >= 300 and m["M005"]["mc"]["ratio"] < 0.03
    assert m["M006"]["visa"]["below_floor"] and m["M006"]["visa"]["ratio"] >= 0.015  # 6. small, sub-floor


def test_most_merchants_are_clean(df):
    worst = [m["worst"] for m in analysis.portfolio(df)["merchants"]]
    assert worst.count(rules.SAFE) >= 30


def test_book_is_just_under_half_percent_without_m6_and_just_over_with_it(df):
    latest = df[df["month"] == "2026-09"]
    ev = latest["visa_tc40_fraud"] + latest["visa_tc15_disputes"]
    sales = latest["visa_cnp_sales_count"]
    no6 = latest["merchant_id"] != "M006"
    without = ev[no6].sum() / sales[no6].sum()
    with6 = ev.sum() / sales.sum()
    assert 0.0049 <= without < 0.005 <= with6 < 0.0052
    book = analysis.portfolio(df)["book"]
    assert book["label"] == "ABOVE STANDARD" and book["headroom_events"] < 0


def test_portfolio_endpoint():
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert len(body["merchants"]) == 40
    assert body["book"]["label"] == "ABOVE STANDARD"
    assert body["lines"] == {"above_standard": 0.005, "excessive": 0.007}


def test_merchant_endpoint_and_404():
    r = client.get("/api/merchants/M003")
    assert r.status_code == 200
    d = r.json()
    assert len(d["months"]) == 6
    assert d["what_if"]["mc"]["ecm"]["cut"] > 0
    assert client.get("/api/merchants/m003").status_code == 200   # case-insensitive
    assert client.get("/api/merchants/NOPE").status_code == 404


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200 and "Card Brand Compliance Monitor" in r.text
