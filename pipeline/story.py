"""The sheet's words, written the way the professor writes them (no AI needed).

His sheets read like a person because they (1) lead with the story, not a fixed list, (2) give every number a
context ("the widest since 2011", "back below 5%", "but +7.3% on the week", "still +6.8% YTD"), (3) explain the
day as driver -> reaction -> why, and (4) state facts, not labels. This module does the same from the numbers,
five years of price history, the economic calendar and the session's headlines. It never invents a cause: a
"because" only appears when the data itself shows it (a surprise, tech vs the index, small caps vs large caps).
"""
from __future__ import annotations

import math
import re
from datetime import date

from .compute import is_rate

NAME = {"spx": "S&P 500", "ixic": "Nasdaq", "dji": "Dow", "rut": "Russell 2000", "sx5e": "Euro Stoxx 50", "dax": "DAX",
        "cac": "CAC 40", "ibex": "IBEX 35", "n225": "Nikkei", "kospi": "KOSPI", "csi300": "CSI 300", "nifty": "Nifty 50",
        "us2": "2Y", "us10": "10Y", "us30": "30Y", "de10": "Germany 10Y", "fr10": "France 10Y", "jp10": "Japan 10Y",
        "brent": "Brent", "wti": "WTI", "xau": "Gold", "xag": "Silver", "btc": "Bitcoin", "ttf": "European gas", "vix": "VIX",
        "move": "MOVE", "eurusd": "EUR/USD", "usdjpy": "USD/JPY", "usdchf": "USD/CHF", "ibx50": "Brazil 50",
        "msciw": "MSCI World", "mscieu": "MSCI Europe", "msciem": "MSCI EM", "frcds": "France 5Y CDS", "rsp": "equal weighted S&P 500",
        "sox": "Philadelphia Semiconductor index"}
REGION = {"US": "US", "EZ": "Euro area", "EU": "Euro area", "UK": "UK", "DE": "Germany", "FR": "France", "CN": "China",
          "JP": "Japan", "IT": "Italy", "ES": "Spain"}


# ------------------------------------------------------------------ numbers in the professor's formats
def lvl(r) -> str:
    v, u = r["last"], r["unit"]
    if u == "yield":
        return f"{v:.2f}%"
    if u == "cds":
        return f"{v:.0f} bp"
    if u == "fx":
        return f"{v:.4f}" if v < 10 else f"{v:.2f}"
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}"


def day(r) -> float | None:
    """Today's move: % for prices, bp for yields and CDS."""
    if r.get("chg") is None:
        return None
    if r["unit"] == "yield":
        return r["chg"] * 100
    if r["unit"] == "cds":
        return r["chg"]
    return r.get("chg_pct")


def wk(r, field="week") -> float | None:
    return (r.get("perf") or {}).get(field)


def fmt(v, r, dp=1) -> str:
    if v is None:
        return "—"
    if is_rate(r["unit"]):
        return "flat" if abs(v) < 0.5 else f"{v:+.0f} bp"
    return "flat" if abs(v) < 0.05 else f"{v:+.{dp}f}%"


def small(v, r) -> bool:
    return v is None or (abs(v) < 1.5 if is_rate(r["unit"]) else abs(v) < 0.3)


def today_and_week(r, label_today="today") -> str:
    """'-1.0% today and -7.0% on the week' / '+1.6% today but -8.6% on the week' / '-0.6%, flat on the week'."""
    d, w = day(r), wk(r)
    s = f"{fmt(d, r)} {label_today}" if d is not None and not small(d, r) else ("flat " + label_today if d is not None else "")
    if w is None:
        return s
    if small(w, r):
        return f"{s}, flat on the week" if s else "flat on the week"
    joiner = " but " if d is not None and not small(d, r) and (d > 0) != (w > 0) else " and "
    return f"{s}{joiner}{fmt(w, r)} on the week" if s else f"{fmt(w, r)} on the week"


def ytd(r, lead=", ", before: str = "") -> str:
    """', still +60% YTD'. Pass the text it follows as `before` to avoid 'and ... and'."""
    y = wk(r, "ytd")
    if y is None:
        return ""
    if lead.strip() == "and" and (" and " in before or " but " in before or not before):
        lead = ", "
    w = wk(r)
    still = "still " if w is not None and y * w < 0 and abs(w) >= (2 if is_rate(r["unit"]) else 1) else ""
    v = f"{y:+.0f} bp" if is_rate(r["unit"]) else (f"{y:+.0f}%" if abs(y) >= 20 else f"{y:+.1f}%")
    return f"{lead}{still}{v} YTD"


