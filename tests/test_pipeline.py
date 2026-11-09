"""Run with:  python -m pytest -q   (or python tests/test_pipeline.py)"""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import importers, journal  # noqa: E402
from pipeline.compute import display, row_from_series, row_from_values  # noqa: E402

IDX = {"key": "spx", "name": "S&P 500", "symbol": "US500", "group": "equities", "unit": "index", "decimals": 2}
YLD = {"key": "us10", "name": "United States 10-Year", "symbol": "US10", "group": "fixed_income", "unit": "yield", "decimals": 3}
CDS = {"key": "frcds", "name": "France CDS", "symbol": "FR", "group": "fixed_income", "unit": "cds", "decimals": 2}


def series(start, values):
    d0 = date.fromisoformat(start)
    out, i, d = [], 0, d0
    while i < len(values):
        if d.weekday() < 5:
            out.append({"date": d.isoformat(), "open": values[i], "close": values[i]})
            i += 1
        d += timedelta(days=1)
    return out


def test_index_row():
    s = series("2023-01-02", [100 + i * 0.1 for i in range(900)])
    r = row_from_series(IDX, s, "yahoo")
    assert abs(r["chg"] - 0.1) < 1e-9
    assert r["perf"]["week"] > 0 and r["perf"]["y3"] is None or r["perf"]["y3"] > 0
    d = display(r)
    assert d["chg"].startswith("+") and d["chg_pct"].endswith("%")


def test_yield_bp():
    s = series("2025-01-01", [4.0] * 300 + [4.10])
    r = row_from_series(YLD, s, "treasury")
    d = display(r)
    assert d["chg"] == "+10.0 bp", d["chg"]
    assert d["week"] == "+10 bp"


def test_cds_bp_not_scaled():
    r = row_from_values(CDS, {"last": 94.0, "chg": -3.25}, "investing_csv", "2026-10-29")
    assert display(r)["chg"] == "-3.2 bp" or display(r)["chg"] == "-3.3 bp"
    assert abs(r["prev"] - 97.25) < 1e-9  # stale Prev. replaced by Last - Chg


def test_values_glitch_zero_chg():
    r = row_from_values(IDX, {"last": 101.0, "chg": 0.0, "chg_pct": 1.0}, "investing_csv", "2026-10-29")
    assert abs(r["prev"] - 100.0) < 1e-6


def test_investing_csv_import():
    insts = [IDX, {**YLD, "aliases": ["U.S. 10Y"]}]
    IDX["aliases"] = ["S&P 500"]
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "My Watchlist_Watchlist_10292026.csv"
        p.write_text('Name,Last,Open,Prev.,Chg.,Chg. %,1 Week\n"S&P 500","7,720.22","7,699.61","7,720.22",-23.76,-0.31%,0.74%\n'
                     'U.S. 10Y,4.934,4.994,5.051,-0.117,-2.32%,-0.38%\nUnknown thing,1,1,1,0,0%,0%\n')
        vals, d = importers.read_values(p, insts)
        assert d == "2026-10-29"
        r = row_from_values(IDX, vals["spx"], "investing_csv", d)
        assert abs(r["prev"] - 7743.98) < 1e-6
        y = row_from_values(YLD, vals["us10"], "investing_csv", d)
        assert display(y)["chg"] == "-11.7 bp"


def test_journal_rules():
    spx = [{"date": "2026-11-02", "open": 100, "close": 101}, {"date": "2026-11-03", "open": 101, "close": 102},
           {"date": "2026-11-04", "open": 102, "close": 99}, {"date": "2026-11-05", "open": 99, "close": 98}]
    entries = [{"session_date": "2026-11-02", "call": "Long", "reason": "x"},
               {"session_date": "2026-11-05", "call": "Short", "reason": "y"}]
    res = journal.score(entries, spx)
    first, second = res["entries"]
    assert first["exit_date"] == "2026-11-04" and abs(first["move_pct"] - (-1.0)) < 1e-9 and first["pnl_pct"] < 0
    assert second["status"].startswith("open") and second["pnl_pct"] > 0
    assert res["closed"] == 1 and res["hits"] == 0



def test_macro_number_and_classify():
    from pipeline import macro
    assert macro.number("3.75%-4.00%") == 4.0
    assert macro.number("165k") == 165
    assert macro.number("-0.3%") == -0.3
    assert macro.classify("CPI (Oct)", "3.9%", "3.7%")[0] == "hawkish"
    assert macro.classify("Nonfarm payrolls", "165k", "65k")[0] == "growth_pos"
    assert macro.classify("Unemployment rate", "4.3%", "4.2%")[0] == "growth_neg"
    assert macro.classify("FOMC decision", "4.25%", "4.00%")[0] == "hawkish"
    assert macro.classify("GDP", "3.2%", "3.2%")[0] == "inline"


