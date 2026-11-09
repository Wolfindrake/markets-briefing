"""'Why it moved', in plain words, one block per asset class.

Each block answers the questions Shiv asks his tutor: what happened, why, what it affects, what to retain, and a
question to test yourself. Two kinds of reasons are kept apart:
  * "data"    - shown by today's numbers or by a headline in our sources (Bloomberg, FT), with the evidence listed;
  * "pattern" - how this usually works (the textbook link), clearly labelled as the usual pattern, not today's proof.
No cause is invented: if there is no evidence, the block says so and gives the usual drivers instead.
"""
from __future__ import annotations

import re
from datetime import date

from .story import NAME, context, day, fmt, lvl, rank, wk, ev_parts, REGION

SECTORS = {"xlk": "Technology", "xlf": "Financials", "xle": "Energy", "xlv": "Health care", "xlu": "Utilities",
           "xli": "Industrials", "xly": "Consumer discretionary", "xlp": "Consumer staples", "xlb": "Materials",
           "xlre": "Real estate", "xlc": "Communication services"}
OIL = r"(?<!olive )(?<!palm )\b(oil|crude|brent|wti|opec\+?|barrels?|hormuz)\b"
DEFENSIVE = {"xlu", "xlp", "xlv", "xlre"}
GROWTH = {"xlk", "xly", "xlc"}


def _p(v, dp=1):
    return f"{abs(v):.{dp}f}%"


def _evidence(headlines, pattern, n=2):
    out = []
    for h in headlines or []:
        if re.search(pattern, h["headline"], re.I):
            out.append({"text": h["headline"], "source": h.get("source", ""), "url": h.get("url", "")})
            if len(out) >= n:
                break
    return out


def _prev_day(S, key, market_date):
    """The change on the session BEFORE the market date (Asia trades first, so it reacts to that one)."""
    s = [p for p in (S.get(key) or []) if p["date"] < market_date]
    if len(s) < 2 or not s[-2]["close"]:
        return None, None
    return (s[-1]["close"] / s[-2]["close"] - 1) * 100, s[-1]["date"]


def _top_surprise(surprises_, md):
    s = sorted([x for x in surprises_ or [] if x.get("signal") and x["signal"] != "inline"], key=lambda x: -rank(x, md))
    return s[0] if s else None


def _surprise_text(s):
    n, per, _ = ev_parts(s["event"])
    reg = REGION.get(str(s.get("region", "")).upper(), s.get("region", ""))
    return f"{reg} {n} came in at {s['actual']}{per} against {s['consensus']} expected"


