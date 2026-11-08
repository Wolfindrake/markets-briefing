"""Free data sources: Yahoo Finance (via yfinance, with a direct-API fallback) and US Treasury par yields.

Every function returns {key: [{"date": "YYYY-MM-DD", "open": float|None, "close": float}, ...]}
sorted by date. Failures are logged and simply leave the key out; the pipeline then falls back to
the CSV import, the manual file or the last stored value.
"""
from __future__ import annotations

import csv
import io
import logging
import math
import re
import time
from datetime import date, datetime

import requests

log = logging.getLogger("fetch")
UA = {"User-Agent": "Mozilla/5.0 (compatible; markets-briefing/1.0)"}


def _clean(rows):
    out = []
    for r in rows:
        c = r.get("close")
        if c is None or (isinstance(c, float) and math.isnan(c)):
            continue
        o = r.get("open")
        if o is not None and isinstance(o, float) and math.isnan(o):
            o = None
        out.append({"date": r["date"], "open": o, "close": float(c)})
    out.sort(key=lambda x: x["date"])
    # de-duplicate dates, keep last
    dedup = {}
    for r in out:
        dedup[r["date"]] = r
    return [dedup[d] for d in sorted(dedup)]


def _yahoo_direct(ticker: str, rng: str = "5y") -> list[dict]:
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(ticker)}"
    r = requests.get(url, params={"range": rng, "interval": "1d"}, headers=UA, timeout=30)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    tz_off = res.get("meta", {}).get("gmtoffset", 0)
    rows = []
    for i, t in enumerate(ts):
        d = datetime.utcfromtimestamp(t + tz_off).date().isoformat()
        rows.append({"date": d, "open": q["open"][i], "close": q["close"][i]})
    return _clean(rows)


def yahoo(tickers: dict[str, str]) -> dict[str, list[dict]]:
    """tickers: {key: yahoo_ticker}"""
    out: dict[str, list[dict]] = {}
    if not tickers:
        return out
    try:
        import yfinance as yf

        data = yf.download(
            list(tickers.values()), period="5y", interval="1d", group_by="ticker",
            auto_adjust=False, progress=False, threads=True,
        )
        for key, t in tickers.items():
            try:
                df = data[t] if t in data.columns.get_level_values(0) else None
                if df is None or df.empty:
                    continue
                rows = [
                    {"date": idx.date().isoformat(), "open": row.get("Open"), "close": row.get("Close")}
                    for idx, row in df.iterrows()
                ]
                rows = _clean(rows)
                if rows:
                    out[key] = rows
            except Exception as exc:  # noqa: BLE001
                log.warning("yfinance parse failed for %s: %s", t, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("yfinance download failed: %s", exc)

    for key, t in tickers.items():
        if key in out:
            continue
        for attempt in range(3):
            try:
                rows = _yahoo_direct(t)
                if rows:
                    out[key] = rows
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("Yahoo direct failed for %s (attempt %d): %s", t, attempt + 1, exc)
                time.sleep(2 * (attempt + 1))
    missing = [t for k, t in tickers.items() if k not in out]
    if missing:
        log.warning("No Yahoo data for: %s", ", ".join(missing))
    return out


TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
)


def treasury(columns: dict[str, str], years_back: int = 4) -> dict[str, list[dict]]:
    """columns: {key: treasury_column} e.g. {"us10": "10 Yr"}. Official daily par yields (no open)."""
    out: dict[str, list[dict]] = {k: [] for k in columns}
    if not columns:
        return {}
    this_year = date.today().year
    for year in range(this_year - years_back, this_year + 1):
        try:
            r = requests.get(TREASURY_URL.format(year=year), headers=UA, timeout=30)
            r.raise_for_status()
            reader = csv.DictReader(io.StringIO(r.text))
            for row in reader:
                d = datetime.strptime(row["Date"], "%m/%d/%Y").date().isoformat()
                for key, col in columns.items():
                    v = row.get(col)
                    if v not in (None, "", "N/A"):
                        out[key].append({"date": d, "open": None, "close": float(v)})
        except Exception as exc:  # noqa: BLE001
            log.warning("Treasury %s failed: %s", year, exc)
    return {k: _clean(v) for k, v in out.items() if v}


# ----------------------------------------------------------------------------- official sources
BUNDESBANK_URL = "https://api.statistiken.bundesbank.de/rest/data/BBSIS/{key}"
_DATE_VAL = re.compile(r'^"?(\d{4}-\d{2}-\d{2})"?\s*[,;]\s*"?(-?\d+(?:[.,]\d+)?)"?')


def bundesbank(series: dict[str, str], years_back: int = 4) -> dict[str, list[dict]]:
    """Deutsche Bundesbank daily series (CSV). series: {key: series_key}, e.g. the 10-year federal
    yield from the Svensson term structure: D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A"""
    out = {}
    start = f"{date.today().year - years_back}-01-01"
    for key, skey in series.items():
        try:
            r = requests.get(BUNDESBANK_URL.format(key=skey), params={"format": "csv", "lang": "en", "startPeriod": start},
                             headers=UA, timeout=40)
            r.raise_for_status()
            rows = []
            for line in r.content.decode("utf-8", "replace").splitlines():
                m = _DATE_VAL.match(line.strip())
                if m:
                    rows.append({"date": m.group(1), "open": None, "close": float(m.group(2).replace(",", "."))})
            if rows:
                out[key] = _clean(rows)
            else:
                log.warning("Bundesbank %s: no rows parsed", skey)
        except Exception as exc:  # noqa: BLE001
            log.warning("Bundesbank %s failed: %s", skey, exc)
    return out


MOF_CURRENT = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
MOF_ALL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv"


def _parse_mof(text: str, column: str) -> list[dict]:
    rows, idx = [], None
    for raw in csv.reader(io.StringIO(text)):
        if not raw:
            continue
        if raw[0].strip().lower() == "date":
            idx = [c.strip() for c in raw].index(column) if column in [c.strip() for c in raw] else None
            continue
        if idx is None:
            continue
        m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", raw[0].strip())
        if not m or idx >= len(raw):
            continue
        v = raw[idx].strip()
        if v in ("", "-"):
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
            rows.append({"date": d, "open": None, "close": float(v)})
        except ValueError:
            continue
    return rows


def mof_japan(columns: dict[str, str]) -> dict[str, list[dict]]:
    """Japan Ministry of Finance JGB benchmark yields. columns: {key: "10Y"}."""
    out = {}
    texts = []
    for url in (MOF_ALL, MOF_CURRENT):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            texts.append(r.content.decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            log.warning("MOF %s failed: %s", url, exc)
    for key, col in columns.items():
        rows = []
        for t in texts:
            rows += _parse_mof(t, col)
        cutoff = date(date.today().year - 4, 1, 1).isoformat()
        rows = [r for r in rows if r["date"] >= cutoff]
        if rows:
            out[key] = _clean(rows)
    return out
