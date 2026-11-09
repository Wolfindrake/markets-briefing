"""The Long / Short meter for Lords of Finance (S&P 500, next session).

Rule-based and transparent: about ten signals, each scored from -1 (short) to +1 (long), are weighted and combined.
The needle goes to the extremes only when the signals are strong AND agree; when they disagree, or a big event
(CPI, FOMC, payrolls) lands before the next close, it is pulled back to the middle.
Every call is logged in data/history/meter.csv and scored against the next session, so the site shows how often
the meter has been right. Educational tool for the class game, not investment advice.
"""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path

POS = ["rally", "rallies", "gain", "gains", "surge", "surges", "soar", "record high", "beat", "beats", "rebound", "rebounds",
       "rise", "rises", "rising", "higher", "optimism", "upgrade", "strong", "eases", "easing", "cools", "cooling", "deal",
       "ceasefire", "truce", "soft landing", "recover", "recovers", "boost", "jumps", "climbs", "cut rates", "rate cut", "stimulus"]
NEG = ["selloff", "sell-off", "slump", "slumps", "plunge", "plunges", "fall", "falls", "drop", "drops", "loss", "losses",
       "fear", "fears", "worry", "worries", "miss", "misses", "downgrade", "recession", "tumble", "tumbles", "slide", "slides",
       "war", "attack", "strikes", "tariff", "tariffs", "weak", "weaker", "crisis", "default", "probe", "layoffs", "hike",
       "hikes", "hawkish", "sinks", "rout", "turmoil", "shutdown", "sanctions", "correction", "bubble", "volatility"]


def headline_score(text: str) -> float:
    t = " " + re.sub(r"[^a-z\- ]", " ", (text or "").lower()) + " "
    p = sum(t.count(f" {w} ") for w in POS)
    n = sum(t.count(f" {w} ") for w in NEG)
    return 0.0 if p == n == 0 else (p - n) / (p + n)


def sentiment(headlines: list[dict]) -> dict:
    scored = [(headline_score(h.get("headline", "")), h) for h in headlines or []]
    hits = [s for s, _ in scored if s != 0]
    avg = sum(hits) / len(hits) if hits else 0.0
    pos = sum(1 for s in hits if s > 0)
    neg = sum(1 for s in hits if s < 0)
    label = "positive" if avg > 0.15 else "negative" if avg < -0.15 else "mixed"
    return {"score": round(avg, 2), "positive": pos, "negative": neg, "neutral": len(scored) - len(hits), "label": label,
            "top": [{"headline": h["headline"], "source": h.get("source", ""), "url": h.get("url", ""), "score": round(s, 2)}
                    for s, h in sorted(scored, key=lambda x: -abs(x[0]))[:6] if s != 0]}


def _c(x):
    return max(-1.0, min(1.0, x))


def _r(rows):
    return {r["key"]: r for r in rows if r.get("last") is not None}


def regime(rows, closes) -> dict:
    """Market regime from yesterday's close (no look-ahead): volatility x trend, the r/algotrading favourite filter."""
    R = _r(rows)
    rv = None
    if len(closes) >= 21:
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 20, len(closes))]
        mu = sum(rets) / len(rets)
        rv = math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1)) * math.sqrt(252) * 100
    slope = None
    if len(closes) >= 30:
        sma = lambda k, end: sum(closes[end - 20:end]) / 20  # noqa: E731
        slope = (sma(20, len(closes)) / sma(20, len(closes) - 10) - 1) * 100
    vix = (R.get("vix") or {}).get("last")
    stressed = (vix is not None and vix >= 25) or (rv is not None and rv >= 25)
    choppy = slope is not None and abs(slope) < 0.5 and (rv or 0) >= 15
    name = "Stressed" if stressed else "Choppy" if choppy else "Trending" if slope is not None and abs(slope) >= 0.5 else "Calm"
    gate = 0.7 if stressed else 0.8 if choppy else 1.0
    bits = [f"VIX {vix:.1f}" if vix is not None else "", f"20-day realised vol {rv:.0f}%" if rv is not None else "",
            f"20-day average {slope:+.1f}% over 2 weeks" if slope is not None else ""]
    return {"name": name, "gate": gate, "detail": ", ".join(b for b in bits if b),
            "note": {"Stressed": "Stressed regime: daily direction is close to a coin flip, so conviction is cut.",
                     "Choppy": "Choppy, trendless market: signals whipsaw, so conviction is reduced.",
                     "Trending": "Trending market: signals are more reliable.", "Calm": "Calm market."}[name]}


