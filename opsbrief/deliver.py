"""Outputs: Telegram alert, Google Sheet log, and an HTML/Markdown brief on disk."""
from __future__ import annotations

import datetime as dt
import html
import json
import os

import requests

SEV_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}
STATUS_ICON = {"green": "🟢", "amber": "🟠", "red": "🔴"}


def pct(v):
    return "n/a" if v is None else f"{v * 100:+.0f}%"


# ---------------------------------------------------------------- Telegram

def telegram_text(client: str, brief: dict, report_url: str = "") -> str:
    e = html.escape
    lines = [f"{STATUS_ICON.get(brief['status'], '')} <b>{e(client)}</b>: search & shopping check",
             e(brief["headline"]), ""]
    for a in brief["alerts"][:3]:
        lines.append(f"{SEV_ICON.get(a['severity'], '')} <b>{e(a['title'])}</b>")
        lines.append(f"{e(a['evidence'])}")
        lines.append(f"→ {e(a['next_action'])} <i>({e(a['owner'].replace('_', ' '))})</i>")
        lines.append("")
    if brief["opportunities"]:
        o = brief["opportunities"][0]
        lines.append(f"💡 {e(o['title'])}: {e(o['next_action'])}")
    if report_url:
        lines.append(f'\n<a href="{e(report_url)}">Full brief</a>')
    return "\n".join(lines).strip()


def send_telegram(text: str) -> dict:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return {"ok": False, "skipped": "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"}
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=30,
                      json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
    data = r.json()
    return {"ok": data.get("ok", False), "message_id": (data.get("result") or {}).get("message_id"),
            "error": data.get("description")}


# ---------------------------------------------------------------- Google Sheets

def sheet_rows(run_date: str, client: str, signals: dict, brief: dict):
    alerts = [[run_date, client, a["severity"], a["source"], a["title"], a["evidence"], a["likely_cause"],
               a["next_action"], a["owner"]] for a in brief["alerts"]]
    kpis = []
    s = signals["sources"]
    for src, key in (("search_console", "totals"), ("ga4", "totals")):
        for metric, v in (s.get(src, {}).get(key) or {}).items():
            kpis.append([run_date, client, src, metric, v["cur"], v["prev"], v["change"]])
    mc = s.get("merchant_center", {})
    if "products_total" in mc:
        kpis.append([run_date, client, "merchant_center", "products_total", mc["products_total"], "", ""])
        kpis.append([run_date, client, "merchant_center", "disapproved_share", mc["disapproved_share"], "", ""])
        perf = mc.get("performance") or {}
        if perf:
            kpis.append([run_date, client, "merchant_center", "shopping_clicks", perf["clicks"], perf["clicks_prev"],
                         round((perf["clicks"] - perf["clicks_prev"]) / perf["clicks_prev"], 3) if perf["clicks_prev"] else None])
    summary = [[run_date, client, brief["status"], brief["headline"], brief["client_note"]]]
    return {"Summary": summary, "Alerts": alerts, "KPIs": kpis}


HEADERS = {
    "Summary": ["date", "client", "status", "headline", "client_note"],
    "Alerts": ["date", "client", "severity", "source", "title", "evidence", "likely_cause", "next_action", "owner"],
    "KPIs": ["date", "client", "source", "metric", "current", "previous", "change"],
}


def append_sheet(gsession, sheet_id: str, rows_by_tab: dict) -> dict:
    """Append rows to tabs Summary / Alerts / KPIs; creates missing tabs with a header row."""
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    meta = gsession.get(base, params={"fields": "sheets.properties.title"})
    if meta.status_code >= 400:
        return {"ok": False, "error": meta.text[:300]}
    have = {sh["properties"]["title"] for sh in meta.json().get("sheets", [])}
    missing = [t for t in rows_by_tab if t not in have]
    if missing:
        gsession.post(f"{base}:batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": t}}} for t in missing]})
        for t in missing:
            gsession.post(f"{base}/values/{t}!A1:append", params={"valueInputOption": "RAW"}, json={"values": [HEADERS[t]]})
    written = {}
    for tab, rows in rows_by_tab.items():
        if not rows:
            continue
        r = gsession.post(f"{base}/values/{tab}!A1:append", params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                          json={"values": rows})
        written[tab] = len(rows) if r.status_code < 400 else f"error {r.status_code}: {r.text[:200]}"
    return {"ok": True, "rows": written, "url": f"https://docs.google.com/spreadsheets/d/{sheet_id}"}