def test_yoy_with_missing_month():
    from pipeline import macro
    s = [("2025-09-01", 100.0), ("2025-11-01", 101.0), ("2026-08-01", 103.0), ("2026-09-01", 103.7)]
    assert abs(macro._yoy(s) - 3.7) < 1e-9


def test_tape_patterns():
    from pipeline import method
    def r(key, unit, chg, pct):
        return {"key": key, "unit": unit, "last": 1.0, "chg": chg, "chg_pct": pct}
    risk_off = [r("us2", "yield", -0.12, -2.7), r("us10", "yield", -0.06, -1.2), r("spx", "index", -330, -4.3),
                r("eurusd", "fx", -0.001, -0.12), r("vix", "index", 11, 70), r("xau", "price", 27, 0.7)]
    t = method.tape(risk_off)
    assert t["key"] == "risk_off" and all(c["match"] for c in t["checks"])
    hawk = [r("us2", "yield", 0.10, 2.0), r("us10", "yield", 0.06, 1.2), r("spx", "index", -50, -1.0), r("eurusd", "fx", -0.005, -0.4)]
    assert method.tape(hawk)["key"] == "hawkish"


def test_meter_and_sentiment():
    from pipeline import meter
    assert meter.headline_score("Stocks rally as inflation cools") > 0
    assert meter.headline_score("Stocks tumble on recession fears") < 0
    def r(key, unit, last, chg, pct):
        return {"key": key, "unit": unit, "last": last, "chg": chg, "chg_pct": pct}
    up = [{"date": f"2026-{(i // 28) + 9:02d}-{(i % 28) + 1:02d}", "close": 100 + i * 0.5} for i in range(60)]
    bull = [r("vix", "index", 14, -2, -12), r("us10", "yield", 4.5, -0.08, -1.7), r("dxy", "index", 100, -0.5, -0.5),
            r("rsp", "price", 180, 2, 1.2), r("spx", "index", 129.5, 0.5, 0.39)]
    heads = [{"headline": "Stocks rally as inflation cools"}, {"headline": "Shares rise on soft landing hopes"}]
    strong_prev = {"needle": "0.7"}
    m = meter.build(bull, up, {"key": "dovish", "name": "Dovish"}, [], None, meter.sentiment(heads), [], up[-1]["date"], prev=strong_prev)
    assert m["needle"] > 0.4 and "Long" in m["zone"] and m["prob_up"] > 60, m
    capped = meter.build(bull, up, {"key": "dovish", "name": "Dovish"}, [], None, meter.sentiment(heads), [], up[-1]["date"])
    assert capped["needle"] <= 0.59 + 1e-9   # persistence: no Strong call on the first day
    bear = [r("vix", "index", 24, 5, 26), r("us10", "yield", 4.9, 0.12, 2.5), r("dxy", "index", 100, 0.6, 0.6),
            r("rsp", "price", 180, -3, -1.8)]
    down = [{"date": x["date"], "close": 200 - i * 0.5} for i, x in enumerate(up)]
    m2 = meter.build(bear, down, {"key": "hawkish", "name": "Hawkish"}, [], None,
                     meter.sentiment([{"headline": "Stocks tumble on recession fears"}]), [], down[-1]["date"], prev={"needle": "-0.7"})
    assert m2["needle"] < -0.4 and "Short" in m2["zone"], m2
    m3 = meter.build(bull, up, {"key": "dovish", "name": "Dovish"}, [], None, meter.sentiment(heads),
                     [{"day": "Tue", "event": "CPI y/y, 13:30 GMT"}], up[-1]["date"], prev=strong_prev)
    assert abs(m3["needle"]) < abs(m["needle"])   # event risk pulls the needle to the middle


def test_meter_track_brier():
    import tempfile
    from pathlib import Path
    from pipeline import meter
    spx = [{"date": f"2026-10-{d:02d}", "close": c} for d, c in ((1, 100), (2, 101), (5, 100), (6, 102))]
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "m.csv"
        for d, n in (("2026-10-01", 0.5), ("2026-10-02", 0.5), ("2026-10-05", 0.5)):
            tr = meter.track(p, d, {"needle": n, "zone": "Lean Long", "prob_up": round(50 + 35 * n)}, spx)
        assert tr["calls"] == 3 and tr["hits"] == 2 and tr["scored"] == 3
        assert abs(tr["brier"] - round(((0.68 - 1) ** 2 * 2 + 0.68 ** 2) / 3, 3)) < 1e-6