def build(rows, spx_series, tape_, surprises_, fed, sent, upcoming, market_date, macro_=None, prev=None) -> dict:
    R = _r(rows)
    sig = []

    def add(name, s, w, why):
        if s is None:
            return
        sig.append({"name": name, "score": round(_c(s), 2), "weight": w, "why": why})

    closes = [p["close"] for p in spx_series if p["date"] <= market_date]
    if len(closes) >= 21:
        sma20 = sum(closes[-20:]) / 20
        gap = closes[-1] / sma20 - 1
        add("Trend (S&P vs 20-day average)", gap / 0.03, 1.5, f"S&P {gap * 100:+.1f}% vs its 20-day average")
    if len(closes) >= 6:
        wk = (closes[-1] / closes[-6] - 1) * 100
        add("5-day momentum", wk / 4, 1.0, f"S&P {wk:+.1f}% over 5 sessions")
    if len(closes) >= 30:
        rets = [(closes[i] / closes[i - 1] - 1) * 100 for i in range(max(1, len(closes) - 62), len(closes))][:-1]
        mu = sum(rets) / len(rets)
        sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / max(1, len(rets) - 1)) or 1
        z = ((closes[-1] / closes[-2] - 1) * 100) / sd
        if abs(z) >= 1.5:
            add("Overshoot (mean reversion)", -z / 3, 1.0, f"Today's move is {z:+.1f}σ: big moves often partly reverse")
    vix = R.get("vix")
    if vix and vix.get("chg_pct") is not None:
        s = -vix["chg_pct"] / 20
        why = f"VIX {vix['last']:.1f} ({vix['chg_pct']:+.0f}%)"
        if vix["last"] >= 30:
            s += 0.6
            why += ": panic levels are often near short-term lows"
        add("Fear gauge (VIX)", s, 1.0, why)
    us10 = R.get("us10")
    if us10 and us10.get("chg") is not None:
        bp = us10["chg"] * 100
        add("US 10Y yield (discount rate)", -bp / 10, 1.0, f"10Y {bp:+.0f} bp: higher yields weigh on valuations")
    dxy = R.get("dxy")
    if dxy and dxy.get("chg_pct") is not None:
        add("US dollar", -dxy["chg_pct"] / 0.8, 0.5, f"Dollar index {dxy['chg_pct']:+.2f}%")
    rsp = R.get("rsp")
    if rsp and rsp.get("chg_pct") is not None:
        add("Breadth (average stock)", rsp["chg_pct"] / 1.5, 0.5, f"Equal-weight S&P {rsp['chg_pct']:+.1f}%")
    if sent and (sent.get("positive") or sent.get("negative")):
        add("News sentiment (Bloomberg, FT)", sent["score"] * 1.5, 1.5,
            f"{sent['positive']} positive vs {sent['negative']} negative session headlines")
    infl = bool((macro_ or {}).get("cpiYoy") and macro_["cpiYoy"] > 3)
    sv = {"dovish": 0.8, "hawkish": -0.8, "growth_pos": (-0.2 if infl else 0.4), "growth_neg": -0.3, "inline": 0.0}
    rec = [s for s in (surprises_ or []) if s.get("signal") in sv][:4]
    if rec:
        add("Data surprises", sum(sv[s["signal"]] for s in rec) / len(rec), 1.0,
            "; ".join(f"{s['event']} {s['label'].lower()}" for s in rec[:2]))
    if fed and fed.get("change_pp") is not None:
        add("Fed odds (futures)", -fed["change_pp"] / 15, 1.0, f"Hike odds {fed['change_pp']:+.0f} pp on the day")
    tv = {"risk_off": -0.4, "hawkish": -0.7, "oil_shock": -0.5, "dovish": 0.7, "growth_pos": 0.4, "growth_neg": -0.3}
    if tape_ and tape_.get("key") in tv:
        add("Reaction-map pattern", tv[tape_["key"]], 1.0, tape_["name"])

    if not sig:
        return {"needle": 0, "zone": "Neutral", "conviction": 0, "signals": [], "note": "Not enough data."}
    tw = sum(s["weight"] for s in sig)
    score = sum(s["score"] * s["weight"] for s in sig) / tw
    same = sum(s["weight"] for s in sig if s["score"] * score > 0) / tw
    risk = [e for e in (upcoming or [])[:4] if re.search(r"CPI|FOMC|Fed|payroll|rate decision|PCE|GDP", str(e.get("event", "")), re.I)]
    damp = 0.75 if risk else 1.0
    reg = regime(rows, closes)
    needle = _c(score * 1.8) * (0.55 + 0.45 * same) * damp * reg["gate"]
    persist = ""
    if abs(needle) >= 0.6:
        pn = float((prev or {}).get("needle") or 0)
        if not (pn * needle > 0 and abs(pn) >= 0.4):
            needle = math.copysign(0.59, needle)
            persist = " Strong calls need two runs in a row; today is capped at Lean."
    a = abs(needle)
    zone = ("Strong " if a >= 0.6 else "Lean " if a >= 0.2 else "") + ("Long" if needle > 0 else "Short") if a >= 0.2 else "Neutral"
    note = f"{len(sig)} signals, {same * 100:.0f}% of the weight agrees."
    if risk:
        note += f" Event risk before the next close ({risk[0].get('day', '')}: {risk[0].get('event', '')}) pulls the needle toward the middle."
    note += " " + reg["note"] + persist
    prob = 0.5 + 0.35 * needle   # probability the S&P closes the next session higher (15%..85%)
    return {"needle": round(needle, 3), "zone": zone, "conviction": round(a * 100), "score": round(score, 3),
            "prob_up": round(prob * 100), "regime": reg,
            "agreement": round(same * 100), "signals": sorted(sig, key=lambda s: -abs(s["score"] * s["weight"])), "note": note}