# ---------------------------------------------------------------- Markdown + HTML brief

def markdown(client: str, signals: dict, brief: dict) -> str:
    out = [f"# {client}: search & shopping brief", "", f"**Status:** {brief['status']}  ", f"**Headline:** {brief['headline']}", ""]
    out += ["## Alerts", ""]
    for a in brief["alerts"]:
        out += [f"### [{a['severity']}] {a['title']}", f"- Source: {a['source']}", f"- Evidence: {a['evidence']}",
                f"- Likely cause: {a['likely_cause']}", f"- Next action: {a['next_action']} (owner: {a['owner']})", ""]
    out += ["## Opportunities", ""]
    for o in brief["opportunities"]:
        out += [f"- **{o['title']}**: {o['evidence']} Next: {o['next_action']}"]
    out += ["", "## Note for the client", "", brief["client_note"], ""]
    out += ["## Rule-based alerts (before Claude)", ""]
    for r in signals["rule_alerts"]:
        if r["prev"] is None:
            share = f" ({r['change'] * 100:.0f}% of products)" if r["metric"] == "disapproved_share" else ""
            out.append(f"- {r['severity']}: {r['source']} / {r['metric']}: {r['cur']}{share}")
        else:
            out.append(f"- {r['severity']}: {r['source']} / {r['metric']}: {r['cur']} vs {r['prev']} ({pct(r['change'])})")
    return "\n".join(out) + "\n"