# ------------------------------------------------------------------ the blocks
def rates(R, S, top, fed, heads, md):
    if "us10" not in R:
        return None
    r10, r2 = R["us10"], R.get("us2")
    d10, d2 = day(r10), day(r2) if r2 else None
    w10 = wk(r10)
    verb = "barely moved" if abs(d10) < 1.5 else ("edged up" if d10 > 0 else "edged down") if abs(d10) < 3 else ("rose" if d10 > 0 else "fell")
    why, kind = [], "pattern"
    if top and str(top.get("region", "")).upper() in ("US", ""):
        kind = "data"
        hot = top["signal"] in ("hawkish", "growth_pos")
        why.append(f"{_surprise_text(top)}. " + (
            "Numbers that strong tell the Fed the economy can take higher rates, and they can keep inflation sticky, "
            "so a rate cut gets less likely and a hike more likely." if hot else
            "Weaker numbers give the Fed room to be gentler, so traders price fewer hikes or more cuts."))
        if fed and fed.get("meeting"):
            m = date.fromisoformat(fed["meeting"])
            mv = "hike" if fed["hike"] >= fed["cut"] else "cut"
            pr = fed["hike"] if mv == "hike" else fed["cut"]
            ch = fed.get("change_pp")
            why.append(f"Traders now price a {pr}% chance of a {mv} on {m.day} {m:%B}" +
                       (f", {'up' if ch > 0 else 'down'} {abs(ch):.0f} points in a day." if ch is not None and abs(ch) >= 3 else "."))
        if hot and abs(d10) < 3 and w10 is not None and w10 < -3:
            b = R.get("brent")
            extra = f", and oil's slide (Brent {fmt(wk(b), b)} on the week) eases inflation worries" if b and wk(b) is not None and wk(b) <= -3 else ""
            why.append(f"Yet the 10-year moved only {fmt(d10, r10)}. One likely reason: yields had already fallen this week "
                       f"({fmt(w10, r10)}){extra}, which pulls the other way.")
    if d2 is not None:
        if abs(d2) > abs(d10) + 1:
            why.append(f"The 2-year ({fmt(d2, r2)}) moved more than the 10-year ({fmt(d10, r10)}). The 2-year follows what the Fed "
                       "will do over the next two years; the 10-year mixes in long-term growth, inflation and government borrowing. "
                       "So this was mainly a 'what will the Fed do' move.")
        elif abs(d10) > abs(d2) + 1:
            why.append(f"The 10-year ({fmt(d10, r10)}) moved more than the 2-year ({fmt(d2, r2)}): the worry is long-term "
                       "(inflation, growth, how much the government borrows), not the next Fed meeting.")
    if "fr10" in R and "de10" in R:
        sp = (R["fr10"]["last"] - R["de10"]["last"]) * 100
        ws = (wk(R["fr10"]) - wk(R["de10"])) if wk(R["fr10"]) is not None and wk(R["de10"]) is not None else None
        why.append(f"In Europe, France pays {sp:.0f} bp more than Germany to borrow for 10 years" +
                   (f", {abs(ws):.0f} bp {'more' if ws > 0 else 'less'} than a week ago" if ws is not None and abs(ws) >= 3 else "") +
                   ". That gap is the market's price for French debt risk.")
    if not why:
        why.append("No single data release explains it in our sources. Yields usually move on inflation and jobs data, "
                   "central-bank speeches, and how much debt governments sell.")
    dxy = R.get("dxy")
    return {
        "key": "rates", "title": "Interest rates & bonds", "kind": kind,
        "headline": f"US yields {verb}: 10-year {lvl(r10)}" + (f", 2-year {lvl(r2)}" if r2 else ""),
        "what": f"US 10Y {lvl(r10)} ({fmt(d10, r10)} today" + (f", {fmt(w10, r10)} on the week" if w10 is not None else "") + ")" +
                (f"; 2Y {lvl(r2)} ({fmt(d2, r2)})" if r2 else "") + ".",
        "why": why,
        "affects": [
            "Dollar: higher US yields usually pull money into dollars" + (f" (dollar index {fmt(day(dxy), dxy)} today)." if dxy else "."),
            "Growth stocks: most of their profits are far in the future, so higher rates hurt them most, like long bonds.",
            "Gold: it pays no interest, so it loses appeal when yields rise.",
            "Borrowers: mortgages and company loans are priced off these yields.",
        ],
        "retain": "The 2-year listens to the Fed. The 10-year listens to growth, inflation and how much the government borrows.",
        "ask": ("Strong data pushed hike odds up, yet the 10-year barely moved. What else was pulling yields down this week?"
                if top and abs(d10) < 3 else "If the 2-year rises more than the 10-year, what is the market telling you about the Fed?"),
        "evidence": _evidence(heads, r"\b(treasur\w*|yields?|bonds?|gilts?|bunds?|fed|fomc|powell|warsh|ecb|lagarde|boj|"
                                     r"rate (cut|hike|decision)s?|interest rates?|inflation|jobs|payrolls?)\b"),
    }


