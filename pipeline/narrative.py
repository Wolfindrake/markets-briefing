"""The words on the dashboard.

Two layers:
  * auto()  — always available, built only from today's numbers and headlines (no AI, no guessing).
  * ai()    — optional, if ANTHROPIC_API_KEY is set: an AI writes the explanations (why it moved,
              plain-English analogies, Trump Impact) from the same numbers and headlines.
AI output is merged on top of auto(), field by field, and anything malformed is ignored.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date

import requests

from .compute import display, is_rate

log = logging.getLogger("narrative")

SHORT = {"spx": "S&P 500", "ixic": "Nasdaq", "dji": "Dow", "rut": "Russell 2000", "sx5e": "Euro Stoxx 50", "dax": "DAX",
         "cac": "CAC 40", "ibex": "IBEX 35", "n225": "Nikkei", "kospi": "KOSPI", "csi300": "CSI 300", "nifty": "Nifty 50",
         "us2": "US 2Y", "us10": "US 10Y", "us30": "US 30Y", "de10": "Germany 10Y", "fr10": "France 10Y", "jp10": "Japan 10Y",
         "brent": "Brent", "wti": "WTI", "xau": "Gold", "xag": "Silver", "btc": "Bitcoin", "ttf": "Dutch gas", "vix": "VIX", "move": "MOVE",
         "eurusd": "EUR/USD", "usdjpy": "USD/JPY", "usdchf": "USD/CHF", "ibx50": "Brazil 50",
         "msciw": "MSCI World", "mscieu": "MSCI Europe", "msciem": "MSCI EM", "ief": "IEF (7-10Y UST)", "frcds": "France CDS"}


GLOSSARY = [
    {"term": "Stock Index", "def": "A basket of company shares, like the S&P 500. Its level tells you how the whole basket is doing."},
    {"term": "Interest Rate", "def": "The price of borrowing money, set mainly by the central bank. Higher rate = more expensive to borrow."},
    {"term": "Bond Yield", "def": "The return for lending to a government. When yields rise, bond prices fall, and safe lending competes with stocks."},
    {"term": "Basis point (bp)", "def": "One hundredth of a percentage point. A yield going from 4.93% to 5.05% has risen 12 bp."},
    {"term": "Inflation", "def": "How fast everyday prices rise. High inflation is why central banks raise rates."},
    {"term": "Credit Spread", "def": "The extra yield a riskier borrower pays over a safer one (e.g. France over Germany). Wider = more perceived risk."},
    {"term": "Credit Default Swap (CDS)", "def": "Insurance against a borrower defaulting, quoted in bp per year. Higher = more worry."},
    {"term": "VIX / MOVE", "def": "Expected volatility of US stocks (VIX) and of US Treasury yields (MOVE): the markets' fear gauges."},
    {"term": "Market Breadth", "def": "How many stocks are actually rising, not just the index average. Compare the S&P 500 with its equal-weight version."},
    {"term": "Consensus", "def": "The forecast economists expect before a data release. Markets move on the gap between the actual number and the consensus."},
    {"term": "Hawkish / Dovish", "def": "Hawkish: leaning to higher rates to fight inflation. Dovish: leaning to lower rates to support growth and jobs."},
    {"term": "Real interest rate", "def": "The policy rate minus inflation. Only a clearly positive real rate is truly restrictive."},
    {"term": "Yield curve (2s10s)", "def": "The 10-year yield minus the 2-year. Steepening: the gap widens. Flattening: it narrows."},
    {"term": "Cap-weighted index", "def": "Bigger companies count for more. The S&P 500 is cap-weighted; the Dow is price-weighted."},
]


def _m(name, d, key, field="chg_pct"):
    return d.get(key, {}).get(field, "—")


def _nice_date(iso):
    d = date.fromisoformat(iso)
    return d.strftime("%B %-d, %Y")


def _dirn(row):
    if not row or row["chg"] is None:
        return "flat"
    if is_rate(row["unit"]):
        bp = row["chg"] * (100 if row["unit"] == "yield" else 1)
        return "up" if bp > 0.5 else "down" if bp < -0.5 else "flat"
    p = row["chg_pct"] or 0
    return "up" if p > 0.05 else "down" if p < -0.05 else "flat"


def _lvl(r) -> str:
    v, u = r["last"], r["unit"]
    if u == "yield":
        return f"{v:.2f}%"
    if u == "cds":
        return f"{v:.0f} bp"
    if u == "fx":
        return f"{v:.4f}" if v < 10 else f"{v:.2f}"
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}"


def _today(r) -> str:
    if r["chg"] is None:
        return "—"
    if is_rate(r["unit"]):
        bp = r["chg"] * (100 if r["unit"] == "yield" else 1)
        return "flat" if abs(bp) < 0.5 else f"{bp:+.0f} bp"
    return "flat" if r["chg_pct"] is None or abs(r["chg_pct"]) < 0.05 else f"{r['chg_pct']:+.1f}%"


def _week(r) -> str | None:
    w = (r.get("perf") or {}).get("week")
    if w is None:
        return None
    if is_rate(r["unit"]):
        return "flat" if abs(w) < 0.5 else f"{w:+.0f} bp"
    return "flat" if abs(w) < 0.05 else f"{w:+.1f}%"


def sheet_text(rows, headlines, tape_=None, surprises_=None) -> dict:
    """Sheet commentary in the professor's style: level, 'today and on the week', bp for rates."""
    R = {r["key"]: r for r in rows if r["last"] is not None}
    nm = lambda k: SHORT.get(k, R[k]["name"])  # noqa: E731

    def chg_to(keys):  # "S&P 500 -4.3% to 7,358, Nasdaq -5.5% to 24,315, Dow -3.4%"
        out = []
        for i, k in enumerate([k for k in keys if k in R]):
            out.append(f"{nm(k)} {_today(R[k])}" + (f" to {_lvl(R[k])}" if i < 2 else ""))
        return ", ".join(out)

    def tw(k, label=None, week=True):  # "US 2Y 4.46%, -12 bp today and -19 bp on the week"
        r = R[k]
        w = _week(r) if week else None
        return f"{label or nm(k)} {_lvl(r)}, {_today(r)} today" + (f" and {w} on the week" if w else "")

    def join(keys, week=True, labels=None):
        return ". ".join(tw(k, (labels or {}).get(k), week) for k in keys if k in R)

    eq = [x for x in (
        ("US: " + chg_to(["spx", "ixic", "dji", "rut"])) if "spx" in R else "",
        ("Europe: " + chg_to(["sx5e", "dax", "cac", "ibex"])) if "sx5e" in R else "",
        ("Asia: " + ", ".join(f"{nm(k)} {_today(R[k])}" for k in ("n225", "kospi", "csi300", "nifty") if k in R)) if any(k in R for k in ("n225", "kospi")) else "",
        ("On the week: " + ", ".join(f"{nm(k)} {_week(R[k])}" for k in ("spx", "ixic", "sx5e", "msciw") if k in R and _week(R[k]))) if "spx" in R and _week(R["spx"]) else "",
    ) if x]
    fi = [x for x in (
        join(["us2", "us10"], labels={"us10": "10Y"}),
        join(["us30"], labels={"us30": "30Y"}) + (f". MOVE {_lvl(R['move'])}, {_today(R['move'])} today" if "move" in R else ""),
        join(["de10", "fr10"]),
        join(["jp10", "frcds"], labels={"frcds": "France 5Y CDS"}),
    ) if x]
    ot = [x for x in (
        join(["brent", "wti"]),
        join(["xau", "xag"], labels={"xag": "Silver"}),
        ". ".join(f"{nm(k)} {_lvl(R[k])}, {_today(R[k])}" for k in ("eurusd", "usdjpy", "usdchf") if k in R),
        join(["btc", "ttf"], labels={"ttf": "European gas"}),
    ) if x]

    over = []
    if tape_:
        over.append(tape_["name"].split(":")[0] + ".")
    if "spx" in R:
        s = f"S&P 500 {_today(R['spx'])} to {_lvl(R['spx'])}"
        if "ixic" in R:
            s += f", Nasdaq {_today(R['ixic'])}"
        if "vix" in R and abs(R["vix"]["chg_pct"] or 0) >= 10:
            s += f", VIX {_today(R['vix'])} to {_lvl(R['vix'])}"
        over.append(s + ".")
    rates = [f"{lab} {_today(R[k])} to {_lvl(R[k])}" for k, lab in (("us2", "US 2Y"), ("us10", "10Y")) if k in R]
    if rates:
        over.append(" and ".join(rates) + ".")
    if "brent" in R and abs(R["brent"]["chg_pct"] or 0) >= 1.5:
        over.append(f"Brent {_today(R['brent'])} to {_lvl(R['brent'])}.")
    surp = [s for s in (surprises_ or []) if s.get("signal")]
    if surp:
        s = surp[0]
        over.append(f"{s['event']} {s['actual']} vs {s['consensus']} expected: {s['label'].lower()}.")

    hl = [f"{s['event']}: {s['actual']} vs {s['consensus']} expected (previous {s['previous']}). {s['label']}." for s in surp[:3]]
    hl += [f"{h['source']}: {h['headline']}" for h in headlines[: max(0, 7 - len(hl))]]
    return {"overview": " ".join(over), "highlights": hl, "performance": {"equities": eq, "fixed_income": fi, "others": ot}}


