"""Data collectors: Google Search Console, GA4 and Merchant Center (Merchant API v1).

All three use one Google service account with read-only access. Each collector returns a plain dict
and never raises: on failure it returns {"ok": False, "error": "..."} so one broken source
does not stop the client report.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/content",
    "https://www.googleapis.com/auth/spreadsheets",
]


def session(key_file: str) -> AuthorizedSession:
    creds = service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)
    return AuthorizedSession(creds)


def windows(end: dt.date, days: int):
    """Current window ending on `end` and the same-length window right before it."""
    cur_from = end - dt.timedelta(days=days - 1)
    prev_to = cur_from - dt.timedelta(days=1)
    prev_from = prev_to - dt.timedelta(days=days - 1)
    return (cur_from, end), (prev_from, prev_to)


def _err(exc: Exception) -> dict:
    return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def _check(resp):
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


# ---------------------------------------------------------------- Search Console

def gsc(s: AuthorizedSession, site: str, today: dt.date, days: int = 7) -> dict:
    # Search Console data lags 2-3 days
    (cf, ct), (pf, pt) = windows(today - dt.timedelta(days=3), days)
    url = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{_q(site)}/searchAnalytics/query"

    def q(a, b, dims=None, limit=5000):
        body = {"startDate": a.isoformat(), "endDate": b.isoformat(), "rowLimit": limit, "dataState": "final"}
        if dims:
            body["dimensions"] = dims
        return _check(s.post(url, json=body)).get("rows", [])

    def total(a, b):
        r = q(a, b, limit=1)
        if not r:
            return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": None}
        r = r[0]
        return {"clicks": int(r["clicks"]), "impressions": int(r["impressions"]),
                "ctr": round(r["ctr"], 4), "position": round(r["position"], 1) if r["impressions"] else None}

    try:
        out = {"ok": True, "site": site, "cur_range": [cf.isoformat(), ct.isoformat()],
               "prev_range": [pf.isoformat(), pt.isoformat()],
               "cur": total(cf, ct), "prev": total(pf, pt)}
        for dim in ("query", "page"):
            cur = {r["keys"][0]: r for r in q(cf, ct, [dim])}
            prev = {r["keys"][0]: r for r in q(pf, pt, [dim])}
            rows = []
            for key in set(cur) | set(prev):
                c, p = cur.get(key, {}), prev.get(key, {})
                rows.append({dim: key,
                             "clicks": int(c.get("clicks", 0)), "clicks_prev": int(p.get("clicks", 0)),
                             "impr": int(c.get("impressions", 0)), "impr_prev": int(p.get("impressions", 0)),
                             "pos": round(c["position"], 1) if c else None,
                             "pos_prev": round(p["position"], 1) if p else None})
            out[dim + "_rows"] = rows
        return out
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def _q(site: str) -> str:
    from urllib.parse import quote
    return quote(site, safe="")


# ---------------------------------------------------------------- GA4

GA4_METRICS = ["sessions", "activeUsers", "engagedSessions", "keyEvents", "addToCarts", "checkouts"]


def ga4(s: AuthorizedSession, prop: str, today: dt.date, days: int = 7) -> dict:
    """Traffic and engagement only. Revenue and order values are deliberately not requested."""
    (cf, ct), (pf, pt) = windows(today - dt.timedelta(days=1), days)
    url = f"https://analyticsdata.googleapis.com/v1beta/{prop}:runReport"
    ranges = [{"startDate": cf.isoformat(), "endDate": ct.isoformat(), "name": "cur"},
              {"startDate": pf.isoformat(), "endDate": pt.isoformat(), "name": "prev"}]

    def run(body):
        return _check(s.post(url, json=body)).get("rows", [])

    try:
        totals = {"cur": {m: 0 for m in GA4_METRICS}, "prev": {m: 0 for m in GA4_METRICS}}
        for r in run({"dateRanges": ranges, "metrics": [{"name": m} for m in GA4_METRICS]}):
            key = r["dimensionValues"][0]["value"]
            totals[key] = {m: _num(v["value"]) for m, v in zip(GA4_METRICS, r["metricValues"])}

        def by(dim, limit=15):
            res = defaultdict(lambda: {"cur": 0, "prev": 0})
            for r in run({"dateRanges": ranges, "dimensions": [{"name": dim}], "metrics": [{"name": "sessions"}],
                          "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}], "limit": 200}):
                name, rng = r["dimensionValues"][0]["value"], r["dimensionValues"][1]["value"]
                res[name][rng] = _num(r["metricValues"][0]["value"])
            rows = [{"name": k, "sessions": v["cur"], "sessions_prev": v["prev"]} for k, v in res.items()]
            return sorted(rows, key=lambda x: -(x["sessions"] + x["sessions_prev"]))[:limit]

        return {"ok": True, "property": prop, "cur_range": [cf.isoformat(), ct.isoformat()],
                "prev_range": [pf.isoformat(), pt.isoformat()], "cur": totals["cur"], "prev": totals["prev"],
                "channels": by("sessionDefaultChannelGroup", 8), "landing_pages": by("landingPage", 30)}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def _num(v):
    f = float(v)
    return int(f) if f.is_integer() else round(f, 2)


# ---------------------------------------------------------------- Merchant Center

MAPI = "https://merchantapi.googleapis.com"


def merchant(s: AuthorizedSession, account: str, today: dt.date, days: int = 7) -> dict:
    """Product statuses and item issues (product_view), account-level issues, and Shopping clicks per product."""
    try:
        products = _search(s, account, "SELECT id, offer_id, title, brand, aggregated_reporting_context_status, "
                                        "item_issues FROM product_view")
    except Exception as exc:  # noqa: BLE001
        return _err(exc)

    status = Counter()
    issues = defaultdict(lambda: {"count": 0, "severity": "", "attribute": "", "examples": []})
    for row in products:
        p = row.get("productView", {})
        st = p.get("aggregatedReportingContextStatus", "UNKNOWN")
        status[st] += 1
        for it in p.get("itemIssues", []):
            t = it.get("type", {})
            sev = it.get("severity", {}).get("aggregatedSeverity", "")
            key = t.get("code", "unknown")
            rec = issues[key]
            rec["count"] += 1
            rec["severity"] = rec["severity"] or sev
            rec["attribute"] = rec["attribute"] or t.get("canonicalAttribute", "")
            if len(rec["examples"]) < 3:
                rec["examples"].append(p.get("title", p.get("offerId", ""))[:90])

    out = {"ok": True, "account": account, "products_total": sum(status.values()), "status": dict(status),
           "issues": sorted(({"code": k, **v} for k, v in issues.items()), key=lambda x: -x["count"])[:15]}

    # account-level issues (suspension, misrepresentation, missing policies)
    try:
        data = _check(s.get(f"{MAPI}/accounts/v1/accounts/{account}/issues", params={"pageSize": 50}))
        out["account_issues"] = [{"title": i.get("title", ""), "severity": i.get("severity", ""),
                                  "detail": (i.get("detail") or "")[:300]}
                                 for i in data.get("accountIssues", [])]
    except Exception as exc:  # noqa: BLE001
        out["account_issues_error"] = str(exc)[:200]

    # free listings / Shopping performance per product, current vs previous window
    (cf, ct), (pf, pt) = windows(today - dt.timedelta(days=1), days)
    try:
        perf = defaultdict(lambda: {"clicks": 0, "clicks_prev": 0, "impr": 0, "impr_prev": 0, "title": ""})
        rows = _search(s, account, "SELECT offer_id, title, date, clicks, impressions FROM product_performance_view "
                                   f"WHERE date BETWEEN '{pf.isoformat()}' AND '{ct.isoformat()}'")
        for row in rows:
            p = row.get("productPerformanceView", {})
            d = p.get("date", {})
            day = dt.date(int(d.get("year", 1970)), int(d.get("month", 1)), int(d.get("day", 1)))
            rec = perf[p.get("offerId", "")]
            rec["title"] = p.get("title", rec["title"])[:90]
            suffix = "" if day >= cf else "_prev"
            rec["clicks" + suffix] += int(p.get("clicks", 0))
            rec["impr" + suffix] += int(p.get("impressions", 0))
        out["performance"] = {
            "cur_range": [cf.isoformat(), ct.isoformat()], "prev_range": [pf.isoformat(), pt.isoformat()],
            "clicks": sum(v["clicks"] for v in perf.values()), "clicks_prev": sum(v["clicks_prev"] for v in perf.values()),
            "impr": sum(v["impr"] for v in perf.values()), "impr_prev": sum(v["impr_prev"] for v in perf.values()),
            "top": sorted(perf.values(), key=lambda v: -(v["clicks"] * 100 + v["impr"]))[:10]}
    except Exception as exc:  # noqa: BLE001
        out["performance_error"] = str(exc)[:200]
    return out


def _search(s: AuthorizedSession, account: str, query: str, max_pages: int = 20) -> list:
    url = f"{MAPI}/reports/v1/accounts/{account}/reports:search"
    rows, token = [], None
    for _ in range(max_pages):
        body = {"query": query, "pageSize": 1000}
        if token:
            body["pageToken"] = token
        data = _check(s.post(url, json=body))
        rows += data.get("results", [])
        token = data.get("nextPageToken")
        if not token:
            break
    return rows
