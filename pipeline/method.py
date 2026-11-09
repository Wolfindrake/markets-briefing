"""How to read the day, the way the course teaches it.

  * tape():       which row of the professor's market reaction map today's moves look like
                  (yields, dollar, equities), and whether each asset behaved as the map expects.
  * internals():  breadth (cap-weighted vs equal-weight S&P), chips, dollar index, 2s10s curve.
  * overshoot():  how big today's S&P move is against its own recent volatility (step 3: "overshooting?").
  * lessons():    the rules of thumb that today's market illustrates (the learning layer).
  * steps():      the briefing guideline's five steps, pre-filled with today's evidence.
All rule-based from the numbers: no AI, nothing invented.
"""
from __future__ import annotations

import math

from .compute import display


def _r(rows):
    return {r["key"]: r for r in rows if r.get("last") is not None}


def _bp(r):
    return None if not r or r["chg"] is None else r["chg"] * (100 if r["unit"] == "yield" else 1)


def _pct(r):
    return None if not r else r.get("chg_pct")


def _arrow(v, eps):
    if v is None:
        return None
    return "up" if v > eps else "down" if v < -eps else "flat"


PATTERNS = {
    "risk_off": {"name": "Risk-off: flight to quality",
                 "map": "Geopolitical or growth scare: yields down, dollar up (also CHF and JPY), equities down. Treasuries and gold outperform.",
                 "expect": {"yields": "down", "usd": "up", "equities": "down"}},
    "hawkish": {"name": "Hawkish: rates up, stocks down",
                "map": "Inflation above consensus or a hawkish central bank: yields up (short end most), dollar up, equities down. Value, energy and banks hold up; growth and tech lag.",
                "expect": {"yields": "up", "usd": "up", "equities": "down"}},
    "oil_shock": {"name": "Oil supply shock",
                  "map": "Oil jumps: inflation fear lifts yields while growth fear hits equities; the dollar firms. Energy and defence outperform.",
                  "expect": {"yields": "up", "usd": "up", "equities": "down"}},
    "dovish": {"name": "Dovish relief: rates down, stocks up",
               "map": "Soft inflation or a dovish central bank: yields down, dollar down, equities up. Growth and tech lead.",
               "expect": {"yields": "down", "usd": "down", "equities": "up"}},
    "growth_pos": {"name": "Growth-positive: rates and stocks up",
                   "map": "Strong growth data with inflation contained: yields up, dollar up, equities up. Cyclicals and small caps lead.",
                   "expect": {"yields": "up", "usd": "up", "equities": "up"}},
    "growth_neg": {"name": "Growth scare: bonds bid, stocks soft",
                   "map": "Weak jobs or GDP: yields down, dollar down, equities mixed. Bonds and defensives (utilities, staples) outperform.",
                   "expect": {"yields": "down", "usd": "down", "equities": "mixed"}},
    "idiosyncratic": {"name": "Equity-specific move: rates calm",
                      "map": "Stocks moved but rates barely did: the driver is earnings, a sector or positioning rather than macro. Go bottom-up.",
                      "expect": {"yields": "flat", "usd": None, "equities": None}},
    "quiet": {"name": "Quiet session",
              "map": "Small moves across assets: no strong macro signal today.",
              "expect": {"yields": "flat", "usd": None, "equities": "flat"}},
    "mixed": {"name": "Mixed signals",
              "map": "The moves do not fit one row of the reaction map: more than one driver is at work.",
              "expect": {"yields": None, "usd": None, "equities": None}},
}


