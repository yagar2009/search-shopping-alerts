"""Rule tests: run with `python -m pytest -q` (no network, no Claude)."""
from opsbrief import signals
from opsbrief.run import mask


def gsc(cur_clicks, prev_clicks, rows=()):
    return {"ok": True, "cur_range": ["2026-10-13", "2026-11-09"], "prev_range": ["2026-09-15", "2026-10-12"],
            "cur": {"clicks": cur_clicks, "impressions": 1000, "ctr": 0.01, "position": 20.0},
            "prev": {"clicks": prev_clicks, "impressions": 1000, "ctr": 0.01, "position": 20.0},
            "query_rows": list(rows), "page_rows": []}


def test_click_drop_is_high_when_over_25_percent():
    sig = signals.build({"name": "X"}, {"gsc": gsc(60, 100)})
    assert sig["rule_alerts"][0]["severity"] == "high"
    assert sig["rule_alerts"][0]["metric"] == "clicks"


def test_small_base_is_ignored():
    sig = signals.build({"name": "X"}, {"gsc": gsc(2, 10)})
    assert sig["rule_alerts"] == []


def test_rising_and_page_two_queries():
    rows = [{"query": "a", "clicks": 0, "clicks_prev": 0, "impr": 50, "impr_prev": 5, "pos": 12.0, "pos_prev": 15.0},
            {"query": "b", "clicks": 0, "clicks_prev": 0, "impr": 3, "impr_prev": 4, "pos": 40.0, "pos_prev": 40.0}]
    s = signals.build({"name": "X"}, {"gsc": gsc(50, 50, rows)})["sources"]["search_console"]
    assert [r["query"] for r in s["rising_queries"]] == ["a"]
    assert [r["query"] for r in s["striking_distance"]] == ["a"]


def test_merchant_suspension_raises_high_alerts():
    m = {"ok": True, "products_total": 100, "status": {"NOT_ELIGIBLE_OR_DISAPPROVED": 100}, "issues": [],
         "account_issues": [{"title": "Misrepresentation", "severity": "CRITICAL", "detail": ""}]}
    alerts = signals.build({"name": "X"}, {"merchant": m})["rule_alerts"]
    assert {a["metric"] for a in alerts} == {"account_issues", "disapproved_share"}
    assert all(a["severity"] == "high" for a in alerts)


def test_unconfigured_source_is_not_reported():
    sig = signals.build({"name": "X"}, {"gsc": gsc(50, 50)})
    assert "merchant_center" not in sig["sources"]


def test_mask_hides_domain_and_brand():
    client = {"name": "Store A", "domain": "shop.example", "real_name": "ShopBrand", "mask": ["shopbrand"]}
    out = mask({"t": "ShopBrand page https://www.shop.example/doors", "u": ["shopbrand"]}, client)
    assert out == {"t": "Store A page /doors", "u": ["Store A"]}
