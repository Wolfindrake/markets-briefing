"""The professor's top-down toolkit (M4S4), automated.

  * dashboard(): the seven-indicator macro dashboard (growth, jobs, inflation, PMI, policy rate, 10-year, wages),
    plus real rates and a rule-of-thumb read of the business cycle. US data come free from FRED (no key needed).
  * surprises(): "markets trade the surprise, not the level". For every released event in the week-ahead list
    that has an `actual` and a `consensus`, answer the four questions:
      1. what was released vs consensus, 2. hawkish / dovish / growth surprise,
      3. what it changes for the central bank, 4. what actually moved, and does it match the reaction map.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date

import requests

from .compute import display

log = logging.getLogger("macro")
UA = {"User-Agent": "Mozilla/5.0 (compatible; markets-briefing/1.0)"}
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"

SERIES = {
    "gdp": "A191RL1Q225SBEA",      # real GDP, % change annualised (quarterly)
    "unrate": "UNRATE",            # unemployment rate
    "payems": "PAYEMS",            # nonfarm payrolls, thousands
    "cpi": "CPIAUCSL",             # CPI all items
    "core": "CPILFESL",            # CPI ex food & energy
    "pce_core": "PCEPILFE",        # core PCE price index (the Fed's preferred gauge)
    "fed_lo": "DFEDTARL", "fed_hi": "DFEDTARU",
    "effr": "EFFR",                # effective fed funds rate
    "ecb": "ECBDFR",               # ECB deposit facility rate
    "ahe": "CES0500000003",        # average hourly earnings
}


def fred(series_id: str) -> list[tuple[str, float]]:
    try:
        r = requests.get(FRED_CSV.format(series_id), headers=UA, timeout=30)
        r.raise_for_status()
        out = []
        for row in csv.reader(io.StringIO(r.text)):
            if len(row) >= 2 and re.match(r"\d{4}-\d{2}-\d{2}$", row[0]):
                try:
                    out.append((row[0], float(row[1])))
                except ValueError:
                    continue
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("FRED %s failed: %s", series_id, exc)
        return []


def _yoy(s, i=-1):
    """Year-on-year % by matching the same month a year earlier (FRED has gaps, e.g. Oct 2025 CPI)."""
    if not s or len(s) < -i:
        return None
    d, now = s[i]
    past = dict(s).get(f"{int(d[:4]) - 1}{d[4:]}")
    return (now / past - 1) * 100 if past else None


def _month(iso):
    return date.fromisoformat(iso).strftime("%b %Y")


def _quarter(iso):
    d = date.fromisoformat(iso)
    return f"Q{(d.month - 1) // 3 + 1} {d.year}"


def _sahm(unrate):
    """Sahm-rule gap: 3-month average unemployment minus its low of the prior 12 months."""
    if len(unrate) < 15:
        return None
    vals = [v for _, v in unrate]
    avg3 = [sum(vals[i - 2:i + 1]) / 3 for i in range(2, len(vals))]
    return avg3[-1] - min(avg3[-13:-1])


def dashboard(rows: list[dict], offline: bool, manual: list[dict] | None = None) -> dict:
    """Build the macro dashboard. `manual` = extra readings typed in content/briefing.yaml (e.g. ISM PMI)."""
    R = {r["key"]: r for r in rows}
    data = {} if offline else {k: fred(v) for k, v in SERIES.items()}
    ind = []

    def add(key, name, latest, previous, measures, impact, src="FRED"):
        ind.append({"key": key, "name": name, "latest": latest, "previous": previous, "measures": measures,
                    "impact": impact, "source": src})

    g = data.get("gdp") or []
    if g:
        add("gdp", "GDP growth", f"{_quarter(g[-1][0])}: {g[-1][1]:+.1f}% annualised",
            f"{_quarter(g[-2][0])}: {g[-2][1]:+.1f}%" if len(g) > 1 else "", "Total output of the economy",
            "Stronger growth supports earnings and equities")
    u, p = data.get("unrate") or [], data.get("payems") or []
    if u:
        pay = ""
        if len(p) >= 2:
            pay = f"; payrolls {p[-1][1] - p[-2][1]:+,.0f}k"
        prev_pay = f"; payrolls {p[-2][1] - p[-3][1]:+,.0f}k" if len(p) >= 3 else ""
        add("jobs", "Unemployment & payrolls", f"{_month(u[-1][0])}: {u[-1][1]:.1f}%{pay}",
            (f"{_month(u[-2][0])}: {u[-2][1]:.1f}%{prev_pay}" if len(u) > 1 else ""), "Labour market strength",
            "Low unemployment supports consumption; very strong jobs can be read as hawkish")
    c, cc = data.get("cpi") or [], data.get("core") or []
    cpi_yoy = _yoy(c) if c else None
    core_yoy = _yoy(cc) if cc else None
    if cpi_yoy is not None:
        add("cpi", "Inflation (CPI)", f"{_month(c[-1][0])}: {cpi_yoy:.1f}% headline" + (f", {core_yoy:.1f}% core" if core_yoy is not None else ""),
            (f"{_month(c[-2][0])}: {_yoy(c, -2):.1f}% headline" if _yoy(c, -2) is not None else ""),
            "Change in consumer prices, year on year", "High inflation means tighter policy and pressure on valuations")
    pc = data.get("pce_core") or []
    if _yoy(pc) is not None:
        add("pce", "Core PCE (the Fed's gauge)", f"{_month(pc[-1][0])}: {_yoy(pc):.1f}%",
            f"{_month(pc[-2][0])}: {_yoy(pc, -2):.1f}%" if _yoy(pc, -2) is not None else "",
            "Prices ex food and energy, the Fed's preferred measure", "Above 2% keeps the Fed leaning hawkish")
    for m in manual or []:
        if isinstance(m, dict) and m.get("name") and m.get("latest"):
            add(str(m.get("key", m["name"])).lower().replace(" ", "_"), str(m["name"]), str(m["latest"]), str(m.get("previous", "")),
                str(m.get("measures", "")), str(m.get("impact", "")), "your entry")
    lo, hi, ecb = data.get("fed_lo") or [], data.get("fed_hi") or [], data.get("ecb") or []
    if lo and hi:
        pol = f"Fed {lo[-1][1]:.2f}% to {hi[-1][1]:.2f}%" + (f"; ECB deposit {ecb[-1][1]:.2f}%" if ecb else "")
        prev_hi = next((v for d, v in reversed(hi) if v != hi[-1][1]), None)
        add("policy", "Policy rate", pol, f"Fed upper bound before the last move: {prev_hi:.2f}%" if prev_hi is not None else "",
            "Central bank target rate", "Higher rates raise discount rates for every asset")
    if "us10" in R and R["us10"]["last"] is not None:
        d10 = display(R["us10"])
        add("us10", "10-year government yield", f"US 10Y {R['us10']['last']:.2f}% ({d10['chg']} today, {d10['week']} on the week)",
            f"{d10['ytd']} YTD", "Market long-term rate", "The benchmark discount rate for all assets", "market data")
    w = data.get("ahe") or []
    wage_yoy = _yoy(w) if w else None
    if wage_yoy is not None:
        real = f"; real wages {'rising' if cpi_yoy is None or wage_yoy > cpi_yoy else 'falling'}" if cpi_yoy is not None else ""
        add("wages", "Wages", f"{_month(w[-1][0])}: {wage_yoy:+.1f}% y/y{real}", "", "Average hourly earnings",
            "Drive consumption and services inflation")

    # real policy rate (professor's worked example: effective fed funds minus CPI)
    real_rate = None
    e = data.get("effr") or []
    if e and cpi_yoy is not None:
        real_rate = {"effr": round(e[-1][1], 2), "cpi": round(cpi_yoy, 1), "core": None if core_yoy is None else round(core_yoy, 1),
                     "real_headline": round(e[-1][1] - cpi_yoy, 1), "real_core": None if core_yoy is None else round(e[-1][1] - core_yoy, 1)}
        rh = real_rate["real_headline"]
        real_rate["read"] = ("Policy is barely restrictive against headline inflation." if 0 <= rh < 1 else
                             "Real rates are negative: money is effectively cheap." if rh < 0 else
                             "Real rates are clearly positive: policy is restrictive.")

    # business-cycle phase, rule of thumb (inputs shown so you can disagree)
    cycle = None
    if g and u and cpi_yoy is not None and hi:
        gdp_now = g[-1][1]
        sahm = _sahm(u)
        six_m_ago = next((v for d, v in reversed(hi) if d <= _months_back(hi[-1][0], 6)), hi[0][1])
        policy_move = hi[-1][1] - six_m_ago
        reasons = [f"GDP {gdp_now:+.1f}%", f"CPI {cpi_yoy:.1f}%", f"Fed upper bound {policy_move:+.2f} pp vs 6 months ago"]
        if sahm is not None:
            reasons.append(f"unemployment gap {sahm:+.2f} pp (0.5 = recession signal)")
        if gdp_now < 0 or (sahm is not None and sahm >= 0.5):
            phase = "Recession risk"
            text = "Growth is falling or unemployment is rising fast: equities fall and government bonds usually outperform."
        elif gdp_now >= 2 and cpi_yoy >= 3 and policy_move >= 0:
            phase = "Late expansion, near the peak"
            text = "Strong growth, inflation above target and central banks hiking or on hold: inflation worries and higher volatility."
        elif policy_move < 0 and (sahm or 0) > 0.2:
            phase = "Recovery"
            text = "Policy is easing after a slowdown: credit and equities tend to rebound early."
        else:
            phase = "Expansion"
            text = "Rising output and a firm labour market: equities strong, cyclicals lead."
        cycle = {"phase": phase, "text": text, "inputs": reasons}

    return {"indicators": ind, "realRate": real_rate, "cycle": cycle, "cpiYoy": cpi_yoy,
            "asOf": max((s[-1][0] for s in data.values() if s), default="")}


def _months_back(iso, n):
    d = date.fromisoformat(iso)
    y, m = divmod(d.month - 1 - n, 12)
    return date(d.year + y, m + 1, min(d.day, 28)).isoformat()


# ---------------------------------------------------------------- surprises (the four questions)

_NUM = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

KINDS = [
    ("cb", ["fomc", "fed decision", "fed rate", "ecb", "boe", "bank of england", "boj", "bank of japan", "rate decision", "policy rate"]),
    ("inverse", ["unemployment", "jobless", "claims", "challenger"]),
    ("inflation", ["cpi", "pce", "ppi", "inflation", "hicp", "prices", "hourly earnings", "wages"]),
    ("growth", ["payroll", "nfp", "gdp", "pmi", "ism", "retail", "adp", "jolts", "sentiment", "confidence", "industrial",
                "durable", "housing", "orders", "employment"]),
]

MAP = {  # the professor's market reaction map (typical first reactions)
    "hawkish": {"yields": "up", "usd": "up", "equities": "down", "outperform": "Value, energy, banks; growth and tech lag",
                "cb": "Raises the odds of a hike, or of fewer cuts"},
    "dovish": {"yields": "down", "usd": "down", "equities": "up", "outperform": "Growth and tech lead",
               "cb": "Lowers the odds of a hike; more room to cut"},
    "growth_pos": {"yields": "up", "usd": "up", "equities": "up", "outperform": "Cyclicals, small caps (if inflation is contained)",
                   "cb": "Supports holding or hiking"},
    "growth_neg": {"yields": "down", "usd": "down", "equities": "mixed", "outperform": "Bonds, defensives (utilities, staples)",
                   "cb": "Raises the odds of easing"},
    "inline": {"yields": "flat", "usd": "flat", "equities": "flat", "outperform": "",
               "cb": "No change to the expected path"},
}
LABEL = {"hawkish": "Hawkish surprise", "dovish": "Dovish surprise", "growth_pos": "Growth-positive surprise",
         "growth_neg": "Growth-negative surprise", "inline": "In line with consensus"}


def number(s) -> float | None:
    if s is None:
        return None
    t = str(s).replace("−", "-").replace(",", "")
    t = re.sub(r"(\d)\s*(%?)\s*-\s*(\d)", r"\1\2 to \3", t)
    nums = [float(x) for x in _NUM.findall(t)]
    if not nums:
        return None
    # a range such as "3.75%-4.00%" counts as its upper bound; units (k, %) are kept as typed
    return max(nums) if (len(nums) == 2 and re.search(r"\d\s*%?\s*(?:-|to)\s*\d", t)) else nums[0]


def kind_of(event: str) -> str:
    e = (event or "").lower()
    for k, words in KINDS:
        if any(w in e for w in words):
            return k
    return "growth"


def classify(event: str, actual, consensus, inflation_high: bool = False) -> tuple[str, float | None]:
    a, c = number(actual), number(consensus)
    if a is None or c is None:
        return "", None
    diff = a - c
    if abs(diff) < 1e-9:
        return "inline", 0.0
    k = kind_of(event)
    if k in ("cb", "inflation"):
        return ("hawkish" if diff > 0 else "dovish"), diff
    if k == "inverse":
        return ("growth_neg" if diff > 0 else "growth_pos"), diff
    return ("growth_pos" if diff > 0 else "growth_neg"), diff


def _arrow(v, eps):
    if v is None:
        return None
    return "up" if v > eps else "down" if v < -eps else "flat"


def actual_moves(rows: list[dict], euro: bool = False) -> dict:
    R = {r["key"]: r for r in rows}
    y = R.get("de10" if euro else "us2")
    eq = R.get("sx5e" if euro else "spx")
    fx = R.get("eurusd")
    out = {"yields": None, "usd": None, "equities": None, "detail": []}
    if y and y["chg"] is not None:
        bp = y["chg"] * 100
        out["yields"] = _arrow(bp, 1.0)
        out["detail"].append(f"{'Germany 10Y' if euro else 'US 2Y'} {bp:+.0f} bp")
    if fx and fx["chg_pct"] is not None:
        out["usd"] = _arrow(-fx["chg_pct"], 0.05)
        out["detail"].append(f"EUR/USD {fx['chg_pct']:+.2f}%")
    if eq and eq["chg_pct"] is not None:
        out["equities"] = _arrow(eq["chg_pct"], 0.15)
        out["detail"].append(f"{'Euro Stoxx 50' if euro else 'S&P 500'} {eq['chg_pct']:+.1f}%")
    return out


def surprises(week_ahead: list[dict], rows: list[dict], market_date: str, cpi_yoy: float | None) -> list[dict]:
    out = []
    infl_high = cpi_yoy is not None and cpi_yoy > 3
    md = date.fromisoformat(market_date)
    for e in week_ahead or []:
        if not isinstance(e, dict) or str(e.get("actual", "") or "").strip() == "":
            continue
        if e.get("date"):  # only releases since the last week ("what happened since the last session")
            try:
                age = (md - date.fromisoformat(str(e["date"]))).days
            except ValueError:
                age = 0
            if age < 0 or age > 8:
                continue
        ev = str(e.get("event", ""))
        sig, diff = classify(ev, e.get("actual"), e.get("consensus"), infl_high)
        if not sig:
            out.append({"event": ev, "date": str(e.get("date", "")), "day": e.get("day", ""), "region": e.get("region", ""),
                        "actual": str(e.get("actual")), "consensus": str(e.get("consensus", "") or "—"), "previous": str(e.get("previous", "") or "—"),
                        "signal": "", "label": "No consensus to compare with", "q": []})
            continue
        m = MAP[sig]
        q3 = m["cb"]
        if sig == "growth_pos" and infl_high:
            q3 += ". With inflation above target, good growth news can be read as hawkish"
        euro = (e.get("region", "") or "").upper() in ("EU", "EZ", "EA", "EUROZONE", "EURO AREA", "DE", "FR") or "ecb" in ev.lower()
        region = (e.get("region", "") or "US").upper()
        same_day = str(e.get("date", "")) == market_date
        if same_day and not euro and region not in ("US", "USA"):
            q4 = f"{region} event: check that market's bonds and currency (US and euro-area assets are what the map checks here)."
        elif same_day:
            mv = actual_moves(rows, euro)
            checks = [(k, m[k], mv[k]) for k in ("yields", "usd", "equities") if m[k] not in ("mixed", "flat") and mv[k]]
            hit = sum(1 for _, exp, got in checks if exp == got)
            q4 = f"{', '.join(mv['detail'])}. Matches the reaction map on {hit} of {len(checks)}." if checks else ", ".join(mv["detail"])
            if checks and hit < len(checks):
                q4 += " Ask why: another driver dominated, or the regime differs."
        else:
            q4 = "Released on another day: compare with that session's moves."
        unit = "%" if "%" in str(e.get("actual")) else ""
        out.append({
            "event": ev, "date": str(e.get("date", "")), "day": e.get("day", ""), "region": e.get("region", ""),
            "actual": str(e.get("actual")), "consensus": str(e.get("consensus", "") or "—"), "previous": str(e.get("previous", "") or "—"),
            "signal": sig, "label": LABEL[sig],
            "expected": {"yields": m["yields"], "usd": m["usd"], "equities": m["equities"], "outperform": m["outperform"]},
            "q": [
                f"{ev}: {e.get('actual')} vs {e.get('consensus')} expected" + (f" (surprise {diff:+.2f}{unit})" if diff else ""),
                LABEL[sig],
                q3,
                q4,
            ],
        })
    return out