def equities(R, S, top, fed, heads, md):
    if "spx" not in R:
        return None
    sp, nq = day(R["spx"]), day(R["ixic"]) if "ixic" in R else None
    why, affects, kind = [], [], "pattern"
    up = sp > 0.15
    why.append("Stocks weigh two things: company profits (the cash flows) and interest rates (the discount rate that "
               "turns future profits into today's price).")
    if top and top["signal"] in ("hawkish", "growth_pos"):
        kind = "data"
        why.append(f"{_surprise_text(top)}: good for profits, bad for rates. Today the " +
                   ("profit side won: stocks rose even as rate-hike odds went up." if up else
                    "rate side won: stocks fell as investors priced a tougher Fed." if sp < -0.15 else
                    "two sides cancelled out: the index barely moved."))
    elif top and top["signal"] in ("dovish", "growth_neg"):
        kind = "data"
        why.append(f"{_surprise_text(top)}: weaker growth hurts profits but lowers rates. Stocks " +
                   ("rose: the lower-rate side won." if up else "fell: the profit worry won." if sp < -0.15 else "were flat."))
    sox = R.get("sox")
    if sox and day(sox) is not None and abs(day(sox)) >= 1.5:
        kind = "data"
        s = f"Chip stocks led (Philadelphia Semiconductor index {fmt(day(sox), sox)})"
        if wk(sox) is not None and wk(sox) * day(sox) < 0 and abs(wk(sox)) >= 2:
            s += (f", a bounce, though they are still {fmt(wk(sox), sox)} on the week" if day(sox) > 0 else
                  f", giving back part of a {fmt(wk(sox), sox)} week")
        why.append(s + ". Chips are the heart of the AI trade, so they swing the most when confidence in AI spending changes.")
    elif nq is not None and nq - sp >= 0.6:
        why.append(f"Tech led: Nasdaq {fmt(nq, R['ixic'])} against {fmt(sp, R['spx'])} for the S&P 500.")
    rsp = R.get("rsp")
    if rsp and day(rsp) is not None and abs(day(rsp) - sp) >= 0.5:
        kind = "data"
        if (day(rsp) < 0) != (sp < 0) or abs(day(rsp)) < abs(sp):
            why.append(f"But it was narrow: the average stock (equal-weighted S&P 500 {fmt(day(rsp), rsp)}) did worse than the index "
                       f"({fmt(sp, R['spx'])}). In a cap-weighted index the giants are most of the pizza, so a few big names can lift the "
                       "whole index while most stocks fall.")
            affects.append("A narrow, mega-cap rally is fragile: watch whether more stocks join in before trusting it.")
        else:
            why.append(f"And it was broad: the average stock ({fmt(day(rsp), rsp)}) beat the index ({fmt(sp, R['spx'])}).")
    secs = [(k, day(R[k])) for k in SECTORS if k in R and day(R[k]) is not None]
    if len(secs) >= 6:
        secs.sort(key=lambda x: -x[1])
        best, worst = secs[:2], secs[-2:]
        tilt = ("toward defensive sectors (people want safety)" if {best[0][0], best[1][0]} & DEFENSIVE == {best[0][0], best[1][0]} else
                "toward growth sectors (people want upside)" if {best[0][0], best[1][0]} <= GROWTH else "")
        why.append("Sectors: best " + ", ".join(f"{SECTORS[k]} {fmt(v, R[k])}" for k, v in best) + "; worst " +
                   ", ".join(f"{SECTORS[k]} {fmt(v, R[k])}" for k, v in worst) + (f". Money moved {tilt}." if tilt else "."))
    eu = [k for k in ("dax", "sx5e", "cac") if k in R and day(R[k]) is not None]
    if eu and up and all(day(R[k]) < 0 for k in eu):
        why.append(f"Europe fell ({', '.join(f'{NAME[k]} {fmt(day(R[k]), R[k])}' for k in eu[:2])}) while the US rose. Europe closes at "
                   "17:30 Madrid time, before most of the US session, so it missed the US recovery.")
    asia = sorted([k for k in ("n225", "kospi", "csi300", "nifty") if k in R and day(R[k]) is not None], key=lambda k: -abs(day(R[k])))
    if asia and abs(day(R[asia[0]])) >= 2:
        a = asia[0]
        prev, pd = _prev_day(S, "ixic", md)
        s = f"{NAME[a]} {fmt(day(R[a]), R[a])}" + (f" and {NAME[asia[1]]} {fmt(day(R[asia[1]]), R[asia[1]])}" if len(asia) > 1 and abs(day(R[asia[1]])) >= 2 else "")
        if prev is not None and abs(prev) >= 1 and (prev < 0) == (day(R[a]) < 0):
            kind = "data"
            why.append(f"Asia: {s}. Asia trades first, so its session reflects the US session before it: on {date.fromisoformat(pd):%A} "
                       f"the Nasdaq moved {fmt(prev, R['ixic'])}. Korea and Japan are full of chip makers, so an AI sell-off hits them hard.")
        else:
            why.append(f"Asia: {s}. Asia trades before the US, so it often reacts to the previous US session or to local news.")
    affects += [
        "Lords of Finance: the S&P 500 call depends on whether profits or rates win the tug of war this week.",
        "Volatility: big index swings feed the VIX; calm days bring it down.",
    ]
    lead = "rose" if up else "fell" if sp < -0.15 else "were flat"
    return {
        "key": "equities", "title": "Stocks", "kind": kind,
        "headline": f"US stocks {lead}" + (", led by chips" if sox and day(sox) is not None and day(sox) >= 1.5 and up else
                                          ", led by tech" if nq is not None and nq - sp >= 0.6 else "") +
                    (f"; {NAME[asia[0]]} {fmt(day(R[asia[0]]), R[asia[0]])}" if asia and abs(day(R[asia[0]])) >= 3 else ""),
        "what": f"S&P 500 {fmt(sp, R['spx'])} to {lvl(R['spx'])}" + (f", Nasdaq {fmt(nq, R['ixic'])}" if nq is not None else "") +
                (f", Dow {fmt(day(R['dji']), R['dji'])}" if "dji" in R else "") +
                (f". On the week the S&P 500 is {fmt(wk(R['spx']), R['spx'])}" if wk(R["spx"]) is not None else "") + ".",
        "why": why,
        "affects": affects,
        "retain": "Short term, stocks move on headlines and rates. Long term, they follow profits. Good economic news helps "
                  "profits but can hurt through higher rates: which side wins depends on inflation.",
        "ask": ("Why can the S&P 500 rise on a day when the average stock falls?" if rsp and day(rsp) is not None and day(rsp) < sp - 0.5
                else "Strong data raised the odds of a rate hike. Why did stocks still rise?" if up and top and top["signal"] in ("hawkish", "growth_pos")
                else "Was today's move about profits or about interest rates? What would tell you?"),
        "evidence": _evidence(heads, r"\b(stocks?|shares|equit|s&p|nasdaq|dow|nvidia|ai\b|chip|semiconductor|earnings|tech|kospi|nikkei|dax)"),
    }