def auto(rows: list[dict], market_date: str, as_of: str, headlines: list[dict], week_ahead: list[dict],
         tape_: dict | None = None, surprises_: list[dict] | None = None) -> dict:
    R = {r["key"]: r for r in rows}
    D = {r["key"]: display(r) for r in rows}
    have = lambda k: k in R and R[k]["last"] is not None  # noqa: E731

    def line(keys, field="chg_pct", label=None):
        parts = []
        for k in keys:
            if have(k):
                parts.append(f"{label(k) if label else R[k]['name']} {D[k][field]} to {D[k]['last']}")
        return ", ".join(parts)

    short = SHORT
    nm = lambda k: short.get(k, R[k]["name"])  # noqa: E731

    items = []
    if have("spx"):
        items.append({"label": "Stocks", "direction": _dirn(R["spx"]),
                      "directionText": f"S&P 500 {D['spx']['chg_pct']}, Nasdaq {D.get('ixic', {}).get('chg_pct', '—')}",
                      "detail": line(["spx", "ixic", "dji", "rut"], label=nm) + ". " + line(["sx5e", "dax", "n225"], label=nm), "verified": True})
    if have("us10"):
        items.append({"label": "Interest Rates", "direction": _dirn(R["us10"]),
                      "directionText": f"US 10-year {D['us10']['chg']} to {D['us10']['last']}%",
                      "detail": "; ".join(f"{nm(k)} {D[k]['last']}% ({D[k]['chg']})" for k in ("us2", "us30", "de10", "fr10", "jp10") if have(k)),
                      "verified": True})
    if have("brent") or have("wti"):
        k = "brent" if have("brent") else "wti"
        items.append({"label": "Oil", "direction": _dirn(R[k]), "directionText": f"{nm(k)} {D[k]['chg_pct']} to ${D[k]['last']}",
                      "detail": line(["brent", "wti", "ttf"], label=nm), "verified": True})
    if have("xau"):
        items.append({"label": "Gold & Silver", "direction": _dirn(R["xau"]), "directionText": f"Gold {D['xau']['chg_pct']}",
                      "detail": line(["xau", "xag"], label=nm), "verified": True})
    if have("btc"):
        items.append({"label": "Bitcoin", "direction": _dirn(R["btc"]), "directionText": f"{D['btc']['chg_pct']} to ${D['btc']['last']}",
                      "detail": f"1 week {D['btc']['week']}, YTD {D['btc']['ytd']}", "verified": True})
    if have("vix"):
        items.append({"label": "Volatility", "direction": _dirn(R["vix"]), "directionText": f"VIX {D['vix']['last']} ({D['vix']['chg_pct']})",
                      "detail": f"MOVE {D['move']['last']} ({D['move']['chg_pct']})" if have("move") else "", "verified": True})

    # biggest movers (non-rate) for the explanation cards
    movers = sorted([r for r in rows if r["chg_pct"] is not None and not is_rate(r["unit"]) and r["key"] not in ("vix", "move")],
                    key=lambda r: abs(r["chg_pct"]), reverse=True)[:3]
    forces = []
    for r in movers:
        words = [w for w in re.split(r"\W+", nm(r["key"])) if len(w) > 2]
        rel = [h for h in headlines if any(w.lower() in h["headline"].lower() for w in words)][:1]
        forces.append({
            "title": f"{nm(r['key'])} {D[r['key']]['chg_pct']}",
            "analogy": "",
            "explanation": f"One of the day's biggest moves among the tracked markets: {nm(r['key'])} closed at {D[r['key']]['last']}"
                           f" ({D[r['key']]['chg_pct']}; 1 week {D[r['key']]['week']}, YTD {D[r['key']]['ytd']}).",
            "key": r["key"],
            "stats": [{"label": "Today", "value": D[r["key"]]["chg_pct"]}, {"label": "1 week", "value": D[r["key"]]["week"]},
                      {"label": "YTD", "value": D[r["key"]]["ytd"]}],
            "source": rel[0]["source"] + ": " + rel[0]["headline"] if rel else "Market data",
            "sourceUrl": rel[0]["url"] if rel else "",
            "whyItMatters": "Automatic summary from the numbers; switch on the AI commentary (README) for the why.",
        })

    def world(region, keys):
        ks = [k for k in keys if have(k)]
        if not ks:
            return None
        ups = sum(1 for k in ks if _dirn(R[k]) == "up")
        dirw = "Higher" if ups > len(ks) / 2 else "Lower" if ups < len(ks) / 2 else "Mixed"
        return {"region": region, "direction": dirw, "detail": " · ".join(f"{nm(k)} {D[k]['chg_pct']}" for k in ks), "note": ""}

    world_around = [w for w in (world("United States", ["spx", "ixic", "dji", "rut"]), world("Europe", ["sx5e", "dax", "cac", "ibex"]),
                                world("Asia", ["n225", "kospi", "csi300", "nifty"]), world("Commodities & Crypto", ["brent", "xau", "btc", "ttf"])) if w]
    big = []
    if have("spx"):
        big.append(f"US stocks {('rose' if _dirn(R['spx']) == 'up' else 'fell' if _dirn(R['spx']) == 'down' else 'were flat')}: "
                   f"S&P 500 {D['spx']['chg_pct']}, Nasdaq {D.get('ixic', {}).get('chg_pct', '—')}.")
    if have("us10"):
        big.append(f"The US 10-year yield moved {D['us10']['chg']} to {D['us10']['last']}%.")
    if have("brent"):
        big.append(f"Brent {D['brent']['chg_pct']} to ${D['brent']['last']}; gold {D.get('xau', {}).get('chg_pct', '—')}.")
    simple = {
        "bigPicture": " ".join(big),
        "chain": {"explanation": "The day's biggest moves, largest first.", "steps": [f"{nm(r['key'])} {D[r['key']]['chg_pct']}" for r in movers]},
        "driverNotes": {
            "equities": line(["spx", "ixic", "dji", "rut", "sx5e", "dax", "cac", "n225", "nifty"], label=nm) + ".",
            "fixedIncome": "; ".join(f"{nm(k)} {D[k]['last']}% ({D[k]['chg']}, 1 week {D[k]['week']})" for k in ("us2", "us10", "us30", "de10", "fr10", "jp10") if have(k)) + ".",
            "others": line(["brent", "wti", "xau", "xag", "btc", "ttf", "eurusd", "usdjpy"], label=nm) + ".",
        },
        "forces": forces,
        "keyNumbers": [{"label": short.get(k, k), "value": (D[k]["last"] + ("%" if is_rate(R[k]["unit"]) else "")), "verified": True}
                       for k in ("spx", "ixic", "us10", "us2", "brent", "xau", "btc") if have(k)],
        "whatToWatch": [{"title": f"{e.get('day', '')}: {e.get('event', '')}", "detail": e.get("note", "") or e.get("region", "")} for e in (week_ahead or [])[:4]],
        "worldAround": world_around,
        "glossary": GLOSSARY,
    }
    sheet = sheet_text(rows, headlines, tape_, surprises_)
    return {"overview": {"date": _nice_date(market_date), "asOf": as_of, "items": items}, "simple": simple, "sheet": sheet,
            "news": [{k: h[k] for k in ("headline", "dateISO", "source", "url", "blurb")} for h in headlines[:12]],
            "trump": None, "ai_used": False}