def tape(rows: list[dict]) -> dict:
    R = _r(rows)
    d2, d10 = _bp(R.get("us2")), _bp(R.get("us10"))
    eq = _pct(R.get("spx"))
    usd = _pct(R.get("dxy")) if R.get("dxy") else (None if _pct(R.get("eurusd")) is None else -_pct(R["eurusd"]))
    oil, gold, vix = _pct(R.get("brent")), _pct(R.get("xau")), _pct(R.get("vix"))
    if eq is None or (d2 is None and d10 is None):
        return {}
    yld = d2 if d2 is not None else d10
    big_yld = max(abs(d2 or 0), abs(d10 or 0))
    if eq <= -1.0 and yld < -2 and ((vix or 0) >= 10 or (gold or 0) > 0):
        key = "risk_off"
    elif oil is not None and oil >= 4 and eq < 0 and yld >= 0:
        key = "oil_shock"
    elif yld >= 3 and eq <= -0.5:
        key = "hawkish"
    elif yld <= -3 and eq >= 0.5:
        key = "dovish"
    elif yld >= 3 and eq >= 0.5:
        key = "growth_pos"
    elif yld <= -3 and eq < 0.5:
        key = "growth_neg"
    elif abs(eq) >= 1.0 and big_yld < 3:
        key = "idiosyncratic"
    elif abs(eq) < 0.5 and big_yld < 3:
        key = "quiet"
    else:
        key = "mixed"
    p = PATTERNS[key]
    got = {"yields": _arrow(yld, 1.0), "usd": _arrow(usd, 0.05), "equities": _arrow(eq, 0.15)}
    checks = []
    for k, label in (("yields", "US 2Y yield" if d2 is not None else "US 10Y yield"), ("usd", "US dollar"), ("equities", "S&P 500")):
        exp = p["expect"].get(k)
        val = {"yields": f"{yld:+.0f} bp", "usd": (f"{usd:+.2f}%" if usd is not None else "—"), "equities": f"{eq:+.1f}%"}[k]
        ok = None if exp in (None, "mixed") or got[k] is None else (exp == got[k])
        checks.append({"asset": label, "expected": exp or "—", "actual": got[k] or "—", "value": val, "match": ok})
    curve = None
    if d2 is not None and d10 is not None:
        c = d10 - d2
        curve = ("bull steepener (short end fell most: markets price easier policy)" if c > 2 and d2 < 0 else
                 "bear steepener (long end rose most: term premium / fiscal worry)" if c > 2 else
                 "bear flattener (short end rose most: hawkish)" if c < -2 and d2 > 0 else
                 "bull flattener (long end fell most: growth worry)" if c < -2 else "little change in the curve")
        curve = f"2s10s {c:+.0f} bp: {curve}"
    misses = [c["asset"] for c in checks if c["match"] is False]
    return {"key": key, "name": p["name"], "map": p["map"], "checks": checks, "curve": curve,
            "verdict": ("Moves match the reaction map." if not misses and any(c["match"] for c in checks) else
                        f"Does not fit on: {', '.join(misses)}. Ask why: another driver, or a different regime." if misses else "")}


def internals(rows: list[dict]) -> list[dict]:
    R = _r(rows)
    out = []
    spx, rsp = _pct(R.get("spx")), _pct(R.get("rsp"))
    if spx is not None and rsp is not None:
        gap = spx - rsp
        note = ("The giants pulled the index down while the average stock did better." if gap < -0.5 else
                "The giants carried the index; the average stock did worse." if gap > 0.5 else
                "Broad move: the average stock moved with the index.")
        out.append({"key": "breadth", "label": "Breadth", "value": f"S&P {spx:+.1f}% vs equal-weight {rsp:+.1f}%", "note": note})
    nas, dow = _pct(R.get("ixic")), _pct(R.get("dji"))
    if nas is not None and dow is not None:
        out.append({"key": "style", "label": "Growth vs value", "value": f"Nasdaq {nas:+.1f}% vs Dow {dow:+.1f}%",
                    "note": "Growth outperformed value." if nas - dow > 0.5 else "Value (old economy) outperformed growth." if dow - nas > 0.5 else "No clear style tilt."})
    sox = _pct(R.get("sox"))
    if sox is not None:
        out.append({"key": "chips", "label": "Chips (SOX)", "value": f"{sox:+.1f}%",
                    "note": "The AI trade drove the day." if abs(sox) >= 3 else "Chips in line with the market."})
    dxy = R.get("dxy")
    if dxy and _pct(dxy) is not None:
        out.append({"key": "dollar", "label": "Dollar index", "value": f"{dxy['last']:.2f} ({_pct(dxy):+.2f}%)", "note": ""})
    vix = R.get("vix")
    if vix and _pct(vix) is not None:
        lvl = vix["last"]
        out.append({"key": "fear", "label": "Fear gauge (VIX)", "value": f"{lvl:.1f} ({_pct(vix):+.0f}%)",
                    "note": "Calm (below 15)." if lvl < 15 else "Normal (15-20)." if lvl < 20 else "Stressed (20-30)." if lvl < 30 else "Panic territory (above 30)."})
    return out


