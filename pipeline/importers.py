"""Read the Investing.com watchlist CSV export and the hand-edited manual file.

The Investing.com export format is not documented, so the reader is deliberately tolerant:
it finds the header row, matches columns by common names, strips '%', '+', ',' and 'K/M/B'
suffixes, and matches rows to instruments by the aliases in config/instruments.yaml.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger("import")

COLS = {
    "key": ["key"],
    "name": ["name", "instrument", "symbol name"],
    "symbol": ["symbol", "ticker"],
    "date": ["date", "as of"],
    "last": ["last", "price", "last price", "close"],
    "open": ["open"],
    "prev": ["prev.", "prev", "previous close", "prev close"],
    "chg": ["chg.", "chg", "change"],
    "chg_pct": ["chg. %", "chg %", "change %", "% chg", "chg.%", "% change"],
    "daily": ["daily"],
    "week": ["1 week", "weekly", "1w"],
    "month": ["1 month", "monthly", "1m"],
    "ytd": ["ytd"],
    "year": ["1 year", "yearly", "1y"],
    "y3": ["3 years", "3y", "3 year"],
    "taken": ["taken"],          # when the browser extension read the watchlist (ISO time, UTC)
}
NUMERIC = ["last", "open", "prev", "chg", "chg_pct", "daily", "week", "month", "ytd", "year", "y3"]


def to_number(s):
    if s is None:
        return None
    s = str(s).strip().replace("−", "-").replace(",", "")
    if s in ("", "-", "—", "N/A", "n/a"):
        return None
    s = s.replace("%", "").replace("bp", "").replace("+", "").strip()
    mult = 1.0
    if s and s[-1] in "KMB":
        mult = {"K": 1e3, "M": 1e6, "B": 1e9}[s[-1]]
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _read_rows(text: str) -> list[dict]:
    lines = text.splitlines()
    # find the header line: the first line mentioning a name/key column and a last/price column
    start = 0
    for i, line in enumerate(lines[:30]):
        low = line.lower()
        if ("name" in low or "key" in low) and ("last" in low or "price" in low):
            start = i
            break
    sample = "\n".join(lines[start:start + 5])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO("\n".join(lines[start:])), dialect)
    header = next(reader, [])
    idx = {}
    for field, names in COLS.items():
        for j, h in enumerate(header):
            if _norm(h) in names and field not in idx:
                idx[field] = j
    rows = []
    for rec in reader:
        if not any(c.strip() for c in rec):
            continue
        row = {}
        for field, j in idx.items():
            v = rec[j] if j < len(rec) else ""
            row[field] = to_number(v) if field in NUMERIC else v.strip()
        rows.append(row)
    return rows


def _match(instruments: list[dict], row: dict):
    if row.get("key"):
        for inst in instruments:
            if inst["key"] == row["key"].strip():
                return inst
    cand = {_norm(row.get("name", "")), _norm(row.get("symbol", ""))} - {""}
    for inst in instruments:
        names = {_norm(a) for a in inst.get("aliases", [])} | {_norm(inst["name"]), _norm(inst.get("symbol", ""))}
        if cand & names:
            return inst
    return None


def _date_from_filename(path: Path):
    m = re.search(r"(\d{2})(\d{2})(20\d{2})", path.stem)  # MMDDYYYY as in My Watchlist_Watchlist_10292026.csv
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            pass
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", path.stem)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()


def stale_intraday(taken: str | None, as_of: str, now: datetime | None = None) -> bool:
    """True when a snapshot was taken DURING the New York session of `as_of` and that session has since closed:
    the closing prices from the regular feeds are then better than the intraday snapshot."""
    if not taken:
        return False
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        t = datetime.fromisoformat(taken.replace("Z", "+00:00")).astimezone(ny)
        n = (now or datetime.now(tz=ny)).astimezone(ny)
    except (ValueError, KeyError):
        return False
    before_close = t.date().isoformat() == as_of and (t.hour, t.minute) < (16, 10)
    closed_since = n.date().isoformat() > as_of or (n.date().isoformat() == as_of and (n.hour, n.minute) >= (16, 10))
    return before_close and closed_since


def latest_investing_csv(folder: Path):
    files = sorted(folder.glob("*.csv"), key=lambda p: (_date_from_filename(p), p.stat().st_mtime))
    return files[-1] if files else None


def read_values(path: Path, instruments: list[dict]) -> tuple[dict, str]:
    """Return ({key: values}, file_date)."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    file_date = _date_from_filename(path)
    out, unmatched = {}, []
    for row in _read_rows(text):
        inst = _match(instruments, row)
        if not inst:
            if row.get("name"):
                unmatched.append(row["name"])
            continue
        if row.get("last") is None:
            continue
        vals = {k: row.get(k) for k in NUMERIC}
        if row.get("date"):
            try:
                vals["date"] = datetime.fromisoformat(row["date"]).date().isoformat()
            except ValueError:
                vals["date"] = None
        if row.get("taken"):
            vals["taken"] = row["taken"]
        out[inst["key"]] = vals
    if unmatched:
        log.warning("%s: rows not matched to any instrument (add an alias): %s", path.name, ", ".join(unmatched))
    return out, file_date
