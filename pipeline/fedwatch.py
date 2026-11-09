"""Fed meeting odds from 30-day fed funds futures (the same arithmetic as CME FedWatch), free from Yahoo.

Futures price P -> implied average fed funds rate for that month = 100 - P.
For the month of the next FOMC (meeting on day d of a month with N days):
    implied = pre * d/N + post * (N-d)/N   ->   post = (implied - pre * d/N) / ((N-d)/N)
pre = implied rate of the month before (no meeting in it). Probability of a 25 bp hike = (post - pre) / 0.25.
"""
from __future__ import annotations

import calendar as _cal
import logging
from datetime import date, timedelta

from . import calendar as econ_calendar
from . import fetch

log = logging.getLogger("fedwatch")
CODES = "FGHJKMNQUVXZ"
# fallback if the economic calendar is unavailable (Fed's published 2026 schedule, decision days)
FOMC_FALLBACK = ["2026-12-09"]


def _ticker(y, m):
    return f"ZQ{CODES[m - 1]}{str(y)[2:]}.CBT"


def next_meeting(market_date: str) -> date | None:
    md = date.fromisoformat(market_date)
    try:
        raw = econ_calendar.fetch(md + timedelta(days=1), md + timedelta(days=120))
        for e in sorted(raw, key=lambda x: x.get("dateUtc", "")):
            if e.get("currencyCode") == "USD" and "fed interest rate decision" in (e.get("name") or "").lower():
                return date.fromisoformat(e["dateUtc"][:10])
    except Exception as exc:  # noqa: BLE001
        log.warning("FOMC date from calendar failed: %s", exc)
    later = [date.fromisoformat(d) for d in FOMC_FALLBACK if d > market_date]
    return later[0] if later else None


def odds(market_date: str, offline: bool = False) -> dict | None:
    if offline:
        return None
    meet = next_meeting(market_date)
    if not meet:
        return None
    prev_m = (meet.replace(day=1) - timedelta(days=1))
    tick = {"pre": _ticker(prev_m.year, prev_m.month), "meet": _ticker(meet.year, meet.month)}
    data = fetch.yahoo(tick)
    pts = {k: [r for r in data.get(k, []) if r["date"] <= market_date] for k in tick}
    if len(pts["pre"]) < 1 or len(pts["meet"]) < 1:
        log.warning("fed funds futures unavailable")
        return None

    def calc(i):
        pre = 100 - pts["pre"][i]["close"]
        imp = 100 - pts["meet"][i]["close"]
        n = _cal.monthrange(meet.year, meet.month)[1]
        d = meet.day
        post = (imp - pre * d / n) / ((n - d) / n)
        return pre, post, (post - pre) / 0.25

    pre, post, p = calc(-1)
    prev = calc(-2)[2] if len(pts["pre"]) > 1 and len(pts["meet"]) > 1 else None
    hike = max(0.0, min(1.0, p)) * 100
    cut = max(0.0, min(1.0, -p)) * 100
    move = "hike" if p > 0.05 else "cut" if p < -0.05 else "hold"
    text = (f"Fed funds futures price a {hike:.0f}% chance of a 25 bp hike at the {meet:%-d %b} FOMC" if move == "hike" else
            f"Fed funds futures price a {cut:.0f}% chance of a 25 bp cut at the {meet:%-d %b} FOMC" if move == "cut" else
            f"Fed funds futures price no change at the {meet:%-d %b} FOMC")
    chg = None if prev is None else (p - prev) * 100
    if chg is not None and abs(chg) >= 1:
        text += f" ({chg:+.0f} pp on the day)"
    return {"meeting": meet.isoformat(), "pre": round(pre, 3), "post": round(post, 3), "prob": round(p * 100, 1),
            "hike": round(hike), "cut": round(cut), "change_pp": None if chg is None else round(chg, 1),
            "implied_bp": round((post - pre) * 100, 1), "tickers": tick, "text": text + "."}
