"""Turns raw source data into a compact list of signals.

Numbers and thresholds live here, in plain code, so every alert can be traced back to a rule.
Claude only gets this compact summary (a few KB), never raw API dumps: that keeps the prompt cheap
and stops the model from inventing figures it was not given.
"""
from __future__ import annotations

# Thresholds (week over week). Tune per client in clients.json -> "thresholds".
DEFAULTS = {
    "drop_high": -0.25,     # -25% or worse -> high
    "drop_medium": -0.10,   # -10% .. -25% -> medium
    "min_base": 30,         # ignore % changes when the previous value is tiny
    "disapproved_high": 0.20,
    "disapproved_medium": 0.05,
}


def pct(cur, prev):
    if not prev:
        return None
    return round((cur - prev) / prev, 3)


def build(client: dict, data: dict) -> dict:
    th = {**DEFAULTS, **client.get("thresholds", {})}
    sig = {"client": client["name"], "window_days": data.get("window_days", 7), "sources": {}, "rule_alerts": []}
    alerts = sig["rule_alerts"]

    def check_drop(source, metric, cur, prev):
        change = pct(cur, prev)
        if change is None or prev < th["min_base"]:
            return
        if change <= th["drop_high"]:
            alerts.append({"severity": "high", "source": source, "metric": metric, "cur": cur, "prev": prev, "change": change})
        elif change <= th["drop_medium"]:
            alerts.append({"severity": "medium", "source": source, "metric": metric, "cur": cur, "prev": prev, "change": change})

    # ---------- Search Console
    g = data.get("gsc") or {}
    if g.get("ok"):
        c, p = g["cur"], g["prev"]
        for m in ("clicks", "impressions"):
            check_drop("search_console", m, c[m], p[m])
        q = g["query_rows"]
        rising = sorted((r for r in q if r["impr"] - r["impr_prev"] > 0), key=lambda r: r["impr_prev"] - r["impr"])[:10]
        new = sorted((r for r in q if r["impr_prev"] == 0 and r["impr"] >= 5), key=lambda r: -r["impr"])[:10]
        losing = sorted((r for r in q if r["clicks"] < r["clicks_prev"]), key=lambda r: r["clicks"] - r["clicks_prev"])[:8]
        pages_losing = sorted((r for r in g["page_rows"] if r["clicks"] < r["clicks_prev"]),
                              key=lambda r: r["clicks"] - r["clicks_prev"])[:8]
        # queries on page 2 with real demand: cheapest SEO wins
        striking = sorted((r for r in q if r["pos"] and 8 <= r["pos"] <= 20 and r["impr"] >= 20),
                          key=lambda r: -r["impr"])[:8]
        sig["sources"]["search_console"] = {
            "range": g["cur_range"], "prev_range": g["prev_range"],
            "totals": {m: {"cur": c[m], "prev": p[m], "change": pct(c[m], p[m])} for m in ("clicks", "impressions")},
            "avg_position": {"cur": c["position"], "prev": p["position"]},
            "rising_queries": rising, "new_queries": new, "losing_queries": losing,
            "losing_pages": pages_losing, "striking_distance": striking}
    elif g:
        sig["sources"]["search_console"] = {"error": g.get("error")}

    # ---------- GA4
    a = data.get("ga4") or {}
    if a.get("ok"):
        c, p = a["cur"], a["prev"]
        for m in ("sessions", "activeUsers", "keyEvents"):
            check_drop("ga4", m, c.get(m, 0), p.get(m, 0))
        sig["sources"]["ga4"] = {
            "range": a["cur_range"], "prev_range": a["prev_range"],
            "totals": {m: {"cur": c.get(m, 0), "prev": p.get(m, 0), "change": pct(c.get(m, 0), p.get(m, 0))} for m in c},
            "channels": [dict(r, change=pct(r["sessions"], r["sessions_prev"])) for r in a["channels"]],
            "landing_pages_losing": sorted((r for r in a["landing_pages"] if r["sessions"] < r["sessions_prev"]),
                                           key=lambda r: r["sessions"] - r["sessions_prev"])[:6]}
        for ch in a["channels"]:
            check_drop("ga4", f"sessions:{ch['name']}", ch["sessions"], ch["sessions_prev"])
    elif a:
        sig["sources"]["ga4"] = {"error": a.get("error")}

    # ---------- Merchant Center
    m = data.get("merchant") or {}
    if m.get("ok"):
        total = m["products_total"] or 1
        bad = m["status"].get("NOT_ELIGIBLE_OR_DISAPPROVED", 0)
        share = round(bad / total, 3)
        sig["sources"]["merchant_center"] = {
            "products_total": m["products_total"], "status": m["status"], "disapproved_share": share,
            "top_issues": m["issues"][:8], "account_issues": m.get("account_issues", []),
            "performance": m.get("performance"), "errors": {k: v for k, v in m.items() if k.endswith("_error")}}
        if m.get("account_issues"):
            alerts.append({"severity": "high", "source": "merchant_center", "metric": "account_issues",
                           "cur": len(m["account_issues"]), "prev": None, "change": None})
        if share >= th["disapproved_high"]:
            alerts.append({"severity": "high", "source": "merchant_center", "metric": "disapproved_share",
                           "cur": bad, "prev": None, "change": share})
        elif share >= th["disapproved_medium"]:
            alerts.append({"severity": "medium", "source": "merchant_center", "metric": "disapproved_share",
                           "cur": bad, "prev": None, "change": share})
        perf = m.get("performance") or {}
        if perf:
            check_drop("merchant_center", "shopping_clicks", perf["clicks"], perf["clicks_prev"])
    elif m:
        sig["sources"]["merchant_center"] = {"error": m.get("error")}

    order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda x: order[x["severity"]])
    return sig