def commodities(R, S, top, fed, heads, md):
    b, g = R.get("brent"), R.get("xau")
    if not b and not g:
        return None
    why, kind, parts = [], "pattern", []
    if b:
        pri, c = context(b, S.get("brent"))
        parts.append(f"Brent {lvl(b)} ({fmt(day(b), b)} today, {fmt(wk(b), b)} on the week)")
        ev = _evidence(heads, OIL, 2)
        s = "Oil is set by supply and demand, plus geopolitics (Middle East, OPEC, Russia)."
        if wk(b) is not None and abs(wk(b)) >= 4:
            s += f" Brent {'fell' if wk(b) < 0 else 'rose'} {_p(wk(b))} this week" + (f", {c}" if pri >= 3 else "") + "."
        why.append(s)
        if ev:
            kind = "data"
            why.append("Our sources link it to: " + " / ".join(f"“{e['text']}” ({'FT' if e['source'] == 'Financial Times' else e['source']})" for e in ev) + ".")
        else:
            why.append("No single oil headline in our sources today; the usual causes are supply news (OPEC, the Middle East) or a weaker demand outlook.")
    t = R.get("ttf")
    if t and wk(t) is not None and abs(wk(t)) >= 4:
        why.append(f"European gas {lvl(t)}, {fmt(wk(t), t)} on the week: Europe's gas price swings with weather, storage levels and LNG shipments.")
    if g:
        parts.append(f"gold {lvl(g)} ({fmt(day(g), g)})")
        dxy, r10 = R.get("dxy"), R.get("us10")
        dd, dy = (day(dxy) if dxy else None), (day(r10) if r10 else None)
        if day(g) is not None and dd is not None and dy is not None:
            kind = "data" if kind == "pattern" else kind
            if day(g) < 0 and (dd > 0.1 or dy > 1):
                why.append(f"Gold fell as the dollar ({fmt(dd, dxy)}) and US yields ({fmt(dy, r10)}) rose. Gold pays no interest, so higher "
                           "yields make it less attractive, and a stronger dollar makes it dearer for buyers outside the US.")
            elif day(g) > 0 and (dd > 0.1 or dy > 1):
                why.append(f"Gold rose even though the dollar and yields went up: a sign of safe-haven buying (people paying for protection).")
            elif day(g) > 0:
                why.append(f"Gold rose with a softer dollar ({fmt(dd, dxy)}) and steady yields: the usual pattern.")
            else:
                why.append("Gold fell even with a softer dollar: other forces (selling after a big run, less fear) dominated.")
    e = R.get("xle")
    affects = ["Cheaper oil lowers inflation expectations, which eases pressure on the Fed; dearer oil does the opposite."]
    affects.append("Airlines and transport gain from cheap fuel; energy producers lose" + (f" (Energy sector {fmt(day(e), e)} today)." if e and day(e) is not None else "."))
    affects.append("Oil exporters' currencies (Canada, Norway) and oil-importing emerging markets feel it too.")
    affects.append("Gold up usually means fear or falling real interest rates; gold down means calm or rising real rates.")
    return {
        "key": "commodities", "title": "Oil, gas & gold", "kind": kind,
        "headline": (f"Oil {'fell' if wk(b) < 0 else 'rose'} {_p(wk(b))} on the week" if b and wk(b) is not None and abs(wk(b)) >= 3 else
                     f"Oil {fmt(day(b), b)}" if b else "") + (f"; gold {fmt(day(g), g)}" if g else ""),
        "what": "; ".join(parts) + ".",
        "why": why,
        "affects": affects,
        "retain": "Oil is about supply, demand and geopolitics. Gold is about real interest rates, the dollar and fear.",
        "ask": f"Oil {'fell' if b and (wk(b) or 0) < 0 else 'moved'} {_p(wk(b)) if b and wk(b) is not None else ''} this week. Who wins and who loses?",
        "evidence": _evidence(heads, OIL + r"|\b(lng|natural gas|gold|bullion|copper|commodit)"),
    }


