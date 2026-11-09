"""Turn price series or imported values into sheet rows.

A row is a dict:
  key, name, symbol, group, unit, decimals,
  date            date of the last value (YYYY-MM-DD)
  last, open, prev, chg, chg_pct
  perf            {"week","month","ytd","year","y3"} -> % for prices, bp for yields/CDS
  source          yahoo | treasury | investing_csv | manual | history | seed | none
  flags           list of strings shown on the site (stale, missing, check...)
"""
from __future__ import annotations

from datetime import date, timedelta

PERF_KEYS = ["week", "month", "ytd", "year", "y3"]
RATE_UNITS = {"yield", "cds"}


def is_rate(unit: str) -> bool:
    return unit in RATE_UNITS


def bp_factor(unit: str) -> float:
    # yields are quoted in %, so 1 bp = 0.01; CDS are quoted in bp already
    return 100.0 if unit == "yield" else 1.0


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _shift_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 - months, 12)
    y = d.year + y
    m = m + 1
    # clamp day
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def value_on_or_before(series: list[dict], target: date):
    best = None
    for r in series:
        if _d(r["date"]) <= target:
            best = r
        else:
            break
    return best["close"] if best else None


def reference_dates(last: date) -> dict[str, date]:
    return {
        "week": last - timedelta(days=7),
        "month": _shift_months(last, 1),
        "ytd": date(last.year - 1, 12, 31),
        "year": _shift_months(last, 12),
        "y3": _shift_months(last, 36),
    }


def change(last: float, past: float | None, unit: str):
    if past is None or past == 0:
        return None
    if is_rate(unit):
        return (last - past) * bp_factor(unit)
    return (last / past - 1.0) * 100.0


def base_row(inst: dict) -> dict:
    return {
        "key": inst["key"], "name": inst["name"], "symbol": inst.get("symbol", ""),
        "group": inst["group"], "unit": inst["unit"], "decimals": inst.get("decimals", 2),
        "date": None, "last": None, "open": None, "prev": None, "chg": None, "chg_pct": None,
        "perf": {k: None for k in PERF_KEYS}, "source": "none", "flags": [],
        "sheet": inst.get("sheet", True), "investing": inst.get("investing", ""),
    }


def row_from_series(inst: dict, series: list[dict], source: str) -> dict | None:
    if not series:
        return None
    row = base_row(inst)
    last = series[-1]
    row["date"] = last["date"]
    row["last"] = last["close"]
    row["open"] = last.get("open")
    if len(series) >= 2:
        row["prev"] = series[-2]["close"]
        row["chg"] = row["last"] - row["prev"]
        row["chg_pct"] = (row["last"] / row["prev"] - 1.0) * 100.0 if row["prev"] else None
    refs = reference_dates(_d(last["date"]))
    first_date = _d(series[0]["date"])
    for k, ref in refs.items():
        if ref < first_date:
            continue  # not enough history: leave empty rather than guess
        row["perf"][k] = change(row["last"], value_on_or_before(series, ref), inst["unit"])
    row["source"] = source
    return row


def fill_perf_from_history(row: dict, series: list[dict]) -> None:
    """For imported/manual rows without performance columns, use our own stored history."""
    if not series or row["last"] is None or not row["date"]:
        return
    refs = reference_dates(_d(row["date"]))
    first_date = _d(series[0]["date"])
    for k, ref in refs.items():
        if row["perf"].get(k) is None and ref >= first_date:
            row["perf"][k] = change(row["last"], value_on_or_before(series, ref), row["unit"])
    if row["prev"] is None:
        prior = [r for r in series if r["date"] < row["date"]]
        if prior:
            row["prev"] = prior[-1]["close"]
            row["chg"] = row["last"] - row["prev"]
            row["chg_pct"] = (row["last"] / row["prev"] - 1.0) * 100.0 if row["prev"] else None


def row_from_values(inst: dict, vals: dict, source: str, as_of: str | None) -> dict:
    """vals may hold last, open, prev, chg, chg_pct and performance in PERCENT (as Investing.com exports)."""
    row = base_row(inst)
    row["date"] = vals.get("date") or as_of
    last = vals.get("last")
    row["last"] = last
    row["open"] = vals.get("open")
    chg, pct, prev = vals.get("chg"), vals.get("chg_pct"), vals.get("prev")
    # Investing.com's "Prev." is often stale; Last - Chg is reliable. Chg of 0 with a non-zero % is a glitch.
    if last is not None and chg is not None and not (chg == 0 and pct not in (None, 0)):
        prev = last - chg
    elif last is not None and pct is not None and pct != -100:
        prev = last / (1 + pct / 100.0)
        chg = last - prev
    if prev is not None and chg is None and last is not None:
        chg = last - prev
    if prev and last is not None and pct is None:
        pct = (last / prev - 1.0) * 100.0
    row["prev"], row["chg"], row["chg_pct"] = prev, chg, pct
    if last is not None:
        for k in PERF_KEYS:
            p = vals.get(k)
            if p is None:
                continue
            if is_rate(inst["unit"]):
                past = last / (1 + p / 100.0) if p != -100 else None
                row["perf"][k] = (last - past) * bp_factor(inst["unit"]) if past is not None else None
            else:
                row["perf"][k] = p
    row["source"] = source
    return row


# ---------------------------------------------------------------- formatting


def _num(v, dp):
    return f"{v:,.{dp}f}"


def _signed(v, dp, suffix=""):
    if v is None:
        return "—"
    s = f"{abs(v):,.{dp}f}"
    sign = "-" if v < 0 and float(s.replace(",", "")) != 0 else "+"
    return f"{sign}{s}{suffix}"


def display(row: dict) -> dict:
    """Strings exactly as printed on the sheet."""
    dp, unit = row["decimals"], row["unit"]
    rate = is_rate(unit)
    f = lambda v: "—" if v is None else _num(v, dp)  # noqa: E731
    out = {
        "name": row["name"], "symbol": row["symbol"],
        "last": f(row["last"]), "open": f(row["open"]), "prev": f(row["prev"]),
    }
    if rate:
        bp = None if row["chg"] is None else row["chg"] * bp_factor(unit)
        out["chg"] = _signed(bp, 1, " bp")
        out["daily"] = out["chg"]
        out["chg_pct"] = _signed(row["chg_pct"], 2, "%")
        for k in PERF_KEYS:
            out[k] = _signed(row["perf"][k], 0, " bp")
    else:
        out["chg"] = _signed(row["chg"], dp)
        out["chg_pct"] = _signed(row["chg_pct"], 2, "%")
        out["daily"] = out["chg_pct"]
        for k in PERF_KEYS:
            out[k] = _signed(row["perf"][k], 2, "%")
    return out
