"""Assemble site/data/dashboard.json: every section of the dashboard in one file.

Sections (same as the original dashboard): today-in-one-look, market tables with "what happened & why",
commentary cards, news, week ahead, 7-day history, plain-English view (big picture, chain, key numbers,
what to watch, world around, glossary), Lords of Finance, Trump Impact, sources & verification.
"Yesterday" versions are rotated automatically from the previous run.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .compute import PERF_KEYS, display
from .config import GROUPS
from .narrative import SHORT

GROUP_JS = {"equities": "equities", "fixed_income": "fixedIncome", "others": "others"}
COLUMNS = ["symbol", "last", "open", "prev", "chg", "chgPct", "daily", "week", "month", "ytd", "year", "y3"]


def snapshot(rows, market_date, as_of):
    snap = {"dateISO": market_date, "label": date.fromisoformat(market_date).strftime("%B %-d, %Y") + " (Close)",
            "asOf": as_of, "columns": COLUMNS, "equities": [], "fixedIncome": [], "others": []}
    for r in rows:
        d = display(r)
        snap[GROUP_JS[r["group"]]].append([r["name"], d["symbol"], d["last"], d["open"], d["prev"], d["chg"], d["chg_pct"],
                                           d["daily"]] + [d[k] for k in PERF_KEYS])
    return snap


def lof_section(scored: dict | None) -> dict:
    entries = (scored or {}).get("entries") or []
    if not entries:
        return {"enabled": True, "currentCall": None, "history": [], "balance": None, "hits": 0, "closed": 0,
                "howTo": "Log each call in data/journal.csv: session_date, call (Long/Short), reason, conviction."}

    def pct(x):
        return "—" if x is None else f"{x:+.2f}%"

    cur = entries[-1]
    current = {"weekOf": cur["session_date"], "call": cur.get("call") or "No call", "rationale": cur.get("reason", ""),
               "keyLevels": (f"Entry at the S&P 500 open {cur['entry']:,.2f} on {cur['session_date']}" if cur.get("entry") else "Entry at the next open")
               + (f" · marked {pct(cur.get('pnl_pct'))} at the {cur.get('exit_date')} close" if cur.get("pnl_pct") is not None else ""),
               "status": cur.get("status", "")}
    hist = []
    for i, e in enumerate(entries[:-1], 1):
        hist.append({"session": i, "weekOf": e["session_date"], "call": f"{e.get('call') or 'No call'} → {pct(e.get('pnl_pct'))}",
                     "rationale": e.get("reason", ""), "status": e.get("status", "")})
    return {"enabled": True, "currentCall": current, "history": list(reversed(hist)),
            "balance": scored.get("balance"), "hits": scored.get("hits", 0), "closed": scored.get("closed", 0), "start": scored.get("start", 100000)}


def trump_section(ai_trump, headlines_trump, previous, market_date, now_iso):
    if isinstance(ai_trump, dict) and (ai_trump.get("summaryBullets") or ai_trump.get("majorMoves")):
        t = dict(ai_trump)
    elif headlines_trump:
        t = {"summaryBullets": [f"{h['source']}: {h['headline']}" for h in headlines_trump[:5]],
             "weeklySummary": "Latest Trump-related headlines from the news feeds. Switch on the AI commentary for the market analysis.",
             "majorMoves": [], "forwardLook": [], "scenarios": []}
    elif previous:
        return previous
    else:
        t = {"summaryBullets": [], "weeklySummary": "No Trump-related headlines in the feeds today.", "majorMoves": [], "forwardLook": [], "scenarios": []}
    d = date.fromisoformat(market_date)
    monday = date.fromordinal(d.toordinal() - d.weekday())
    t.setdefault("forwardLook", [])
    t.setdefault("scenarios", [])
    t.setdefault("majorMoves", [])
    t["weekOf"] = monday.strftime("%B %-d, %Y")
    t["lastUpdated"] = now_iso
    t["sources"] = [{"name": f"{h['source']}: {h['headline']}", "url": h["url"]} for h in headlines_trump[:8]] or t.get("sources", [])
    t["disclaimer"] = ("Educational summary of publicly reported market reactions to Trump-related policy news, built from "
                       "the linked headlines. Not investment advice.")
    return t


def build(*, rows, market_date, week=None, macro=None, surprises=None, reading=None, as_of, text, brief, scored, issues, headlines, trump_heads, inputs, downloads, cfg,
          prev_path: Path, snaps_path: Path, history: dict) -> dict:
    now_iso = datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds")
    prev = json.loads(prev_path.read_text()) if prev_path.exists() else {}

    # ---- snapshots (rolling 15 sessions)
    snaps = json.loads(snaps_path.read_text()) if snaps_path.exists() else {}
    key = f"d{market_date}"
    snaps[key] = snapshot(rows, market_date, as_of)
    keep = sorted(snaps, key=lambda k: snaps[k]["dateISO"])[-15:]
    snaps = {k: snaps[k] for k in keep}
    snaps_path.parent.mkdir(parents=True, exist_ok=True)
    snaps_path.write_text(json.dumps(snaps, indent=1))
    earlier = [k for k in keep if snaps[k]["dateISO"] < market_date]
    previous_key = earlier[-1] if earlier else key

    # ---- today / yesterday rotation
    new_day = prev.get("currentKey") != key
    y_src = prev if new_day else {"overview": prev.get("overviewYesterday"), "news": prev.get("newsYesterday"),
                                  "simple": prev.get("simpleYesterday")}
    overview = text["overview"]
    simple = text["simple"]
    news = text["news"]
    blank_simple = {"bigPicture": "", "chain": {"explanation": "", "steps": []}, "driverNotes": {}, "forces": [], "keyNumbers": [],
                    "whatToWatch": [], "worldAround": [], "glossary": simple.get("glossary", [])}

    week_rows = []
    for e in (week if week is not None else (brief or {}).get("week_ahead") or []):
        week_rows.append([e.get("day", ""), e.get("region", ""), e.get("event", ""), e.get("consensus", "") or "—",
                     e.get("previous", "") or "—", str(e.get("date", "")), e.get("note", "") or "", e.get("url", "") or ""])

    by_key = {r["key"]: r for r in rows}
    D = {r["key"]: display(r) for r in rows}
    ticker_keys = ["spx", "ixic", "dji", "rut", "vix", "sx5e", "dax", "cac", "n225", "nifty", "us10", "us2", "de10", "brent", "xau", "btc", "eurusd"]
    ticker = [{"key": k, "name": SHORT.get(k, by_key[k]["name"]), "last": D[k]["last"], "chg": D[k]["chg"], "chgPct": D[k]["chg_pct"],
               "unit": by_key[k]["unit"]} for k in ticker_keys if k in by_key and by_key[k]["last"] is not None]
    movers = sorted([r for r in rows if r["chg_pct"] is not None and r["unit"] not in ("yield", "cds")], key=lambda r: r["chg_pct"])
    heat = [{"key": r["key"], "name": SHORT.get(r["key"], r["name"]), "group": r["group"], "unit": r["unit"], "chgPct": r["chg_pct"],
             "chgBp": (r["chg"] * (100 if r["unit"] == "yield" else 1)) if (r["chg"] is not None and r["unit"] in ("yield", "cds")) else None,
             "label": D[r["key"]]["chg"] if r["unit"] in ("yield", "cds") else D[r["key"]]["chg_pct"], "last": D[r["key"]]["last"]} for r in rows]

    sources = [{"name": "Yahoo Finance (indices, FX, commodities, crypto)", "url": "https://finance.yahoo.com/"},
               {"name": "US Treasury daily par yield curve", "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"},
               {"name": "Deutsche Bundesbank (German 10-year)", "url": "https://www.bundesbank.de/en/statistics/money-and-capital-markets/interest-rates-and-yields"},
               {"name": "Japan Ministry of Finance (JGB yields)", "url": "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"},
               {"name": "FRED, Federal Reserve Bank of St. Louis (macro dashboard)", "url": "https://fred.stlouisfed.org/"}]
    if inputs.get("csv_file"):
        sources.append({"name": f"Investing.com watchlist export ({inputs['csv_file']})", "url": ""})
    sources += [{"name": f"{h['source']}: {h['headline']}", "url": h["url"]} for h in news[:10]]

    unverified = [f"{i['name']}: {'; '.join(i['flags'])}" for i in issues]
    data = {
        "currentKey": key, "previousKey": previous_key, "updatedAt": now_iso, "marketDate": market_date,
        "aiUsed": bool(text.get("ai_used")),
        "overview": overview,
        "overviewYesterday": y_src.get("overview") or {"date": "", "asOf": "", "items": []},
        "news": news,
        "newsYesterday": y_src.get("news") or [],
        "simple": simple,
        "simpleYesterday": y_src.get("simple") or blank_simple,
        "snapshots": snaps,
        "weekAhead": week_rows,
        "lordsOfFinance": lof_section(scored),
        "macro": macro or {},
        "surprises": surprises or [],
        "reading": reading or {},
        "trumpImpact": trump_section(text.get("trump"), trump_heads, prev.get("trumpImpact"), market_date, now_iso),
        "verification": {"overallStatus": "verified" if not issues else "partial",
                         "note": ("Numbers from free official and market sources, refreshed automatically after the US close. "
                                  "Commentary " + ("written by AI from the linked headlines; check before quoting." if text.get("ai_used")
                                                   else "is an automatic summary of the numbers.")),
                         "verifiedItems": sorted({r["source"] for r in rows if r["source"] not in ("none", "history")}),
                         "unverifiedItems": unverified},
        "sources": sources,
        "ticker": ticker,
        "movers": {"gainers": [{"name": r["name"], "chgPct": D[r["key"]]["chg_pct"], "last": D[r["key"]]["last"]} for r in reversed(movers[-5:])],
                   "losers": [{"name": r["name"], "chgPct": D[r["key"]]["chg_pct"], "last": D[r["key"]]["last"]} for r in movers[:5]]},
        "heatmap": heat,
        "history": history,
        "downloads": downloads,
        "briefingCurrent": bool(brief) and str(brief.get("date", "")) == market_date,
        "site": cfg.get("site", {}),
    }
    return data