PROMPT = """You write the daily text of a personal markets-learning dashboard for an MBA student.
Use ONLY the numbers in TABLE and the facts in HEADLINES. Never invent figures, quotes or events. If a cause is not
supported by a headline, describe the move without a cause. Cite sources only from HEADLINES (use their exact url).
Rates: say "bp" for yield changes. Keep each string short and plain English.

Follow the course method (top-down, Prof. Dieguez M4S4):
 - Markets trade the surprise, not the level: lead with data releases as actual vs consensus (see SURPRISES).
 - Every headline reaches prices through expected cash flows, the discount rate, or both: say which.
 - Use the market reaction map (see TAPE): name today's pattern and say if yields, the dollar and equities
   behaved as expected; if not, say why (another driver, or the regime: with inflation above target, good growth
   news can be bad news for stocks).
 - The sheet is notes for a managing director: figures and how they compared with expectations, no teaching.
   Performance bullets in the style "US 2Y 4.46%, -12 bp today and -19 bp on the week".

Return ONE JSON object, no prose, with exactly these keys:
{{
 "overview_items": [ {{"label": "Stocks|Interest Rates|Oil|...", "direction": "up|down|flat", "directionText": "...", "detail": "..."}} ],   // 5-6 items
 "simple": {{
   "bigPicture": "3-4 sentences",
   "chain": {{"explanation": "one sentence", "steps": ["3-5 short steps, cause to effect"]}},
   "driverNotes": {{"equities": "What happened, why (cited), impact", "fixedIncome": "...", "others": "..."}},
   "forces": [ {{"title": "Why ...", "analogy": "everyday analogy", "explanation": "...", "key": "short-id",
                "stats": [{{"label": "...", "value": "..."}}], "source": "Publisher: headline", "sourceUrl": "url from HEADLINES",
                "whyItMatters": "..."}} ],   // exactly 3
   "whatToWatch": [ {{"title": "...", "detail": "..."}} ],   // 3-4, only from WEEK AHEAD or HEADLINES
   "worldAround": [ {{"region": "United States|Europe|Asia|Commodities & Crypto", "direction": "...", "detail": "...", "note": "..."}} ]
 }},
 "sheet": {{"overview": "2-3 sentences for a managing director", "highlights": ["5-7 bullets: data vs expectations, central banks, earnings, geopolitics"],
           "performance": {{"equities": ["2-3 bullets"], "fixed_income": ["2-3 bullets"], "others": ["2-3 bullets"]}}}},
 "trump": {{"summaryBullets": ["2-4 bullets on Trump-related policy news and the market reaction, only if in HEADLINES"],
           "weeklySummary": "2-3 sentences or empty",
           "majorMoves": [ {{"id": "slug", "title": "...", "dateRange": "...", "background": "...",
                            "impact": {{"equities": "...", "bonds": "...", "commodities": "...", "crypto": "...", "defense": "..."}},
                            "why": "...", "winners": ["..."], "losers": ["..."], "source": {{"name": "...", "url": "..."}}}} ],   // 0-2
           "forwardLook": [ {{"date": "...", "title": "...", "text": "..."}} ],
           "scenarios": [ {{"label": "...", "text": "..."}} ]}}
}}

MARKET DATE: {date}
TABLE (name | last | change | change % | 1 week | YTD):
{table}

WEEK AHEAD:
{week}

TAPE (today's pattern on the reaction map):
{tape}

SURPRISES (released data, actual vs consensus, the four questions):
{surprises}

MACRO DASHBOARD:
{macro}

HEADLINES (source | headline | summary | url):
{heads}
"""