def mood(vals: list[float], strong=1.0, soft=0.3) -> str:
    v = [x for x in vals if x is not None]
    if not v:
        return ""
    up, dn, avg = sum(x > 0.15 for x in v), sum(x < -0.15 for x in v), sum(v) / len(v)
    P, N = sum(x for x in v if x > 0), -sum(x for x in v if x < 0)
    if N >= 2.5 * P and avg <= -strong:
        return "weak"
    if P >= 2.5 * N and avg >= strong:
        return "strong"
    if (up and dn and abs(avg) < soft * 1.5) or (max(v) >= 1 and min(v) <= -1):
        return "mixed"
    if avg >= strong:
        return "strong"
    if avg <= -strong:
        return "weak"
    if avg >= soft:
        return "higher"
    if avg <= -soft:
        return "lower"
    return "little changed" if not (up and dn) else "mixed"


# ------------------------------------------------------------------ context from five years of history
TODAY_YEAR = [date.today().year]


def _month(d: str) -> str:
    x = date.fromisoformat(d)
    return f"{x:%B}" if x.year == TODAY_YEAR[0] else f"{x:%B} {x.year}"


def context(r, series: list[dict] | None) -> tuple[int, str]:
    """(priority, phrase) such as (3, 'the highest since March 2025'). 0 = nothing worth saying."""
    if not series or r.get("last") is None or not r.get("date"):
        return 0, ""
    past = [p for p in series if p["date"] < r["date"] and p.get("close") is not None]
    if len(past) < 60:
        return 0, ""
    cur, closes, dates = r["last"], [p["close"] for p in past], [p["date"] for p in past]
    span_days = (date.fromisoformat(r["date"]) - date.fromisoformat(dates[0])).days
    rate = is_rate(r["unit"])
    best = (0, "")

    def keep(pri, txt):
        nonlocal best
        if pri > best[0]:
            best = (pri, txt)

    # level: highest / lowest since ...
    for hi in (True, False):
        word = ("highest" if hi else "lowest")
        idx = next((i for i in range(len(closes) - 1, -1, -1) if (closes[i] >= cur if hi else closes[i] <= cur)), None)
        if idx is None:
            if span_days > 1500:
                keep(4, f"the {word} in at least five years")
            continue
        gap = (date.fromisoformat(r["date"]) - date.fromisoformat(dates[idx])).days
        if gap >= 365:
            keep(4, f"the {word} since {_month(dates[idx])}")
        elif gap >= 90:
            keep(2, f"the {word} since {_month(dates[idx])}")

    # day move: best / worst day since ...
    d = day(r)
    if d is not None and len(closes) > 61:
        chg = [((closes[i] - closes[i - 1]) * (100 if r["unit"] == "yield" else 1)) if rate else
               (closes[i] / closes[i - 1] - 1) * 100 for i in range(1, len(closes)) if closes[i - 1]]
        threshold = 4 if rate else 1.0
        if abs(d) >= threshold:
            j = next((i for i in range(len(chg) - 1, -1, -1) if (chg[i] >= d if d > 0 else chg[i] <= d)), None)
            if rate:
                txt = "the biggest daily " + ("rise" if d > 0 else "fall") + " in yields since "
            else:
                txt = ("the best day since " if d > 0 else "the worst day since ")
            if j is None and span_days > 1500:
                keep(5, txt.replace(" since ", " in at least five years").rstrip())
            elif j is not None:
                gap = (date.fromisoformat(r["date"]) - date.fromisoformat(dates[j + 1])).days
                if gap >= 365:
                    keep(5, txt + _month(dates[j + 1]))
                elif gap >= 120:
                    keep(3, txt + _month(dates[j + 1]))

    # week move: biggest weekly fall / gain since ...
    w = wk(r)
    if w is not None and len(closes) > 260 and not rate and abs(w) >= 4:
        # calendar weeks, as the press counts them: close on the same weekday as today vs a week earlier
        wd = date.fromisoformat(r["date"]).weekday()
        weeks = []
        for i in range(5, len(closes) - 4):       # windows ending at least a week ago (not overlapping this week)
            d_i = date.fromisoformat(dates[i])
            if d_i.weekday() == wd and closes[i - 5]:
                weeks.append(((closes[i] / closes[i - 5] - 1) * 100, dates[i]))
        hit = next((dt for v, dt in reversed(weeks) if (v >= w if w > 0 else v <= w)), None)
        word = "weekly gain" if w > 0 else "weekly fall"
        if hit is None and span_days > 1500:
            keep(4, f"the biggest {word} in at least five years")
        elif hit is not None:
            gap = (date.fromisoformat(r["date"]) - date.fromisoformat(hit)).days
            if gap >= 365:
                keep(4, f"the biggest {word} since {_month(hit)}")
            elif gap >= 120:
                keep(3, f"the biggest {word} since {_month(hit)}")

    # round numbers: back above 100, back below 5%
    prev = r.get("prev")
    if prev:
        step = 0.5 if r["unit"] == "yield" else (10 ** math.floor(math.log10(abs(cur)))) if cur else 0
        if step and r["unit"] not in ("fx", "cds"):
            lo, hi_ = sorted((prev, cur))
            k = math.floor(hi_ / step) * step
            if lo < k <= hi_ and k > 0:
                up = cur > prev
                lv = (f"{k:.1f}%".replace(".0%", "%") if r["unit"] == "yield" else f"{k:,.0f}")
                seen_before = any((c > k if up else c < k) for c in closes[-250:-1])
                keep(3, f"{'back ' if seen_before else ''}{'above' if up else 'below'} {lv}")
    return best