def html_report(client: str, signals: dict, brief: dict, run_date: str) -> str:
    e = html.escape
    s = signals["sources"]
    kpi_cells = []

    def kpi(label, cur, prev, change):
        cls = "neg" if (change or 0) < -0.1 else "pos" if (change or 0) > 0.1 else ""
        kpi_cells.append(f'<div class="kpi"><span class="lbl">{e(label)}</span><span class="val">{cur:,}</span>'
                         f'<span class="chg {cls}">{pct(change)} vs {prev:,}</span></div>')

    gsc = s.get("search_console", {})
    for m in ("clicks", "impressions"):
        if gsc.get("totals"):
            v = gsc["totals"][m]
            kpi(f"Search {m}", v["cur"], v["prev"], v["change"])
    ga = s.get("ga4", {})
    for m, label in (("sessions", "GA4 sessions"), ("keyEvents", "GA4 key events")):
        if ga.get("totals") and m in ga["totals"]:
            v = ga["totals"][m]
            kpi(label, v["cur"], v["prev"], v["change"])
    mc = s.get("merchant_center", {})
    if "products_total" in mc:
        bad = mc["status"].get("NOT_ELIGIBLE_OR_DISAPPROVED", 0)
        kpi_cells.append(f'<div class="kpi"><span class="lbl">Merchant: not eligible</span><span class="val">{bad:,}</span>'
                         f'<span class="chg {"neg" if mc["disapproved_share"] > 0.05 else ""}">'
                         f'{mc["disapproved_share"] * 100:.0f}% of {mc["products_total"]:,} products</span></div>')

    alerts = "".join(
        f'<tr><td><span class="sev {e(a["severity"])}">{e(a["severity"])}</span></td><td><b>{e(a["title"])}</b>'
        f'<div class="muted">{e(a["evidence"])}</div></td><td>{e(a["likely_cause"])}</td>'
        f'<td>{e(a["next_action"])}<div class="muted">{e(a["owner"].replace("_", " "))}</div></td></tr>'
        for a in brief["alerts"])
    opps = "".join(f'<li><b>{e(o["title"])}</b>. {e(o["evidence"])} <i>Next:</i> {e(o["next_action"])}</li>'
                   for o in brief["opportunities"])

    def qtable(rows, title):
        if not rows:
            return ""
        body = "".join(f'<tr><td>{e(r["query"])}</td><td>{r["impr_prev"]} → {r["impr"]}</td>'
                       f'<td>{r["clicks_prev"]} → {r["clicks"]}</td><td>{r["pos"] if r["pos"] else "-"}</td></tr>' for r in rows[:6])
        return (f'<h3>{e(title)}</h3><table class="data"><tr><th>Query</th><th>Impressions</th><th>Clicks</th>'
                f'<th>Position</th></tr>{body}</table>')

    issues = ""
    if mc.get("top_issues"):
        body = "".join(f'<tr><td><code>{e(i["code"])}</code></td><td>{e(i.get("attribute") or "")}</td><td>{i["count"]:,}</td>'
                       f'<td class="muted">{e("; ".join(i["examples"][:2]))}</td></tr>' for i in mc["top_issues"][:6])
        issues = (f'<h3>Merchant Center: top item issues</h3><table class="data"><tr><th>Issue</th><th>Attribute</th>'
                  f'<th>Products</th><th>Examples</th></tr>{body}</table>')
    meta = brief.get("_meta", {})
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(client)} brief</title><style>
:root{{--bg:#fafaf7;--fg:#1d1d1b;--mut:#6b6b66;--line:#e2e1da;--red:#c0392b;--amb:#c77d0a;--grn:#2e7d4f}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
header{{padding:28px 32px 20px;border-bottom:1px solid var(--line);background:#fff}}
main{{padding:24px 32px 48px;max-width:1180px}}h1{{margin:0;font-size:22px}}h2{{font-size:17px;margin:32px 0 10px}}h3{{font-size:14px;margin:22px 0 8px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}}
.status{{display:inline-block;padding:2px 10px;border-radius:99px;color:#fff;font-size:12px;font-weight:600;text-transform:uppercase;margin-left:8px;vertical-align:middle}}
.status.red{{background:var(--red)}}.status.amber{{background:var(--amb)}}.status.green{{background:var(--grn)}}
.headline{{font-size:18px;margin:10px 0 0;max-width:900px}}.muted{{color:var(--mut);font-size:13px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));border:1px solid var(--line);background:#fff}}
.kpi{{padding:14px 16px;border-right:1px solid var(--line);display:flex;flex-direction:column}}.kpi:last-child{{border-right:0}}
.lbl{{font-size:12px;color:var(--mut)}}.val{{font-size:24px;font-weight:650}}.chg{{font-size:12px;color:var(--mut)}}.chg.neg{{color:var(--red)}}.chg.pos{{color:var(--grn)}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line)}}td,th{{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{font-size:12px;color:var(--mut);font-weight:600}}.sev{{font-size:11px;font-weight:700;text-transform:uppercase}}.sev.high{{color:var(--red)}}.sev.medium{{color:var(--amb)}}.sev.low{{color:var(--mut)}}
ul{{padding-left:20px}}li{{margin:6px 0}}.note{{background:#fff;border:1px solid var(--line);padding:14px 16px;max-width:900px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}@media(max-width:800px){{.grid2{{grid-template-columns:1fr}}main,header{{padding-left:16px;padding-right:16px}}}}
footer{{margin-top:36px}}</style></head><body>
<header><div class="muted">Search &amp; shopping brief · {e(run_date)} · last {signals.get('window_days', 7)} days vs previous {signals.get('window_days', 7)}</div>
<h1>{e(client)}<span class="status {e(brief['status'])}">{e(brief['status'])}</span></h1>
<p class="headline">{e(brief['headline'])}</p></header><main>
<div class="kpis">{''.join(kpi_cells)}</div>
<h2>Alerts</h2><table><tr><th></th><th>What</th><th>Likely cause</th><th>Next action</th></tr>{alerts}</table>
<h2>Opportunities</h2><ul>{opps}</ul>
<h2>Note for the client</h2><div class="note">{e(brief['client_note'])}</div>
<h2>Data behind it</h2><div class="grid2"><div>{qtable(gsc.get('rising_queries'), 'Rising search queries')}{qtable(gsc.get('striking_distance'), 'Page 2 queries with demand')}</div>
<div>{issues}{qtable(gsc.get('losing_queries'), 'Queries losing clicks')}</div></div>
<footer class="muted">Sources: Google Search Console API, GA4 Data API, Merchant API (reports). Rules flag the numbers, Claude writes the brief
({e(str(meta.get('backend', '')))}, {e(str(meta.get('model', '')))}). Revenue is not collected.</footer>
</main></body></html>"""


def save(out_dir, client_id: str, run_date: str, raw: dict, signals: dict, brief: dict, client_name: str, write_raw=True):
    d = out_dir / client_id / run_date
    d.mkdir(parents=True, exist_ok=True)
    if write_raw:
        (d / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "signals.json").write_text(json.dumps(signals, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "brief.md").write_text(markdown(client_name, signals, brief), encoding="utf-8")
    (d / "brief.html").write_text(html_report(client_name, signals, brief, run_date), encoding="utf-8")
    return d


def today_str():
    return dt.date.today().isoformat()
