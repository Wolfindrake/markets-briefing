"""Automatic economic calendar: week ahead + released data with consensus.

Source: the public economic-calendar feed used by FXStreet's website, the same endpoint the open-source
`ecocal` package (github.com/lcsrodriguez/ecocal, MIT) reads. No key, no login. Data "as is": it is checked
against the official releases where we can (see verify.py) and you can always override any entry in
content/briefing.yaml.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

import requests

log = logging.getLogger("calendar")
URL = "https://calendar-api.fxstreet.com/en/api/v1/eventDates/{start}T00:00:00Z/{end}T23:59:59Z"
HEAD = {"User-Agent": "Mozilla/5.0 (compatible; markets-briefing/1.0)", "Referer": "https://www.fxstreet.com/",
        "Accept": "application/json"}
REGION = {"US": "US", "EMU": "EZ", "UK": "UK", "DE": "DE", "CN": "CN", "JP": "JP", "FR": "FR"}
CCY = {"USD", "EUR", "GBP", "CNY", "JPY"}
SKIP = re.compile(r"MPC Vote Rate (Cut|Unchanged)|Minutes|Monetary Policy (Report|Summary)|Press Conference", re.I)


def fetch(start: date, end: date) -> list[dict]:
    try:
        r = requests.get(URL.format(start=start.isoformat(), end=end.isoformat()), headers=HEAD, timeout=25)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as exc:  # noqa: BLE001
        log.warning("economic calendar unavailable: %s", exc)
        return []


def _fmt(v, unit, name=""):
    if v is None:
        return ""
    if not (unit or "").strip() and re.search(r"payroll|employment change|jobless claims|claims", name or "", re.I):
        unit = "K"
    s = f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, (int, float)) else str(v)
    u = (unit or "").strip()
    return f"{s}{'%' if u == '%' else (u.lower() if u in ('K', 'M', 'B') else '')}"


SHORT = [(r"Harmonized Index of Consumer Prices", "HICP"), (r"Consumer Price Index", "CPI"), (r"Producer Price Index", "PPI"),
         (r"Gross Domestic Product", "GDP"), (r"Personal Consumption Expenditures\s*-?\s*Price Index", "PCE prices"),
         (r"Nonfarm Payrolls", "Nonfarm payrolls"), (r"ex Food & Energy", "core"), (r"Interest Rate Decision", "rate decision"),
         (r"'s (Governor|President|Chair)", r" \1")]


def short(name):
    n = name or ""
    for a, b in SHORT:
        n = re.sub(a, b, n, flags=re.I)
    return re.sub(r"\s+", " ", n).strip()


def _base(name):
    n = re.sub(r"\s*\((MoM|YoY|QoQ|Annualized)\)", "", short(name))
    return re.sub(r"\bcore\s*|\s*core\b", "", n, flags=re.I).strip() or n


def build(market_date: str, days_back: int = 8, days_ahead: int = 10) -> tuple[list[dict], list[dict]]:
    """Return (upcoming week-ahead rows, released rows with actual/consensus) in briefing.yaml's format."""
    md = date.fromisoformat(market_date)
    raw = fetch(md - timedelta(days=days_back), md + timedelta(days=days_ahead))
    keep = [e for e in raw if str(e.get("volatility", "")).upper() == "HIGH" and e.get("currencyCode") in CCY
            and not SKIP.search(e.get("name") or "")]
    groups: dict[tuple, list[dict]] = {}
    for e in keep:
        groups.setdefault((e.get("dateUtc", "")[:16], e.get("currencyCode"), _base(e.get("name"))), []).append(e)

    upcoming, released = [], []
    for (when, _ccy, base), items in sorted(groups.items()):
        try:
            dt = datetime.fromisoformat(when.replace("Z", "") + ":00" if len(when) == 16 else when.replace("Z", ""))
        except ValueError:
            continue
        d = dt.date()
        region = REGION.get(items[0].get("countryCode", ""), items[0].get("countryCode", ""))
        main = next((i for i in items if "(YoY)" in (i.get("name") or "")), items[0])
        speech = any(i.get("isSpeech") for i in items)
        yoy = [i for i in items if "(YoY)" in (i.get("name") or "")] or items
        head = next((i for i in yoy if "ex Food" not in (i.get("name") or "")), yoy[0])
        core = next((i for i in yoy if "ex Food" in (i.get("name") or "") and i is not head), None)
        main = head
        label = base + ("" if speech else (" y/y" if "(YoY)" in (main.get("name") or "") else "")) + (" and core" if core else "")

        def pair(f):
            a = _fmt(head.get(f), head.get("unit"), head.get("name"))
            b = _fmt(core.get(f), core.get("unit"), core.get("name")) if core else ""
            return f"{a} / core {b}" if a and b else a
        ev = {"date": d, "day": f"{d:%a} {d.day} {d:%b}", "region": region,
              "event": f"{label}, {dt:%H:%M} GMT", "consensus": pair("consensus"), "previous": pair("previous"),
              "source": "calendar"}
        if d > md:
            upcoming.append(ev)
        elif main.get("actual") is not None:
            if main.get("consensus") is not None:
                released.append({**ev, "event": label.replace(" and core", ""), "actual": _fmt(main.get("actual"), main.get("unit"), main.get("name")),
                                 "consensus": _fmt(main.get("consensus"), main.get("unit"), main.get("name")),
                                 "previous": _fmt(main.get("previous"), main.get("unit"), main.get("name"))})
    return upcoming[:10], released


def merge(user: list[dict], auto: list[dict]) -> list[dict]:
    """Your entries in content/briefing.yaml win: an automatic entry is dropped when you have one for the same
    day and region (or the same day and first word). Result sorted by date."""
    def words(e):
        return set(re.findall(r"[a-z]{3,}", short(str(e.get("event", ""))).lower()))
    out = list(user)
    for e in auto:
        dup = any(str(u.get("date", "")) == str(e.get("date", "")) and
                  ((u.get("region") or "").upper() == (e.get("region") or "").upper() and (words(u) & words(e)))
                  for u in user)
        if not dup:
            out.append(e)
    return sorted(out, key=lambda e: str(e.get("date", "9999")))


def sheet_rows(entries: list[dict], limit: int = 6) -> list[dict]:
    """The professor's week-ahead style: one row per day and region, events joined with '. ', 5-7 rows,
    with 'Ahead' rows (e.g. the next FOMC) kept at the end."""
    ahead = [e for e in entries if str(e.get("day", "")).lower() == "ahead"]
    dated = [e for e in entries if e not in ahead]
    rows, index = [], {}
    for e in dated:
        k = (str(e.get("date", "")), e.get("day", ""))
        if k in index:
            r = rows[index[k]]
            regions = [x for x in str(r["region"]).split(" / ") if x]
            if e.get("region") and e["region"] not in regions:
                regions.append(e["region"])
            r["region"] = " / ".join(regions)
            r["event"] = f"{r['event']}. {e.get('event', '')}"
            r["consensus"] = " · ".join(x for x in (r["consensus"], e.get("consensus", "")) if x)
            r["previous"] = " · ".join(x for x in (r["previous"], e.get("previous", "")) if x)
        else:
            index[k] = len(rows)
            rows.append({**e, "consensus": e.get("consensus", "") or "", "previous": e.get("previous", "") or ""})
    return rows[:limit] + ahead[:2]