# ------------------------------------------------------------------ the three performance blocks
def _item(R, S, k, level=False, week=False, ctx_min=3, used=None):
    r = R[k]
    s = f"{NAME.get(k, r['name'])} {fmt(day(r), r)}"
    if level:
        s += f" to {lvl(r)}"
    pri, c = context(r, S.get(k))
    if pri >= ctx_min and (used is None or k not in used):
        s += f", {c}"
        if used is not None:
            used.add(k)
    if week and wk(r) is not None and not small(wk(r), r):
        w, d = wk(r), day(r)
        s += (" but " if d is not None and not small(d, r) and (d > 0) != (w > 0) else " and ") + f"{fmt(w, r)} on the week"
    return s


def equities(R, S, used) -> list[str]:
    out = []
    us = [k for k in ("ixic", "spx", "dji", "rut") if k in R]
    if "spx" in R:
        m = mood([day(R[k]) for k in us])
        why = ""
        sp, nq, rt = day(R["spx"]), day(R.get("ixic", {})) if "ixic" in R else None, day(R["rut"]) if "rut" in R else None
        if nq is not None and sp is not None and nq - sp >= 0.6:
            why = ", led by tech"
        elif nq is not None and sp is not None and sp - nq >= 0.6:
            why = ", with tech lagging"
        elif rt is not None and sp is not None and rt - sp >= 0.8:
            why = ", small caps ahead"
        w = wk(R["spx"])
        week_line = w is not None and (abs(w) >= 1.5 or (sp is not None and w * sp < 0 and abs(w) >= 0.8))
        order = sorted(us, key=lambda k: -abs(day(R[k]) or 0))
        parts = [_item(R, S, k, level=(i == 0 or k == "spx"), week=(i == 0 and not week_line), used=used) for i, k in enumerate(order)]
        out.append(f"US {m}{why}: " + ", ".join(parts) + ".")
        if "rsp" in R and day(R["rsp"]) is not None and abs(day(R["rsp"]) - sp) >= 0.5:
            br = "a broad move" if (day(R["rsp"]) > sp) == (sp > 0) else "a narrow move led by the largest stocks"
            out.append(f"The {NAME['rsp']} {fmt(day(R['rsp']), R['rsp'])} against {fmt(sp, R['spx'])} for the index: {br}.")
        if week_line:
            ks = [k for k in ("spx", "ixic", "dji") if k in R and wk(R[k]) is not None]
            ws = [wk(R[k]) for k in ks]
            if all(x < 0 for x in ws) or all(x > 0 for x in ws):
                verb = "fell" if ws[0] < 0 else "rose"
                names = [f"the {NAME[k]} {abs(wk(R[k])):.1f}%" for k in ks]
                line = f"On the week the S&P 500 {verb} {abs(ws[0]):.1f}%" + (", " + ", ".join(names[1:-1]) if len(names) > 2 else "") + \
                       (f" and {names[-1]}" if len(names) > 1 else "")
            else:
                line = f"On the week the S&P 500 is {fmt(w, R['spx'])}, " + ", ".join(f"{NAME[k]} {fmt(wk(R[k]), R[k])}" for k in ks[1:])
            y = wk(R["spx"], "ytd")
            out.append(line + (f". The S&P 500 is {'still ' if y * w < 0 else ''}{y:+.1f}% YTD" if y is not None else "") + ".")
    eu = [k for k in ("dax", "cac", "sx5e", "ibex") if k in R]
    if eu:
        order = sorted(eu, key=lambda k: -abs(day(R[k]) or 0))
        out.append(f"Europe {mood([day(R[k]) for k in eu])}: " +
                   ", ".join(_item(R, S, k, level=(i == 0), week=(i < 2), used=used) for i, k in enumerate(order)) + ".")
    asia = [k for k in ("n225", "kospi", "csi300", "nifty") if k in R]
    if asia:
        order = sorted(asia, key=lambda k: -abs(day(R[k]) or 0))
        big = [k for k in order if abs(day(R[k]) or 0) >= 2][:2]
        if big:
            said_ = []
            for k in big:
                r = R[k]
                pri, c = context(r, S.get(k))
                s = f"{NAME[k]} {fmt(day(r), r)} to {lvl(r)}" + (f", {c}" if pri >= 2 else "") + \
                    (f", {fmt(wk(r), r)} on the week" if wk(r) is not None and not small(wk(r), r) else "")
                said_.append(s + ytd(r, " and ", s))
                used.add(k)
            rest = ", ".join(f"{NAME[k]} {fmt(day(R[k]), R[k])}" for k in order if k not in big)
            out.append(f"Asia {mood([day(R[k]) for k in asia])}: " + ". ".join(said_) + ". " + (rest + "." if rest else ""))
        else:
            out.append(f"Asia {mood([day(R[k]) for k in asia])}: " + ", ".join(_item(R, S, k, used=used) for k in order) + ".")
    tail = []
    if "vix" in R:
        tail.append(f"VIX {lvl(R['vix'])}, {today_and_week(R['vix'])}")
    for k in ("ibx50", "msciem"):
        if k in R and day(R[k]) is not None and abs(day(R[k])) >= 1.0:
            tail.append(f"{NAME[k]} {fmt(day(R[k]), R[k])}" + ytd(R[k]))
    if tail:
        out.append(". ".join(tail) + ".")
    return out[:5]


