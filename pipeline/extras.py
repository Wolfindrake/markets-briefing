"""Optional add-ons. Both are skipped silently unless their secrets are configured.

* draft_commentary(): asks an AI model (Anthropic API) for a FIRST DRAFT of the sheet text, from
  today's numbers and RSS headlines, written to content/draft.yaml. It never touches
  content/briefing.yaml: a person reviews and copies what is right.
* supabase_sync(): upserts today's rows into a Supabase table `prices` (see supabase/schema.sql).
"""
from __future__ import annotations

import json
import logging
import os
import re
import xml.etree.ElementTree as ET

import requests
import yaml

from .compute import display

log = logging.getLogger("extras")


def _headlines(feeds, limit):
    items = []
    for url in feeds or []:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "markets-briefing/1.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                t = (it.findtext("title") or "").strip()
                if t:
                    items.append(t)
        except Exception as exc:  # noqa: BLE001
            log.warning("feed failed %s: %s", url, exc)
    seen, out = set(), []
    for t in items:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:limit]


PROMPT = """You draft a one-page markets briefing for a business-school class, written as notes for a managing director
before a client meeting: report figures and how they compared with expectations, no explanations of concepts.
Use ONLY the numbers in the table and the headlines below. If something is not supported, leave it out.
Return YAML with exactly these keys:
overview: 2-3 sentences, the headline story
highlights: 5-8 bullets (data releases with actual vs expected, central banks, earnings, geopolitics)
performance: {{equities: [3-4 bullets], fixed_income: [3-4 bullets], others: [3-4 bullets]}}  # cite moves from the table, yields in bp
week_ahead: []   # leave empty; a person fills it from an economic calendar
sp500_view: {{call: "", reason: ""}}  # leave empty; a person decides

Market date: {date}
TABLE (name | last | chg | chg% | 1 week | YTD):
{table}

HEADLINES:
{headlines}
"""


def draft_commentary(rows, market_date, cfg, out_path):
    key = os.environ.get("ANTHROPIC_API_KEY")
    dcfg = (cfg or {}).get("draft") or {}
    if not key or not dcfg.get("enabled"):
        return False
    table = "\n".join(
        f"{d['name']} | {d['last']} | {d['chg']} | {d['chg_pct']} | {d['week']} | {d['ytd']}"
        for d in (display(r) for r in rows)
    )
    heads = "\n".join(f"- {h}" for h in _headlines(dcfg.get("rss_feeds"), dcfg.get("max_headlines", 40)))
    body = {
        "model": dcfg.get("model", "claude-sonnet-5-5"),
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": PROMPT.format(date=market_date, table=table, headlines=heads)}],
    }
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=120, json=body,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []))
        text = re.sub(r"^```(?:yaml)?|```$", "", text.strip(), flags=re.M).strip()
        data = yaml.safe_load(text) or {}
        data = {"date": market_date, "status": "DRAFT - review every line before copying into briefing.yaml", **data}
        out_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        log.info("draft written to %s", out_path)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("draft failed: %s", exc)
        return False


def supabase_sync(rows):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return False
    payload = [
        {"date": r["date"], "key": r["key"], "close": r["last"], "open": r["open"], "chg_pct": r["chg_pct"], "source": r["source"]}
        for r in rows if r.get("last") is not None and r.get("date") and r["source"] not in ("history", "none")
    ]
    try:
        resp = requests.post(
            f"{url.rstrip('/')}/rest/v1/prices?on_conflict=date,key", data=json.dumps(payload), timeout=60,
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        resp.raise_for_status()
        log.info("supabase: upserted %d rows", len(payload))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("supabase sync failed: %s", exc)
        return False