def _json_from(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1]) if start >= 0 else None


def ai(rows, market_date, headlines, week_ahead, cfg, tape_=None, surprises_=None, macro_=None) -> dict | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    acfg = (cfg or {}).get("ai") or {}
    if not key or not acfg.get("enabled", True):
        return None
    tape_txt = "(none)"
    if tape_:
        tape_txt = f"{tape_['name']}. Map: {tape_['map']} Checks: " + "; ".join(
            f"{c['asset']} expected {c['expected']}, actual {c['actual']} ({c['value']})" for c in tape_["checks"]) + (f". {tape_['curve']}" if tape_.get("curve") else "")
    surp_txt = "\n".join(" | ".join(s.get("q", [])) for s in (surprises_ or [])) or "(none entered)"
    macro_txt = "\n".join(f"{i['name']}: {i['latest']}" for i in ((macro_ or {}).get("indicators") or [])) or "(not available)"
    table = "\n".join(f"{d['name']} | {d['last']} | {d['chg']} | {d['chg_pct']} | {d['week']} | {d['ytd']}" for d in (display(r) for r in rows))
    heads = "\n".join(f"{h['source']} | {h['headline']} | {h.get('blurb', '')[:200]} | {h['url']}" for h in headlines[: acfg.get("max_headlines", 40)])
    week = "\n".join(f"{e.get('day', '')} | {e.get('region', '')} | {e.get('event', '')}" for e in week_ahead or []) or "(none provided)"
    body = {"model": acfg.get("model", "claude-sonnet-5-5"), "max_tokens": 6000,
            "messages": [{"role": "user", "content": PROMPT.format(date=market_date, table=table, week=week, heads=heads or "(none)",
                                                                                  tape=tape_txt, surprises=surp_txt, macro=macro_txt)}]}
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", json=body, timeout=180,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        out = _json_from(text)
        return out if isinstance(out, dict) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("AI narrative failed, using automatic text: %s", exc)
        return None