def fixed_income(R, S, used) -> list[str]:
    out = []
    if "us10" in R:
        d10 = day(R["us10"])
        verb = ("barely moved" if abs(d10) < 1.5 else ("fell hard" if d10 <= -8 else "rose sharply" if d10 >= 8 else
                ("edged down" if d10 < 0 else "edged up") if abs(d10) < 3 else "fell" if d10 < 0 else "rose"))
        bits = []
        for k in ("us10", "us2", "us30"):
            if k in R:
                r = R[k]
                pri, c = context(r, S.get(k))
                b = f"{NAME[k]} {lvl(r)}, {fmt(day(r), r)}" + (f", {c}" if pri >= 3 and k not in used else "")
                if pri >= 3:
                    used.add(k)
                bits.append(b)
        out.append(f"US yields {verb}: " + ". ".join(bits) + ".")
        ws = [(k, wk(R[k])) for k in ("us10", "us2", "us30") if k in R and wk(R[k]) is not None]
        if ws:
            line = "On the week: " + ", ".join(f"{NAME[k]} {fmt(w, R[k])}" for k, w in ws)
            if "us2" in R and wk(R["us2"]) is not None and wk(R["us10"]) is not None:
                c = wk(R["us10"]) - wk(R["us2"])
                line += ("; the curve barely moved" if abs(c) < 3 else f"; the curve {'steepened' if c > 0 else 'flattened'} by {abs(c):.0f} bp")
            if "move" in R:
                line += f". MOVE {lvl(R['move'])}, {fmt(day(R['move']), R['move'])} today"
            out.append(line + ".")
    if "fr10" in R and "de10" in R:
        fr, de = R["fr10"], R["de10"]
        spread = (fr["last"] - de["last"]) * 100
        s = f"France 10Y {lvl(fr)}, {today_and_week(fr)}. The spread over Germany is {spread:.0f} bp"
        if wk(fr) is not None and wk(de) is not None:
            ds = wk(fr) - wk(de)
            if abs(ds) >= 3:
                s += f", {'wider' if ds > 0 else 'narrower'} by {abs(ds):.0f} bp on the week"
        out.append(s + f". Germany 10Y {lvl(de)}, {fmt(wk(de), de)} on the week.")
    elif "de10" in R:
        out.append(f"Germany 10Y {lvl(R['de10'])}, {today_and_week(R['de10'])}.")
    last = []
    if "jp10" in R:
        tw = today_and_week(R["jp10"])
        last.append(f"Japan 10Y {lvl(R['jp10'])}, {tw}{ytd(R['jp10'], ' and ', tw)}")
    if "frcds" in R:
        c = R["frcds"]
        s = f"France 5Y CDS {lvl(c)}, {today_and_week(c)}"
        if c.get("date") and R.get("spx", {}).get("date") and c["date"] != R["spx"]["date"]:
            s += f", quote dated {date.fromisoformat(c['date']):%-d %b}"
        last.append(s)
    if last:
        out.append(". ".join(last) + ".")
    return out[:4]