def currencies(R, S, top, fed, heads, md):
    e, j, dxy = R.get("eurusd"), R.get("usdjpy"), R.get("dxy")
    if not e and not dxy:
        return None
    why, kind = [], "pattern"
    us2, de = R.get("us2"), R.get("de10")
    if dxy and us2 and de and day(dxy) is not None:
        kind = "data"
        gap = day(us2) - day(de)
        if abs(gap) >= 1.5:
            why.append(f"US 2-year yields moved {fmt(day(us2), us2)} against {fmt(day(de), de)} for Germany. Money tends to flow to where it "
                       f"earns more, so a wider US advantage usually supports the dollar" +
                       (f", and the dollar index did rise ({fmt(day(dxy), dxy)})." if (gap > 0) == (day(dxy) > 0) else
                        f", yet the dollar index moved {fmt(day(dxy), dxy)}: other forces (risk appetite, positioning) won today."))
        else:
            why.append(f"The dollar index moved {fmt(day(dxy), dxy)}; the gap between US and German yields barely changed, so rates were not the driver today.")
    if e and wk(e, "ytd") is not None:
        why.append(f"EUR/USD {lvl(e)}: the euro is {fmt(wk(e, 'ytd'), e)} this year. A Fed that may still hike, against an ECB on hold, keeps the dollar supported.")
    if j and j["last"] >= 150:
        why.append(f"USD/JPY {lvl(j)}: the wide gap between US and Japanese interest rates keeps the yen weak. Japan's finance ministry has stepped in "
                   "before when it fell near 160 per dollar, so traders watch that level.")
    return {
        "key": "fx", "title": "Currencies", "kind": kind,
        "headline": (f"Dollar {'firmer' if day(dxy) > 0.1 else 'softer' if day(dxy) < -0.1 else 'steady'}" if dxy and day(dxy) is not None else "Currencies") +
                    (f"; EUR/USD {lvl(e)}" if e else ""),
        "what": "; ".join(x for x in (f"Dollar index {lvl(dxy)} ({fmt(day(dxy), dxy)})" if dxy else "",
                                       f"EUR/USD {lvl(e)} ({fmt(wk(e), e)} on the week)" if e and wk(e) is not None else "",
                                       f"USD/JPY {lvl(j)}" if j else "") if x) + ".",
        "why": why,
        "affects": ["A stronger dollar weighs on gold and on commodities priced in dollars.",
                    "Emerging markets that borrow in dollars get squeezed when the dollar rises.",
                    "A weaker euro helps European exporters (cars, luxury, machinery) sell abroad."],
        "retain": "Currencies follow interest-rate gaps (money goes where it earns more) and risk appetite (in fear, money runs to the dollar, yen and Swiss franc).",
        "ask": "If the Fed hikes in December and the ECB stays on hold, what should happen to EUR/USD, and why?",
        "evidence": _evidence(heads, r"\b(dollar|euro|yen|currenc|fx\b|forex|ecb|boj)"),
    }