def merge(base: dict, extra: dict | None, allowed_urls: set[str]) -> dict:
    """Overlay AI output on the automatic text, keeping only well-formed pieces and known source URLs."""
    if not extra:
        return base
    out = dict(base)
    ok_str = lambda x: isinstance(x, str) and x.strip() != ""  # noqa: E731

    items = extra.get("overview_items")
    if isinstance(items, list) and items and all(isinstance(i, dict) and ok_str(i.get("label")) for i in items):
        out["overview"] = {**base["overview"], "items": [{"label": i["label"], "direction": i.get("direction") if i.get("direction") in ("up", "down", "flat") else "flat",
                                                           "directionText": str(i.get("directionText", "")), "detail": str(i.get("detail", "")), "verified": True} for i in items[:6]]}
    s = extra.get("simple")
    if isinstance(s, dict):
        simple = dict(base["simple"])
        if ok_str(s.get("bigPicture")):
            simple["bigPicture"] = s["bigPicture"]
        ch = s.get("chain")
        if isinstance(ch, dict) and isinstance(ch.get("steps"), list) and ch["steps"]:
            simple["chain"] = {"explanation": str(ch.get("explanation", "")), "steps": [str(x) for x in ch["steps"][:6]]}
        dn = s.get("driverNotes")
        if isinstance(dn, dict):
            simple["driverNotes"] = {k: (dn.get(k) if ok_str(dn.get(k)) else base["simple"]["driverNotes"].get(k, "")) for k in ("equities", "fixedIncome", "others")}
        fs = s.get("forces")
        if isinstance(fs, list) and fs:
            clean = []
            for f in fs[:3]:
                if not isinstance(f, dict) or not ok_str(f.get("title")):
                    continue
                url = f.get("sourceUrl", "")
                clean.append({"title": f["title"], "analogy": str(f.get("analogy", "")), "explanation": str(f.get("explanation", "")),
                              "key": str(f.get("key", "")), "stats": [st for st in f.get("stats", []) if isinstance(st, dict)][:3],
                              "source": str(f.get("source", "")), "sourceUrl": url if url in allowed_urls else "",
                              "whyItMatters": str(f.get("whyItMatters", ""))})
            if clean:
                simple["forces"] = clean
        for k in ("whatToWatch", "worldAround"):
            if isinstance(s.get(k), list) and s[k]:
                simple[k] = [x for x in s[k] if isinstance(x, dict)][:4]
        out["simple"] = simple
    sh = extra.get("sheet")
    if isinstance(sh, dict) and ok_str(sh.get("overview")):
        perf = sh.get("performance") if isinstance(sh.get("performance"), dict) else {}
        out["sheet"] = {"overview": sh["overview"], "highlights": [str(x) for x in sh.get("highlights", []) if ok_str(x)][:8] or base["sheet"]["highlights"],
                        "performance": {k: [str(x) for x in perf.get(k, []) if ok_str(x)][:4] or base["sheet"]["performance"].get(k, []) for k in ("equities", "fixed_income", "others")}}
    t = extra.get("trump")
    if isinstance(t, dict) and (t.get("summaryBullets") or t.get("majorMoves")):
        for m in t.get("majorMoves", []) or []:
            if isinstance(m, dict) and isinstance(m.get("source"), dict) and m["source"].get("url") not in allowed_urls:
                m["source"]["url"] = ""
        out["trump"] = t
    out["ai_used"] = True
    return out