def overshoot(rows: list[dict], spx_history: list[dict]) -> dict | None:
    R = _r(rows)
    s = R.get("spx")
    pts = [p["close"] for p in spx_history][-64:]
    if not s or s["chg_pct"] is None or len(pts) < 21:
        return None
    rets = [(pts[i] / pts[i - 1] - 1) * 100 for i in range(1, len(pts))][:-1] or [0]
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / max(1, len(rets) - 1)) or None
    if not sd:
        return None
    z = s["chg_pct"] / sd
    d = display(s)
    size = "an ordinary day" if abs(z) < 1 else "a sizeable move" if abs(z) < 2 else "a large move" if abs(z) < 3 else "an extreme move"
    return {"z": round(z, 1), "sd": round(sd, 2), "text": f"S&P 500 {d['chg_pct']} is {abs(z):.1f} times its typical daily move "
            f"({sd:.2f}%) over the last 3 months: {size}." + (" Check whether the news justifies it or the market is overshooting." if abs(z) >= 2 else "")}


# ---------------------------------------------------------------- the learning layer

LESSONS = {
    "surprise": ("Markets trade the surprise, not the level",
                 "Investors already expect a number (the consensus). Prices move on the gap between the actual and that expectation."),
    "two_channels": ("Two channels: cash flows and the discount rate",
                     "Every headline reaches prices through expected profits, the discount rate, or both. A strong jobs report can lift profits and yields at the same time: the net effect decides."),
    "good_news_bad": ("Good news can be bad news",
                      "When inflation is the main worry, strong data raises the odds of higher rates, and stocks can fall on it."),
    "cap_weight": ("In a cap-weighted index, the giants decide",
                   "A handful of mega-caps make up a large share of the S&P 500. The index can fall on a day when most of its stocks rise, and the reverse."),
    "dow_price": ("The Dow is price-weighted",
                  "The Dow weights companies by share price, not size. A few high-priced stocks can push it the other way from the S&P 500."),
    "duration": ("Growth stocks behave like long bonds",
                 "Most of a growth company's value sits in profits far in the future. When rates or confidence change, those distant cash flows swing the most."),
    "shovels": ("One company's revenue is another's cost",
                "The AI build-out helps the sellers of chips and memory and squeezes the buyers. 'Tech' is not one block."),
    "uncertainty": ("Markets hate uncertainty more than bad news",
                    "Fear spikes when the outcome is unknown; once it is known, volatility often fades even if the news is bad."),
    "flight_quality": ("Flight to quality",
                       "In a scare, money leaves risky assets for safe ones: Treasuries rally (yields fall), and the dollar, yen, Swiss franc and gold tend to firm."),
    "supply_shock": ("Supply shocks are the hardest case",
                     "An oil shock pushes inflation up and growth down at the same time, leaving central banks with no good option."),
    "real_rates": ("Look at real rates",
                   "Policy is only tight if the rate is well above inflation. Rate minus inflation tells you how restrictive the central bank really is."),
    "results_guidance": ("Results versus expectations, and guidance",
                         "A company can beat estimates and still fall if the outlook disappoints: prices follow the future, not last quarter."),
    "short_long": ("Short term: headlines. Long term: profits",
                   "Over days, prices move on fear and news. Over years, they follow earnings."),
    "curve": ("Read the curve, not only the level",
              "If the 2-year moves most, the market is changing its view on the central bank. If the 30-year moves most, it is about inflation, growth or fiscal risk."),
}