def others(R, S, used) -> list[str]:
    out = []
    if "brent" in R:
        b = R["brent"]
        pri, c = context(b, S.get("brent"))
        s = f"Brent {lvl(b)}, {today_and_week(b)}" + (f", {c}" if pri >= 3 else "") + ytd(b)
        if "wti" in R:
            s += f". WTI {lvl(R['wti'])}, {fmt(day(R['wti']), R['wti'])}"
        out.append(s + ".")
    if "ttf" in R and (abs(day(R["ttf"]) or 0) >= 1 or abs(wk(R["ttf"]) or 0) >= 4):
        out.append(f"European gas {lvl(R['ttf'])}, {today_and_week(R['ttf'])}{ytd(R['ttf'])}.")
    if "xau" in R:
        g = R["xau"]
        pri, c = context(g, S.get("xau"))
        s = f"Gold {lvl(g)}, {today_and_week(g)}" + (f", {c}" if pri >= 3 else "") + ytd(g)
        if "xag" in R:
            s += f". Silver {lvl(R['xag'])}, {fmt(day(R['xag']), R['xag'])}{ytd(R['xag'])}"
        out.append(s + ".")
    fx = []
    if "eurusd" in R:
        e = R["eurusd"]
        s = f"EUR/USD {lvl(e)}" + (f", {fmt(wk(e), e)} on the week" if wk(e) is not None and not small(wk(e), e) else "")
        fx.append(s + ytd(e, " and ", s if "week" in s else ""))
    fx += [f"{NAME[k]} {lvl(R[k])}" for k in ("usdjpy", "usdchf") if k in R]
    if fx:
        out.append(". ".join(fx) + ".")
    if "btc" in R:
        tw = today_and_week(R["btc"])
        out.append(f"Bitcoin {lvl(R['btc'])}, {tw}{ytd(R['btc'], ' and ', tw)}.")
    return out[:5]


# ------------------------------------------------------------------ overview: driver -> reaction -> why
EVENT = [(r"nonfarm payrolls", "payrolls", 3), (r"average hourly earnings", "average hourly earnings", 2),
         (r"unemployment rate", "unemployment", 2), (r"michigan consumer sentiment( index)?", "Michigan sentiment", 1),
         (r"retail sales", "retail sales", 2), (r"core pce|pce", "PCE inflation", 3), (r"\bcpi\b", "CPI", 3), (r"\bhicp\b", "inflation", 2),
         (r"\bppi\b", "PPI", 2), (r"\bgdp\b", "GDP", 3), (r"ism manufacturing", "ISM manufacturing", 2), (r"ism services", "ISM services", 2),
         (r"rate decision", "rate decision", 3), (r"jobless claims", "jobless claims", 1), (r"adp", "ADP private payrolls", 1),
         (r"mpc vote rate hike", "MPC votes to hike", 2), (r"mpc vote rate cut", "MPC votes to cut", 2)]


def ev_parts(ev: str) -> tuple[str, str, int]:
    """('average hourly earnings', ' y/y', importance 1-3)."""
    e = re.sub(r",.*$", "", ev or "").strip()
    per = " y/y" if re.search(r"y/y|\(yoy\)", e, re.I) else " m/m" if re.search(r"m/m|\(mom\)", e, re.I) else \
          " q/q" if re.search(r"q/q|\(qoq\)", e, re.I) else ""
    for pat, nm, imp in EVENT:
        if re.search(pat, e, re.I):
            return nm, per, imp
    return re.sub(r"\s*(y/y|m/m|q/q)\s*$", "", e), per, 1


def ev_name(ev: str) -> str:
    n, p, _ = ev_parts(ev)
    return n + p


def rank(s, market_date) -> float:
    """Which release is THE story: US first, then the big ones (payrolls, CPI, GDP, central banks), then the size
    of the miss, and today's over earlier ones."""
    reg = str(s.get("region", "")).upper()
    w_reg = 3 if reg in ("US", "USA", "") else 2 if reg in ("EZ", "EU", "EA", "DE", "FR") else 1
    _, _, imp = ev_parts(s.get("event", ""))
    a, c = _num(s.get("actual")), _num(s.get("consensus"))
    size = min(3.0, abs(a - c) / max(abs(c), 0.1)) if a is not None and c is not None else 0
    return w_reg * 2 + imp * 2 + size + (1 if s.get("date") == market_date else 0)


def said(s) -> str:
    """'payrolls 165k against 65k expected' / 'average hourly earnings 3.1% y/y against 2.9%'."""
    n, per, _ = ev_parts(s["event"])
    if n.startswith("MPC votes"):
        return f"{s['actual']} MPC members voted to {n.split()[-1]}"
    return f"{n} {s['actual']}{per}"


def _num(s):
    m = re.search(r"-?\d+(?:\.\d+)?", str(s or "").replace(",", ""))
    return float(m.group()) if m else None


def beat_word(actual, consensus) -> str:
    a, c = _num(actual), _num(consensus)
    if a is None or c is None:
        return "came in at"
    if abs(a - c) < 1e-9:
        return "came in line at"
    far = c and abs(a - c) >= max(abs(c) * 0.5, 0.3) if "k" in str(actual).lower() or abs(c) > 20 else abs(a - c) >= 0.3
    return ("came in far above expectations at" if far else "came in above expectations at") if a > c else \
           ("came in far below expectations at" if far else "came in below expectations at")