def test_listen_script():
    from pipeline import listen
    def r(k, u, last, chg, pct):
        return {"key": k, "unit": u, "last": last, "chg": chg, "chg_pct": pct}
    out = listen.script([r("spx", "index", 7376.86, 23.1, 0.31), r("us10", "yield", 4.86, 0.02, 0.4)], "2026-11-06",
                        fed={"text": "Fed funds futures price a 79% chance of a 25 bp hike at the 9 Dec FOMC."},
                        upcoming=[{"day": "Tue 10 Nov", "region": "US", "event": "CPI y/y, 13:30 GMT", "consensus": "3.9%"}])
    text = " ".join(out["sentences"])
    assert "%" not in text and " bp" not in text and "FOMC" not in text
    assert "up 0.3 percent" in text and "25 basis point hike" in text and "Tuesday, US CPI" in text


def test_fed_odds_arithmetic():
    import calendar as cal
    pre, imp, d = 100 - 96.12, 100 - 95.98, 9
    n = cal.monthrange(2026, 12)[1]
    post = (imp - pre * d / n) / ((n - d) / n)
    assert abs((post - pre) / 0.25 - 0.79) < 0.02   # ~79% odds of a December hike, as checked by hand

def test_extension_csv_and_intraday_rule():
    """The Chrome extension's CSV (Key column, Investing.com number formats, Taken time) imports cleanly,
    and an intraday snapshot gives way to the close once that session has ended."""
    from datetime import datetime
    text = ('"Key","Name","Symbol","Last","Open","Prev.","Chg.","Chg. %","Daily","1 Week","1 Month","YTD","1 Year","3 Years","Time","Taken"\n'
            '"spx","S&P 500","US500","7,376.86","7,377.65","7,376.92","+23.13","+0.31%","0.31%","-2.18%","-5.56%","7.76%","7.97%","67.08%","06/11","2026-11-09T01:58:00.000Z"\n'
            '"us10","U.S. 10Y","US10YT","4.874","4.851","4.856","+0.018","+0.37%","0.37%","-0.41%","-7.06%","17.36%","18.59%","4.91%","19:58","2026-11-09T01:58:00.000Z"\n')
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "investing_watchlist_2026-11-06.csv"
        f.write_text(text)
        vals, d = importers.read_values(f, [{**IDX, "aliases": []}, {**YLD, "aliases": []}])
    assert d == "2026-11-06" and vals["spx"]["last"] == 7376.86 and vals["spx"]["taken"].startswith("2026-11-09")
    y = row_from_values(YLD, vals["us10"], "investing_csv", d)
    assert abs(y["chg"] - 0.018) < 1e-9 and y["perf"]["week"] < 0          # yields: % performance turned into bp
    t = datetime.fromisoformat
    assert importers.stale_intraday("2026-11-10T18:00:00Z", "2026-11-10", t("2026-11-10T22:40:00+00:00"))
    assert not importers.stale_intraday("2026-11-10T18:00:00Z", "2026-11-10", t("2026-11-10T18:05:00+00:00"))
    assert not importers.stale_intraday("2026-11-10T22:00:00Z", "2026-11-10", t("2026-11-10T22:40:00+00:00"))


def test_extension_headlines():
    """Headlines saved by the extension: trusted links only, dated, windowed to the session, merged without duplicates."""
    import json
    from datetime import datetime, timezone
    from pipeline import news
    data = {"taken": "2026-11-09T01:58:00Z", "items": [
        {"headline": "Treasury Rally Gets New Boost as Election Hammers the AI Trade", "source": "Bloomberg",
         "url": "https://www.bloomberg.com/news/articles/2026-11-08/treasury-rally", "date": "2026-11-08"},
        {"headline": "Old story from last week that should be dropped", "source": "Bloomberg",
         "url": "https://www.bloomberg.com/news/articles/2026-11-02/old", "date": "2026-11-02"},
        {"headline": "US stocks stage tepid recovery after rout fuelled by AI fears", "source": "Financial Times",
         "url": "https://www.ft.com/content/abc", "date": None},
        {"headline": "A link to somewhere that is not a trusted source at all", "source": "x", "url": "https://example.com/a"}]}
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "news_2026-11-06.json").write_text(json.dumps(data))
        since = datetime(2026, 11, 6, 5, tzinfo=timezone.utc)
        until = datetime(2026, 11, 9, 14, 30, tzinfo=timezone.utc)
        got = news.from_imports(tmp, since, until, "2026-11-06")
    assert [g["source"] for g in got] == ["Bloomberg", "Financial Times"]
    rss = [{"headline": got[1]["headline"], "url": "https://www.ft.com/content/abc?x=1", "source": "Financial Times",
            "ts": "2026-11-08T00:00:00+00:00", "session": False}]
    assert len(news.merge(rss, got)) == 2      # same FT story from RSS and the page counted once


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