def lessons(rows: list[dict], tape_: dict, surprises_: list[dict], macro_: dict | None) -> list[dict]:
    R = _r(rows)
    picks = []

    def add(k, why):
        if k not in [p["key"] for p in picks]:
            t, txt = LESSONS[k]
            picks.append({"key": k, "title": t, "text": txt, "today": why})

    spx, rsp, dow = _pct(R.get("spx")), _pct(R.get("rsp")), _pct(R.get("dji"))
    if surprises_:
        s = next((x for x in surprises_ if x.get("signal") and x["signal"] != "inline"), None)
        if s:
            add("surprise", f"{s['event']}: {s['actual']} vs {s['consensus']} expected ({s['label'].lower()}).")
            if s["signal"] == "growth_pos" and (macro_ or {}).get("cpiYoy") and macro_["cpiYoy"] > 3:
                add("good_news_bad", "Growth beat while inflation is above 3%.")
    if spx is not None and rsp is not None and (spx * rsp < 0 or abs(spx - rsp) >= 0.7):
        add("cap_weight", f"S&P 500 {spx:+.1f}% vs the equal-weight index {rsp:+.1f}%.")
    if spx is not None and dow is not None and spx * dow < 0 and abs(spx - dow) >= 0.4:
        add("dow_price", f"Dow {dow:+.1f}% while the S&P 500 {spx:+.1f}%.")
    nas = _pct(R.get("ixic"))
    if nas is not None and dow is not None and abs(nas - dow) >= 1.0:
        add("duration", f"Nasdaq {nas:+.1f}% vs Dow {dow:+.1f}%.")
    sox = _pct(R.get("sox"))
    if sox is not None and abs(sox) >= 3:
        add("shovels", f"Semiconductors {sox:+.1f}%.")
    k = (tape_ or {}).get("key")
    if k == "risk_off":
        add("flight_quality", "Yields fell while stocks fell.")
    if k == "oil_shock" or (_pct(R.get("brent")) or 0) >= 4:
        add("supply_shock", f"Brent {_pct(R['brent']):+.1f}%.")
    if k in ("hawkish", "dovish"):
        add("two_channels", "Rates moved enough to change the discount rate.")
    vix = _pct(R.get("vix"))
    if vix is not None and vix >= 15:
        add("uncertainty", f"VIX {vix:+.0f}%.")
    d2, d10 = _bp(R.get("us2")), _bp(R.get("us10"))
    if d2 is not None and d10 is not None and abs(d10 - d2) >= 5 and (tape_ or {}).get("curve"):
        add("curve", tape_["curve"])
    rr = (macro_ or {}).get("realRate")
    if rr and len(picks) < 3:
        add("real_rates", f"Fed funds {rr['effr']:.2f}% minus CPI {rr['cpi']:.1f}% = {rr['real_headline']:+.1f}%.")
    if len(picks) < 2:
        add("short_long", "Use today's move as context, not as a forecast.")
    return picks[:4]


def library() -> list[dict]:
    return [{"key": k, "title": t, "text": txt} for k, (t, txt) in LESSONS.items()]


