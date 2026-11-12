"""Weekly search & shopping brief for every client in clients.json.

    python -m opsbrief.run                       # all clients, send Telegram + Sheet
    python -m opsbrief.run --client store-a      # one client
    python -m opsbrief.run --dry-run             # collect + analyze, no Telegram / Sheet
    python -m opsbrief.run --from-cache          # reuse the last raw.json, only re-run the analysis
    python -m opsbrief.run --public              # mask client names and domains in every output

Pipeline per client: collect (GSC, GA4, Merchant) -> signals (rules) -> Claude brief -> deliver.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

from . import analyst, deliver, signals, sources

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def load_env(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def mask(obj, client: dict):
    """Replace the client's real name and domains with its alias, everywhere in a JSON-like object."""
    words = [w for w in client.get("mask", []) + [client.get("domain", ""), client.get("real_name", "")] if w]
    if not words:
        return obj
    pat = re.compile("|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)), re.I)
    url = re.compile(r"https?://(www\.)?" + re.escape(client.get("domain", "x.invalid")), re.I)

    def fix(v):
        if isinstance(v, str):
            return pat.sub(client["name"], url.sub("", v))
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        return v
    return fix(obj)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--client")
    ap.add_argument("--days", type=int, default=0, help="window length; default: client 'days' or 7")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-cache", action="store_true")
    ap.add_argument("--public", action="store_true", help="mask client names/domains; skip raw.json")
    ap.add_argument("--model", default="")
    args = ap.parse_args(argv)

    load_env(ROOT / ".env")
    cfg = json.loads((ROOT / os.environ.get("CLIENTS_FILE", "clients.json")).read_text(encoding="utf-8"))
    clients = [c for c in cfg["clients"] if not args.client or c["id"] == args.client]
    today = dt.date.today()
    run_date = today.isoformat()
    gs = sources.session(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])

    for c in clients:
        name = c["name"] if args.public else c.get("real_name", c["name"])
        print(f"== {name}", flush=True)
        days = args.days or c.get("days", 7)
        cache = OUT / c["id"] / "latest_raw.json"
        if args.from_cache and cache.exists():
            raw = json.loads(cache.read_text(encoding="utf-8"))
        else:
            raw = {"window_days": days}
            if c.get("gsc_site"):
                raw["gsc"] = sources.gsc(gs, c["gsc_site"], today, days)
            if c.get("ga4_property"):
                raw["ga4"] = sources.ga4(gs, c["ga4_property"], today, days)
            if c.get("merchant_id"):
                raw["merchant"] = sources.merchant(gs, c["merchant_id"], today, days)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        for k, v in raw.items():
            if isinstance(v, dict):
                print(f"   {k}: {'ok' if v.get('ok') else v.get('error', '')[:160]}", flush=True)

        sig = signals.build({**c, "name": name}, raw)
        if args.public:
            sig = mask(sig, c)
        print(f"   rule alerts: {len(sig['rule_alerts'])}; asking Claude...", flush=True)
        brief = analyst.analyze(sig, args.model)
        if args.public:
            brief = mask(brief, c)
        folder = deliver.save(OUT, c["id"] + ("-public" if args.public else ""), run_date, raw, sig, brief, name,
                              write_raw=not args.public)
        print(f"   status {brief['status']}: {brief['headline']}")
        print(f"   saved {folder}")

        if args.dry_run:
            continue
        tg = deliver.send_telegram(deliver.telegram_text(name, brief, c.get("report_url", "")))
        print(f"   telegram: {tg}")
        if os.environ.get("SHEET_ID"):
            res = deliver.append_sheet(gs, os.environ["SHEET_ID"], deliver.sheet_rows(run_date, name, sig, brief))
            print(f"   sheet: {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