def crypto(R, S, top, fed, heads, md):
    b = R.get("btc")
    if not b or day(b) is None:
        return None
    nq = day(R["ixic"]) if "ixic" in R else None
    why = ["Bitcoin usually trades like a high-risk tech stock: it does well when money is cheap and investors want risk."]
    kind = "pattern"
    if nq is not None and (day(b) < -0.5) != (nq < -0.5) and abs(day(b) - nq) >= 1.5:
        kind = "data"
        why.append(f"Today it moved {fmt(day(b), b)} while the Nasdaq moved {fmt(nq, R['ixic'])}, so the move was crypto-specific rather than general risk appetite.")
    ev = _evidence(heads, r"\b(bitcoin|crypto|coinbase|stablecoin|ether|blockchain|nubank|mercado pago)")
    if ev:
        kind = "data"
        why.append("Our sources mention: " + " / ".join(f"“{e['text']}”" for e in ev) + ".")
    return {
        "key": "crypto", "title": "Crypto", "kind": kind,
        "headline": f"Bitcoin {fmt(day(b), b)} to {lvl(b)}",
        "what": f"Bitcoin {lvl(b)} ({fmt(day(b), b)} today, {fmt(wk(b), b)} on the week, {fmt(wk(b, 'ytd'), b)} this year).",
        "why": why,
        "affects": ["Crypto-linked stocks (Coinbase, miners) move with it.", "A falling bitcoin while tech rises is a warning sign about speculative appetite."],
        "retain": "Bitcoin behaves like a high-beta tech asset: it needs cheap money and appetite for risk.",
        "ask": "Bitcoin fell while the Nasdaq rose. What does that tell you about where risk appetite is going?",
        "evidence": ev,
    }


def fear(R, S, top, fed, heads, md):
    v, m = R.get("vix"), R.get("move")
    if not v:
        return None
    why = [f"The VIX measures how big investors expect S&P 500 swings to be over the next 30 days. Below 15 is calm, 15 to 20 normal, "
           f"20 to 30 stressed, above 30 panic. It is at {lvl(v)}."]
    if day(v) is not None and wk(v) is not None and day(v) * wk(v) < 0 and abs(wk(v)) >= 10:
        why.append(f"It fell {_p(day(v))} today as stocks recovered, but it is still {fmt(wk(v), v)} on the week: investors are still paying up for protection."
                   if day(v) < 0 else f"It jumped {_p(day(v))} today after a calmer week ({fmt(wk(v), v)}).")
    if m:
        why.append(f"The MOVE index ({lvl(m)}, {fmt(day(m), m)}) is the same idea for US Treasury yields.")
    return {
        "key": "fear", "title": "Fear gauges", "kind": "data",
        "headline": f"VIX {lvl(v)} ({fmt(day(v), v)})",
        "what": f"VIX {lvl(v)} ({fmt(day(v), v)} today, {fmt(wk(v), v)} on the week)" + (f"; MOVE {lvl(m)}" if m else "") + ".",
        "why": why,
        "affects": ["High fear pushes money into Treasuries, gold, the yen and the Swiss franc.", "Options (insurance) get pricier, and funds that target a set risk level sell stocks."],
        "retain": "VIX is the fear gauge for stocks, MOVE for bonds. Fear spikes fast and fades slowly.",
        "ask": "Stocks rose today, but the VIX is still above 20. What does that tell you about how investors feel?",
        "evidence": [],
    }