def overview(R, S, tape_, surprises_, fed, market_date) -> str:
    sents = []
    surp = sorted([s for s in (surprises_ or []) if s.get("signal") and s.get("signal") != "inline"],
                  key=lambda s: -rank(s, market_date))
    lead_sig = None
    if surp:
        top = surp[0]
        reg = REGION.get(str(top.get("region", "")).upper(), top.get("region", ""))
        n, per, _ = ev_parts(top["event"])
        s = f"{reg} {n} {beat_word(top['actual'], top['consensus'])} {top['actual']}{per} against {top['consensus']}"
        same = [x for x in surp[1:4] if x.get("date") == top.get("date") and x.get("region") == top.get("region")]
        if same:
            x = same[0]
            s += f", with {said(x)} against {x['consensus']}"
        lead_sig = top["signal"]
        if fed and lead_sig in ("hawkish", "growth_pos") and fed.get("hike", 0) >= 50:
            s += f". That keeps a December hike in play, now priced at {fed['hike']}%"
        elif fed and lead_sig in ("dovish", "growth_neg") and fed.get("cut", 0) >= 30:
            s += f". Futures now price a {fed['cut']}% chance of a cut"
        sents.append(s + ".")
    if "spx" in R:
        sp, nq = day(R["spx"]), day(R["ixic"]) if "ixic" in R else None
        d10 = day(R["us10"]) if "us10" in R else None
        eq_txt = f"S&P 500 {fmt(sp, R['spx'])}" + (f" and Nasdaq {fmt(nq, R['ixic'])}" if nq is not None else "")
        y_txt = f"10Y {fmt(d10, R['us10'])}" if d10 is not None else ""
        surprised = lead_sig in ("hawkish", "growth_pos") and (d10 is not None and d10 < 1.5)
        if surprised:
            sents.append(f"Yet yields barely moved ({y_txt}) and stocks {'rose' if (sp or 0) > 0 else 'fell'}: {eq_txt}.")
        elif lead_sig in ("hawkish", "growth_pos") and d10 is not None and d10 < 3 and (sp or 0) > 0.15:
            sents.append(f"Stocks still rose, {eq_txt}, and the 10Y added only {d10:.0f} bp.")
        else:
            verb = "rose" if (sp or 0) > 0.15 else "fell" if (sp or 0) < -0.15 else "were flat"
            sents.append(f"Stocks {verb}, {eq_txt}" + (f", with the {y_txt}" if y_txt else "") + ".")
        w = wk(R["spx"])
        if w is not None and date.fromisoformat(market_date).weekday() == 4 and abs(w) >= 1:
            sents[-1] = sents[-1][:-1] + f", leaving the S&P 500 {'down' if w < 0 else 'up'} {abs(w):.1f}% on the week."
    # the other big story of the day: the largest move elsewhere, with its context
    cands = []
    for k in ("kospi", "n225", "dax", "sx5e", "csi300", "nifty", "ibx50", "brent", "xau", "btc", "ttf"):
        if k in R and day(R[k]) is not None:
            pri, c = context(R[k], S.get(k))
            cands.append((abs(day(R[k])) + pri, k, c, pri))
    if cands:
        cands.sort(reverse=True)
        score, k, c, pri = cands[0]
        r = R[k]
        if abs(day(r)) >= 2 or pri >= 4:
            s = f"Elsewhere, {NAME[k]} {'fell' if day(r) < 0 else 'rose'} {abs(day(r)):.1f}% to {lvl(r)}" + (f", {c}" if pri >= 2 else "")
            if len(cands) > 1:
                _, k2, _, _ = cands[1]
                if abs(day(R[k2]) or 0) >= 3 and (day(R[k2]) > 0) == (day(r) > 0):
                    s += f", and the {NAME[k2]} {'lost' if day(r) < 0 else 'gained'} {abs(day(R[k2])):.1f}%"
            sents.append(s + ".")
    if "vix" in R and abs(day(R["vix"]) or 0) >= 8:
        v = R["vix"]
        sents.append(f"The VIX {'fell' if day(v) < 0 else 'jumped'} {abs(day(v)):.1f}% to {lvl(v)}" +
                     (f" but is still {'up' if wk(v) > 0 else 'down'} {abs(wk(v)):.0f}% on the week"
                      if wk(v) is not None and wk(v) * day(v) < 0 and abs(wk(v)) >= 5 else "") + ".")
    if not sents or (len(sents) == 1 and not surp and tape_ and tape_.get("key") == "quiet"):
        sents.insert(0, "A quiet session with no major data surprise.")
    return " ".join(sents[:4])


# ------------------------------------------------------------------ highlights: facts, not labels
STOP = set("a an and as at by for from in into of on or the to with after over amid its is are be his her their new "
           "gets get set sets hits hit makes make takes take says say said".split())