def last_call(path: Path, market_date: str) -> dict | None:
    if not path.exists():
        return None
    with open(path, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["date"] < market_date]
    return rows[-1] if rows else None


def track(path: Path, market_date: str, meter: dict, spx_series) -> dict:
    """Log today's call and score past calls on the next session's S&P close: hit rate, Brier score, calibration."""
    rows = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    rows = [r for r in rows if r["date"] != market_date]
    rows.append({"date": market_date, "needle": f"{meter.get('needle', 0):.3f}", "zone": meter.get("zone", ""),
                 "prob_up": str(meter.get("prob_up", 50))})
    rows.sort(key=lambda r: r["date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "needle", "zone", "prob_up"])
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in ("date", "needle", "zone", "prob_up")} for r in rows])
    close = {p["date"]: p["close"] for p in spx_series}
    dates = sorted(close)
    hits = calls = 0
    briers, ups, recent = [], [], []
    buckets = {"long": [0, 0], "short": [0, 0]}
    for r in rows:
        if r["date"] not in close:
            continue
        nxt = [d for d in dates if d > r["date"]]
        if not nxt:
            continue
        move = close[nxt[0]] / close[r["date"]] - 1
        up = 1.0 if move > 0 else 0.0
        n = float(r["needle"] or 0)
        p = float(r.get("prob_up") or (50 + 35 * n)) / 100
        briers.append((p - up) ** 2)
        ups.append(up)
        if abs(n) >= 0.2:
            ok = (move > 0) == (n > 0)
            calls += 1
            hits += ok
            b = buckets["long" if n > 0 else "short"]
            b[0] += 1
            b[1] += ok
            recent.append({"date": r["date"], "zone": r["zone"], "next": f"{move * 100:+.2f}%", "ok": ok})
    brier = sum(briers) / len(briers) if briers else None
    base_rate = sum(ups) / len(ups) if ups else None
    base = None if base_rate is None else sum((base_rate - u) ** 2 for u in ups) / len(ups)
    return {"calls": calls, "hits": hits, "rate": round(100 * hits / calls) if calls else None, "recent": recent[-8:][::-1],
            "scored": len(briers), "brier": None if brier is None else round(brier, 3),
            "coinflip": 0.25, "baseline": None if base is None else round(base, 3),
            "long": {"n": buckets["long"][0], "right": buckets["long"][1]},
            "short": {"n": buckets["short"][0], "right": buckets["short"][1]}}


def alerts(rows, meter, fed, surprises_) -> list[str]:
    R = _r(rows)
    out = []
    s = R.get("spx")
    if s and s.get("chg_pct") is not None and abs(s["chg_pct"]) >= 2:
        out.append(f"S&P 500 {s['chg_pct']:+.1f}% today.")
    v = R.get("vix")
    if v and v.get("chg_pct") is not None and v["chg_pct"] >= 20:
        out.append(f"VIX +{v['chg_pct']:.0f}% to {v['last']:.1f}.")
    t = R.get("us10")
    if t and t.get("chg") is not None and abs(t["chg"] * 100) >= 10:
        out.append(f"US 10Y {t['chg'] * 100:+.0f} bp to {t['last']:.2f}%.")
    if abs(meter.get("needle", 0)) >= 0.6:
        out.append(f"Lords of Finance meter: {meter['zone']} ({meter['conviction']}% conviction).")
    if fed and fed.get("change_pp") is not None and abs(fed["change_pp"]) >= 15:
        out.append(fed["text"])
    for x in (surprises_ or [])[:3]:
        if x.get("signal") in ("hawkish", "dovish"):
            out.append(f"{x['event']}: {x['actual']} vs {x['consensus']} expected ({x['label'].lower()}).")
    return out