# ------------------------------------------------------------------ the big chain and the teaching map
def chain(R, top, fed):
    steps = []
    if top:
        n, per, _ = ev_parts(top["event"])
        steps.append(f"{n} {top['actual']}{per} vs {top['consensus']} expected")
    if fed and fed.get("hike", 0) >= 10:
        steps.append(f"Hike odds {fed['hike']}%" + (f" ({fed['change_pp']:+.0f} pts)" if fed.get("change_pp") is not None else ""))
    if "us2" in R:
        steps.append(f"US 2Y {fmt(day(R['us2']), R['us2'])}")
    if "dxy" in R and day(R["dxy"]) is not None:
        steps.append(f"Dollar {fmt(day(R['dxy']), R['dxy'])}")
    if "xau" in R:
        steps.append(f"Gold {fmt(day(R['xau']), R['xau'])}")
    if "spx" in R:
        steps.append(f"S&P 500 {fmt(day(R['spx']), R['spx'])}" + (f", Nasdaq {fmt(day(R['ixic']), R['ixic'])}" if "ixic" in R else ""))
    return steps


LINKS = [
    {"cause": "Interest rates go up", "effects": ["Bond prices fall", "Growth stocks fall most", "Dollar rises", "Gold falls", "Mortgages and loans get dearer"],
     "because": "Money today becomes worth more than money tomorrow, so anything that pays far in the future (growth stocks, long bonds) is worth less now."},
    {"cause": "Inflation comes in hot", "effects": ["Central bank likely hikes or delays cuts", "Short-term yields rise", "Stocks wobble"],
     "because": "Central banks fight inflation with higher rates, and markets price that before it happens."},
    {"cause": "Strong growth data (jobs, GDP)", "effects": ["Good for profits", "But rates may rise", "Winner depends on inflation"],
     "because": "With inflation calm, good news is good news. With inflation above target, good news can be bad news for stocks."},
    {"cause": "Oil goes up", "effects": ["Inflation expectations rise", "Energy stocks rise", "Airlines and consumers suffer", "Importers' currencies weaken"],
     "because": "Oil feeds into transport, plastics and electricity: one company's revenue is another's cost."},
    {"cause": "Dollar goes up", "effects": ["Commodities fall (priced in dollars)", "Emerging markets squeezed", "US multinationals earn less abroad"],
     "because": "Everything priced in dollars gets dearer for the rest of the world, and dollar debts get heavier."},
    {"cause": "Fear rises (VIX up)", "effects": ["Stocks fall", "Treasuries, gold, yen and Swiss franc rise", "Credit spreads widen"],
     "because": "In a scare, investors sell what is risky and buy what is safe: a flight to quality."},
    {"cause": "Government borrows more (deficits)", "effects": ["Long-term yields rise", "Country spreads widen (e.g. France vs Germany)"],
     "because": "More bonds to sell means buyers demand a higher return, and lenders charge more for perceived risk."},
    {"cause": "AI and big-tech news", "effects": ["Chip stocks and the Nasdaq swing most", "Korea and Taiwan follow", "The S&P 500 follows the giants"],
     "because": "A handful of tech giants are close to half of the S&P 500 'pizza', and chip makers dominate Asian indices."},
]


def build(rows, series, surprises_, fed, headlines, market_date) -> dict:
    R = {r["key"]: r for r in rows if r.get("last") is not None}
    S = series or {}
    top = _top_surprise(surprises_, market_date)
    blocks = [f(R, S, top, fed, headlines, market_date) for f in (equities, rates, commodities, currencies, crypto, fear)]
    return {"blocks": [b for b in blocks if b], "chain": chain(R, top, fed), "links": LINKS}