LOWER = set("""stocks stock shares bonds bond yields yield rally rallies slump slumps falls fall rises rise gains gain drop drops
surge surges jump jumps slides slide sinks sink climbs climb extends extend biggest worst best since record high low
weekly week day daily month year decline declines advance advances trade trades traders investors markets market
oil gas gold dollar euro yen deal deals boost boosts tests test focus looms loom probe crackdown rating firm firms
fund funds credit private regulator halts halt risk risks election elections party ruling edge races race countdown
begins begin era sweep democratic linked across top-rated sudden distress follow follows asian european global
economy economic growth inflation rate rates cut cuts hike hikes bank banks central tariffs tariff talks warns warn
data jobs report payrolls sales spending profits profit earnings results outlook forecast forecasts tech ai chip chips
chipmakers wall street""".split())


def sentence_case(h: str) -> str:
    words = h.split()
    caps = sum(1 for w in words if w[:1].isupper())
    if len(words) < 4 or caps / len(words) < 0.6:
        return h
    out = [words[0]]
    for w in words[1:]:
        core = re.sub(r"[^\w'-]", "", w)
        out.append(w.lower() if core.lower() in STOP | LOWER and not core.isupper() else w)
    return " ".join(out)


def _words(s):
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in STOP}


SRC = {"Financial Times": "FT", "Bloomberg": "Bloomberg"}


def highlights(R, surprises_, headlines, fed, limit=9, market_date=None) -> list[str]:
    out = []
    if fed and fed.get("meeting"):
        m = date.fromisoformat(fed["meeting"])
        move = "hike" if fed.get("hike", 0) >= fed.get("cut", 0) else "cut"
        p = fed["hike"] if move == "hike" else fed["cut"]
        s = f"Fed: a 25 bp {move} on {m.day} {m:%B} is priced at about {p}%"
        if fed.get("change_pp") is not None and abs(fed["change_pp"]) >= 3:
            s += f", {'up' if fed['change_pp'] > 0 else 'down'} {abs(fed['change_pp']):.0f} points on the day"
        out.append(s + ".")
    md = market_date or max((s.get("date", "") for s in surprises_ or []), default="")
    window = 3 if md and date.fromisoformat(md).weekday() == 0 else 1     # "since the last session"
    recent = [s for s in surprises_ or [] if s.get("actual") and s.get("consensus") not in (None, "", "—")
              and (not md or not s.get("date") or 0 <= (date.fromisoformat(md) - date.fromisoformat(s["date"])).days <= window)]
    groups: dict[tuple, list] = {}
    for s in sorted(recent, key=lambda s: -rank(s, md)):
        groups.setdefault((s.get("region", ""), s.get("date", "")), []).append(s)
    topics = set()
    for (reg, d), items in list(groups.items())[:3]:
        regn = REGION.get(str(reg).upper(), reg)
        when = f" ({date.fromisoformat(d):%-d %b})" if d else ""
        parts = []
        for x in items[:3]:
            prev = f", from {x['previous']}" if x.get("previous") not in (None, "", "—") else ""
            parts.append(f"{said(x)} against {x['consensus']} expected{prev}")
            topics |= {t for t in TOPIC if re.search(TOPIC[t], x["event"], re.I)}
        txt = "; ".join(parts)
        out.append(f"{regn}{when}: {txt[0].upper() + txt[1:]}.")
    # headlines: events, not market wraps; nothing the data bullets already say; Bloomberg and FT taken in turn
    pools: dict[str, list] = {}
    cands = []
    for i, h in enumerate(headlines or []):
        t = h["headline"]
        if WRAP.search(t) or any(re.search(TOPIC[x], t, re.I) for x in topics):
            continue
        score = sum(wt for pat, wt in MATTERS if re.search(pat, t, re.I))
        cands.append((-score, i, h))
    for _, _, h in sorted(cands, key=lambda c: (c[0], c[1])):   # what moves markets first, then the publisher's order
        pools.setdefault(h.get("source", ""), []).append(h)
    seen, picked = [], []
    while len(out) + len(picked) < limit and any(pools.values()):
        for src in list(pools):
            if not pools[src]:
                continue
            h = pools[src].pop(0)
            w = _words(h["headline"])
            if not w or any(len(w & s) / max(1, min(len(w), len(s))) >= 0.4 for s in seen):
                continue
            seen.append(w)
            t = re.sub(r"^(interview|opinion|analysis|explainer|live|video|podcast|lex|the big read|exclusive)\s*[.:|–-]\s*", "",
                       h["headline"].strip(), flags=re.I).rstrip(".")
            picked.append(f"{t} ({SRC.get(src, src)}).")   # publisher's own wording and casing
            if len(out) + len(picked) >= limit:
                break
    return out + picked


