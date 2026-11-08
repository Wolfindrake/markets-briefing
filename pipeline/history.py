"""Our own price history (data/history/prices.csv). Grows by one row per instrument per run.

It matters most for the manual/CSV-only instruments (European and Japanese yields, France CDS,
MSCI indices, Brazil 50): after a few weeks the pipeline can compute their weekly and monthly
changes itself.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

FIELDS = ["date", "key", "open", "close", "source"]


def load(path: Path) -> dict[str, list[dict]]:
    series: dict[str, dict[str, dict]] = defaultdict(dict)
    if path.exists():
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    close = float(r["close"])
                except (TypeError, ValueError):
                    continue
                op = float(r["open"]) if r.get("open") not in (None, "") else None
                series[r["key"]][r["date"]] = {"date": r["date"], "open": op, "close": close, "source": r.get("source", "")}
    return {k: [v[d] for d in sorted(v)] for k, v in series.items()}


def merge_series(stored: list[dict], fetched: list[dict]) -> list[dict]:
    by_date = {r["date"]: r for r in stored or []}
    for r in fetched or []:
        by_date[r["date"]] = r
    return [by_date[d] for d in sorted(by_date)]


def save(path: Path, rows_today: list[dict], existing: dict[str, list[dict]]) -> None:
    """Write existing history plus today's last values (one per instrument)."""
    table: dict[tuple, dict] = {}
    for key, ser in existing.items():
        for r in ser:
            table[(r["date"], key)] = {"date": r["date"], "key": key, "open": r.get("open"),
                                       "close": r["close"], "source": r.get("source", "")}
    for row in rows_today:
        if row.get("last") is None or not row.get("date") or row["source"] in ("history", "none"):
            continue
        table[(row["date"], row["key"])] = {"date": row["date"], "key": row["key"], "open": row.get("open"),
                                            "close": row["last"], "source": row["source"]}
        # also keep yesterday's close when we know it but have no stored value for that date yet
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for k in sorted(table):
            r = table[k]
            w.writerow({**r, "open": "" if r["open"] is None else round(r["open"], 6), "close": round(r["close"], 6)})
