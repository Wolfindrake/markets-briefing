"""Cross-checks: is what we publish correct? Every run produces a scorecard shown on the site.

  1. One date     every number on the sheet is from the same market close (no mixing Nov 5 and Nov 6).
  2. Arithmetic   Prev + Chg = Last and Chg % = Chg / Prev for every row.
  3. Second source key prices confirmed by an independent quote: S&P 500 vs SPY ETF, US 10Y (Treasury) vs ^TNX,
                  gold futures vs GLD ETF, and the Investing.com CSV vs the automatic feed when both exist.
  4. Text facts   every % and bp figure quoted in the commentary must exist in today's table or calendar.
  5. News dates   headlines belong to the session (or after it, up to the next open).
"""
from __future__ import annotations

import re

from . import fetch

CHECK_TICKERS = {"chk_spy": "SPY", "chk_tnx": "^TNX", "chk_gld": "GLD"}


def _item(group, check, ok, detail):
    return {"group": group, "check": check, "ok": bool(ok), "detail": detail}


def _pct(series, date):
    s = [r for r in series if r["date"] <= date]
    if len(s) < 2 or s[-1]["date"] != date or not s[-2]["close"]:
        return None
    return (s[-1]["close"] / s[-2]["close"] - 1) * 100, s[-1]["close"]


def run(rows, market_date, csv_vals=None, csv_date=None, texts=None, calendar_rows=None, headlines=None,
        offline=False) -> dict:
    items = []
    sheet = [r for r in rows if r.get("sheet", True)]
    R = {r["key"]: r for r in rows}

    # 1. one date
    off = [f"{r['name']} ({r['date'] or 'no data'})" for r in sheet if r.get("date") != market_date]
    items.append(_item("One date", f"All {len(sheet)} sheet rows are from the {market_date} close",
                       not off, "OK" if not off else "Different date: " + "; ".join(off[:8]) + ("…" if len(off) > 8 else "")))

    # 2. arithmetic
    bad = []
    for r in sheet:
        if None in (r.get("last"), r.get("prev"), r.get("chg")):
            continue
        tol = max(abs(r["last"]) * 1e-6, 1e-6)
        if abs(r["prev"] + r["chg"] - r["last"]) > tol * 10:
            bad.append(f"{r['name']}: prev+chg≠last")
        if r.get("chg_pct") is not None and r["prev"] and r["unit"] not in ("yield", "cds"):
            if abs(r["chg"] / r["prev"] * 100 - r["chg_pct"]) > 0.02:
                bad.append(f"{r['name']}: chg % inconsistent")
    items.append(_item("Arithmetic", "Prev + Chg = Last and Chg % = Chg / Prev", not bad, "OK" if not bad else "; ".join(bad[:6])))

    # 3. second source
    if not offline:
        chk = fetch.yahoo(CHECK_TICKERS)
        spx = R.get("spx")
        a = _pct(chk.get("chk_spy", []), market_date)
        if spx and spx.get("chg_pct") is not None and a:
            d = abs(a[0] - spx["chg_pct"])
            items.append(_item("Second source", "S&P 500 daily move vs SPY ETF", d <= 0.15,
                               f"S&P {spx['chg_pct']:+.2f}% vs SPY {a[0]:+.2f}% (gap {d:.2f} pp)"))
        tnx = [r for r in chk.get("chk_tnx", []) if r["date"] <= market_date]
        us10 = R.get("us10")
        if us10 and us10.get("last") is not None and tnx and tnx[-1]["date"] == market_date:
            d = abs(tnx[-1]["close"] - us10["last"]) * 100
            items.append(_item("Second source", "US 10Y: Treasury par yield vs CBOE ^TNX", d <= 6,
                               f"Treasury {us10['last']:.3f}% vs ^TNX {tnx[-1]['close']:.3f}% (gap {d:.1f} bp)"))
        g = _pct(chk.get("chk_gld", []), market_date)
        xau = R.get("xau")
        if xau and xau.get("chg_pct") is not None and g:
            d = abs(g[0] - xau["chg_pct"])
            items.append(_item("Second source", "Gold daily move vs GLD ETF", d <= 0.8,
                               f"Gold {xau['chg_pct']:+.2f}% vs GLD {g[0]:+.2f}% (gap {d:.2f} pp)"))
    if csv_vals and csv_date == market_date:
        gaps = []
        for k, v in csv_vals.items():
            r = R.get(k)
            if r and r.get("source") not in ("investing_csv",) and r.get("last") and v.get("last"):
                rel = abs(v["last"] / r["last"] - 1) * 100
                if rel > 0.5:
                    gaps.append(f"{r['name']} {rel:.1f}%")
        items.append(_item("Second source", "Your Investing.com CSV vs the automatic feed (same day)", not gaps,
                           "OK" if not gaps else "Differ by >0.5%: " + "; ".join(gaps[:6])))

    # 4. text facts: every % / bp number in the commentary must exist in today's data
    allowed = set()

    def add(v, dps=(0, 1, 2)):
        if v is None:
            return
        for dp in dps:
            allowed.add(f"{abs(v):.{dp}f}")
    for r in rows:
        add(r.get("chg_pct"))
        add(r.get("last"), (0, 1, 2, 3))
        if r.get("chg") is not None:
            add(r["chg"] * (100 if r["unit"] == "yield" else 1))
        for v in (r.get("perf") or {}).values():
            add(v)
    for e in calendar_rows or []:
        for f in ("actual", "consensus", "previous"):
            for n in re.findall(r"\d+(?:\.\d+)?", str(e.get(f, ""))):
                allowed.add(n)
    missing = []
    for t in texts or []:
        for m in re.finditer(r"([+-]?\d[\d,]*(?:\.\d+)?)\s*(%|\s?bp)", t or ""):
            n = m.group(1).replace(",", "").lstrip("+-")
            if n not in allowed and str(float(n)).rstrip("0").rstrip(".") not in allowed:
                missing.append(m.group(0).strip())
    missing = sorted(set(missing))
    items.append(_item("Text facts", "Every % and bp figure in the commentary is in today's data", not missing,
                       "OK" if not missing else "Not found in the table: " + ", ".join(missing[:10]) + " (check before quoting)"))

    # 5. news dates
    if headlines is not None:
        n = len(headlines)
        sess = sum(1 for h in headlines if h.get("session"))
        items.append(_item("News", f"Headlines anchored to the {market_date} session", n > 0,
                           f"{sess} from the session day, {n - sess} after the close up to the next open" if n else "No headlines in the window"))

    passed = sum(1 for i in items if i["ok"])
    return {"passed": passed, "total": len(items), "items": items,
            "status": "verified" if passed == len(items) else "check"}