# what the professor's highlights cover: central banks, data, energy and geopolitics, rates and credit, big tech/AI,
# Europe/France, China/trade, elections and policy
MATTERS = [(r"\b(fed|fomc|powell|warsh|ecb|lagarde|boj|boe|central bank|rate (cut|hike|decision))\b", 3),
           (r"\b(inflation|cpi|pce|jobs|payrolls|gdp|recession|growth)\b", 2),
           (r"\b(oil|opec|brent|crude|gas|iran|hormuz|israel|russia|ukraine|sanction)", 2),
           (r"\b(treasur|yield|bond|bund|gilt|oat|spread|credit|rating|moody|s&p global|fitch|default|debt|deficit)", 2),
           (r"\b(nvidia|alphabet|google|microsoft|apple|amazon|meta|tesla|ai|chip|semiconductor|earnings|profit|capex)\b", 2),
           (r"\b(trump|tariff|white house|congress|election|midterm|democrat|republican|bessent)\b", 2),
           (r"\b(china|beijing|yuan|japan|yen|euro|dollar|gold)\b", 1),
           (r"\b(france|germany|italy|uk|britain|brazil|india|korea)\b", 1)]
TOPIC = {"jobs": r"payroll|jobs|employment|hiring|labou?r market", "inflation": r"\bcpi\b|inflation|prices|pce|hicp",
         "retail": r"retail sales|consumer spending", "gdp": r"\bgdp\b|growth|economy (grew|shrank|expanded|contracted)",
         "sentiment": r"sentiment|confidence"}
WRAP = re.compile(r"^(us |european |asian |global |emerging[- ]market |wall street |)(stocks|shares|equities|markets?|"
                  r"stock market|bonds|treasuries)\b|stock market today|markets wrap|live updates", re.I)


def lede(rows, surprises_=None, fed=None, market_date=None, overview_text: str = "") -> dict:
    """The page's headline, as a newspaper would write it: the driver, its consequence, the other big story."""
    R = {r["key"]: r for r in rows if r.get("last") is not None}
    md = market_date or date.today().isoformat()
    d = date.fromisoformat(md)
    surp = sorted([s for s in (surprises_ or []) if s.get("signal") and s["signal"] != "inline"], key=lambda s: -rank(s, md))
    parts = []
    if surp:
        t = surp[0]
        n, per, _ = ev_parts(t["event"])
        reg = REGION.get(str(t.get("region", "")).upper(), t.get("region", ""))
        parts.append(f"{reg} {n} {t['actual']}{per} vs {t['consensus']} expected")
        if fed and t["signal"] in ("hawkish", "growth_pos") and fed.get("hike", 0) >= 50:
            m = date.fromisoformat(fed["meeting"])
            parts.append(f"{m:%B} hike odds {fed['hike']}%")
    elif "spx" in R:
        parts.append(f"S&P 500 {fmt(day(R['spx']), R['spx'])}, 10Y {lvl(R['us10'])}" if "us10" in R else f"S&P 500 {fmt(day(R['spx']), R['spx'])}")
    big = sorted([k for k in ("n225", "kospi", "dax", "sx5e", "brent", "xau", "btc", "csi300") if k in R and day(R[k]) is not None],
                 key=lambda k: -abs(day(R[k])))
    if big and abs(day(R[big[0]])) >= 3:
        k = big[0]
        two = [k] + [x for x in big[1:2] if abs(day(R[x]) - day(R[k])) < 0.5]
        parts.append(" and ".join(NAME[x] for x in two) + f" {fmt(day(R[k]), R[k])}")
    sents = [s for s in re.split(r"(?<=\.)\s+", overview_text or "") if s]
    head = "; ".join(parts)
    # the standfirst adds what the headline doesn't already say
    rest = [s for s in sents[1:] if not ("hike" in s and "hike" in head) and not any(NAME.get(k, "~") in s and NAME[k] in head for k in big[:2])]
    return {"kicker": f"{d:%A} {d.day} {d:%B} · US close", "headline": head,
            "standfirst": " ".join(rest[:2]) if rest else (sents[0] if sents else "")}


def build(rows, headlines, tape_=None, surprises_=None, series=None, fed=None, market_date=None) -> dict:
    R = {r["key"]: r for r in rows if r.get("last") is not None}
    S = series or {}
    md = market_date or (R.get("spx", {}).get("date") or date.today().isoformat())
    TODAY_YEAR[0] = date.fromisoformat(md).year
    used: set = set()
    return {"overview": overview(R, S, tape_, surprises_, fed, md),
            "highlights": highlights(R, surprises_, headlines, fed, market_date=md),
            "performance": {"equities": equities(R, S, used), "fixed_income": fixed_income(R, S, used), "others": others(R, S, used)},
            "fed_included": bool(fed)}
