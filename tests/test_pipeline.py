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

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
