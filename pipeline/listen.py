"""The spoken briefing: "what changed and why", written to be read aloud (about a minute).

Built only from the day's numbers, the reaction-map read, data surprises, Fed odds, the meter and the calendar.
The site reads it with the phone's or computer's own text-to-speech (no key, no cost). With an AI key the AI
version replaces it (same facts, more natural wording).
"""
from __future__ import annotations

import re
from datetime import date


def _num(v, dp=1):
    s = f"{abs(v):,.{dp}f}"
    return s[:-2] if s.endswith(".0") and dp == 1 else s


def _pct(v):
    if v is None:
        return None
    if abs(v) < 0.05:
        return "flat"
    return f"{'up' if v > 0 else 'down'} {_num(v)} percent"


def _bp(v):
    if v is None:
        return None
    if abs(v) < 0.5:
        return "unchanged"
    return f"{'up' if v > 0 else 'down'} {abs(v):.0f} basis points"


def speakable(text: str) -> str:
    t = re.sub(r"S&P|S and P|SandP", "S and P", text)
    t = t.replace("%", " percent").replace(" bp", " basis points").replace("&", " and ").replace("y/y", "year on year")
    t = re.sub(r"\bFOMC\b", "Fed meeting", t)
    t = re.sub(r"\b(\d+)Y\b", r"\1-year", t)
    t = re.sub(r"(^|\s)\+(\d)", r"\1up \2", t)
    t = re.sub(r"(^|\s)-(\d)", r"\1down \2", t)
    t = re.sub(r"(\d)k\b", r"\1 thousand", t)
    t = re.sub(r"(\d+) basis points (hike|cut|move)", r"\1 basis point \2", t)
    t = re.sub(r"(\d) pp\b", r"\1 percentage points", t)
    for a, b in (("Jan", "January"), ("Feb", "February"), ("Mar", "March"), ("Apr", "April"), ("Jun", "June"), ("Jul", "July"),
                 ("Aug", "August"), ("Sep", "September"), ("Oct", "October"), ("Nov", "November"), ("Dec", "December")):
        t = re.sub(rf"(\d) {a}\b", rf"\1 {b}", t)
    return re.sub(r"\s+", " ", t).strip()


def script(rows, market_date, tape_=None, surprises_=None, fed=None, meter=None, upcoming=None, sent=None, overview: str = "") -> dict:
    R = {r["key"]: r for r in rows if r.get("last") is not None}
    d = date.fromisoformat(market_date)
    out = [f"Your markets briefing for the close of {d:%A} {d.day} {d:%B}."]
    if overview:
        # the same story as the headline and the sheet: driver, reaction, the twist
        out += [s for s in re.split(r"(?<=\.)\s+", overview) if s]
        bits = []
        for k, nm in (("sx5e", "Europe's Euro Stoxx"), ("brent", "Brent oil"), ("xau", "gold"), ("btc", "bitcoin")):
            r = R.get(k)
            if r and r.get("chg_pct") is not None and abs(r["chg_pct"]) >= 0.5 and nm.split()[-1].lower() not in overview.lower():
                bits.append(f"{nm} {_pct(r['chg_pct'])}")
        if bits:
            out.append("Also: " + ", ".join(bits) + ".")
        return _finish(out, meter, upcoming, sent)
    s = R.get("spx")
    if s:
        line = f"The S and P 500 closed {_pct(s.get('chg_pct'))}, at {s['last']:,.0f}"
        n = R.get("ixic")
        if n:
            line += f". The Nasdaq was {_pct(n.get('chg_pct'))}"
        dji = R.get("dji")
        if dji:
            line += f", and the Dow {_pct(dji.get('chg_pct'))}"
        out.append(line + ".")
    if tape_ and tape_.get("name"):
        out.append(f"The pattern of the day: {tape_['name'].lower()}. {tape_.get('map', '').split('.')[0]}.")
    t2, t10 = R.get("us2"), R.get("us10")
    if t10:
        line = f"In bonds, the US ten-year yield was {_bp(t10['chg'] * 100 if t10.get('chg') is not None else None)}, at {t10['last']:.2f} percent"
        if t2:
            line += f", and the two-year {_bp(t2['chg'] * 100 if t2.get('chg') is not None else None)}"
        out.append(line + ".")
    bits = []
    for k, nm in (("brent", "Brent oil"), ("xau", "gold"), ("btc", "bitcoin")):
        r = R.get(k)
        if r and r.get("chg_pct") is not None and abs(r["chg_pct"]) >= 0.5:
            bits.append(f"{nm} {_pct(r['chg_pct'])}")
    eu = R.get("sx5e")
    if eu and eu.get("chg_pct") is not None:
        bits.insert(0, f"Europe's Euro Stoxx {_pct(eu['chg_pct'])}")
    if bits:
        out.append("Elsewhere: " + ", ".join(bits) + ".")
    v = R.get("vix")
    if v and v.get("chg_pct") is not None and abs(v["chg_pct"]) >= 8:
        out.append(f"The VIX fear gauge moved {_pct(v['chg_pct'])}, to {v['last']:.1f}.")
    surp = [x for x in (surprises_ or []) if x.get("signal") and x["signal"] != "inline"][:2]
    if surp:
        out.append("Why it moved: " + " ".join(
            f"{speakable(x['event'])} came in at {speakable(x['actual'])} against {speakable(x['consensus'])} expected, a {x['label'].lower()}."
            for x in surp))
    if fed:
        out.append(speakable(fed["text"]))
    return _finish(out, meter, upcoming, sent)


def _finish(out, meter, upcoming, sent):
    if sent and sent.get("label"):
        out.append(f"The tone of the news was {sent['label']}.")
    if meter and meter.get("zone"):
        z = meter["zone"].lower()
        out.append(f"For Lords of Finance, the meter reads {z}, with {meter.get('conviction', 0)} percent conviction"
                   + (f", in a {meter['regime']['name'].lower()} market" if meter.get("regime") else "") + ".")
    DAYS = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
    REG = {"US": "US", "CN": "China", "UK": "UK", "EZ": "euro area", "JP": "Japan", "DE": "Germany", "FR": "France"}
    nxt = [e for e in (upcoming or []) if str(e.get("day", "")).lower() != "ahead"][:3]
    if nxt:
        out.append("Coming up: " + "; ".join(f"{DAYS.get(str(e.get('day', '')).split(' ')[0], '')}, {REG.get(e.get('region', ''), '')} {speakable(str(e.get('event', '')).split(',')[0])}".replace("US US", "US")
                                               + (f", expected {speakable(str(e['consensus']).split(' /')[0])}" if e.get("consensus") else "")
                                               for e in nxt) + ".")
    out.append("That's the briefing. Have a good class.")
    out = [speakable(x) for x in out if x]
    words = sum(len(x.split()) for x in out)
    return {"sentences": out, "words": words, "seconds": round(words / 2.6)}