def steps(rows, tape_, surprises_, overshoot_, week, view, headlines, forces) -> list[dict]:
    """The briefing guideline's five steps, with today's evidence filled in."""
    R = _r(rows)
    D = {k: display(r) for k, r in R.items()}
    pic = []
    if "spx" in D:
        pic.append(f"S&P 500 {D['spx']['chg_pct']}, Nasdaq {D.get('ixic', {}).get('chg_pct', '—')}")
    if "us10" in D:
        pic.append(f"US 10Y {R['us10']['last']:.2f}% ({D['us10']['chg']})")
    if "eurusd" in D:
        pic.append(f"EUR/USD {D['eurusd']['chg_pct']}")
    if "brent" in D:
        pic.append(f"Brent {D['brent']['chg_pct']}")
    drivers = [s["q"][0] + " — " + s["label"] for s in surprises_ if s.get("q")][:3]
    drivers += [f.get("title", "") for f in (forces or [])][: max(0, 3 - len(drivers))]
    if not drivers:
        drivers = [h["headline"] for h in (headlines or [])[:3]]
    cats = [f"{e.get('day', '')}: {e.get('event', '')}" for e in (week or [])[:4]]
    call = (view or {}).get("call") or ""
    return [
        {"n": 1, "title": "Market picture", "q": "What moved, and how much?", "auto": "; ".join(pic) + (f". Pattern: {tape_['name']}." if tape_ else "")},
        {"n": 2, "title": "Drivers", "q": "Why? Data vs consensus, central banks, earnings, geopolitics.", "auto": " | ".join(d for d in drivers if d) or "Add the main headlines."},
        {"n": 3, "title": "Overshooting?", "q": "Is the move justified by the news, or too big?", "auto": (overshoot_ or {}).get("text", "Not enough history yet.")},
        {"n": 4, "title": "Catalysts", "q": "What could change the picture next?", "auto": " | ".join(cats) or "Add upcoming events in content/briefing.yaml."},
        {"n": 5, "title": "S&P 500 view", "q": "Your Lords of Finance call and why.",
         "auto": (f"{call}: {(view or {}).get('reason', '')}" if call else "Not set yet: add sp500_view in content/briefing.yaml.")},
    ]


def risk_strip(rows, fed=None) -> list[dict]:
    """One-row risk dashboard: equity fear, bond fear, curve, credit, euro stress, Fed, dollar."""
    R = _r(rows)
    out = []

    def add(label, value, level, tip):
        out.append({"label": label, "value": value, "level": level, "tip": tip})
    v = R.get("vix")
    if v:
        x = v["last"]
        add("Equity fear (VIX)", f"{x:.1f}", "calm" if x < 15 else "normal" if x < 20 else "stressed" if x < 30 else "panic",
            "Below 15 calm, 15-20 normal, 20-30 stressed, above 30 panic.")
    m = R.get("move")
    if m:
        x = m["last"]
        add("Bond fear (MOVE)", f"{x:.0f}", "calm" if x < 80 else "normal" if x < 120 else "stressed",
            "Expected Treasury volatility: below 80 calm, above 120 stressed.")
    if R.get("us10") and R.get("us2"):
        c = (R["us10"]["last"] - R["us2"]["last"]) * 100
        add("Curve 2s10s", f"{c:+.0f} bp", "stressed" if c < 0 else "normal" if c < 50 else "calm",
            "Negative (inverted) has preceded past recessions; steep is normal.")
    h, i = R.get("hyg"), R.get("ief")
    if h and i and h.get("chg_pct") is not None and i.get("chg_pct") is not None:
        d = h["chg_pct"] - i["chg_pct"]
        add("Credit (HY vs Tsy)", f"{d:+.2f} pp", "stressed" if d < -0.5 else "normal" if d < 0.2 else "calm",
            "High-yield bonds (HYG) vs Treasuries (IEF) today: junk lagging means credit stress.")
    if R.get("fr10") and R.get("de10"):
        sp = (R["fr10"]["last"] - R["de10"]["last"]) * 100
        add("Euro stress (OAT-Bund)", f"{sp:.0f} bp", "stressed" if sp >= 90 else "normal" if sp >= 60 else "calm",
            "France minus Germany 10-year spread: above 90 bp is crisis territory.")
    if fed:
        k = fed["hike"] if fed["hike"] >= fed["cut"] else fed["cut"]
        add("Fed next meeting", f"{k}% {'hike' if fed['hike'] >= fed['cut'] else 'cut'}", "stressed" if fed["hike"] >= 50 else "normal",
            fed["text"])
    d = R.get("dxy")
    if d and (d.get("perf") or {}).get("week") is not None:
        w = d["perf"]["week"]
        add("Dollar (1 week)", f"{w:+.1f}%", "stressed" if abs(w) >= 1.5 else "normal", "Big dollar swings tighten global financial conditions.")
    return out
