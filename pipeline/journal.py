"""Lords of Finance call journal, scored on the real game rules:

  * the call is placed before the US open on a class day and executed at the OPEN of that day;
  * it is held until the CLOSE of the trading day before the next class (next journal row);
  * a correct call earns the S&P 500 move over that period, a wrong call loses it;
  * the last call stays open and is marked to the latest close.

data/journal.csv columns: session_date, call (Long/Short), reason, conviction (optional)
"""
from __future__ import annotations

import csv
from pathlib import Path


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("session_date") or "").strip()]
    rows.sort(key=lambda r: r["session_date"])
    return rows


def score(entries: list[dict], spx: list[dict], start_balance: float = 100_000.0) -> dict:
    by_date = {r["date"]: r for r in spx}
    dates = [r["date"] for r in spx]
    balance = start_balance
    out = []
    for i, e in enumerate(entries):
        d = e["session_date"].strip()
        call = (e.get("call") or "").strip().capitalize()
        entry_bar = by_date.get(d)
        res = {"session_date": d, "call": call, "reason": e.get("reason", ""), "conviction": e.get("conviction", ""),
               "entry": None, "exit": None, "exit_date": None, "move_pct": None, "pnl_pct": None, "status": ""}
        if entry_bar is None or entry_bar.get("open") is None:
            res["status"] = "no S&P data for this date yet"
            out.append(res)
            continue
        res["entry"] = entry_bar["open"]
        if i + 1 < len(entries):
            nxt = entries[i + 1]["session_date"].strip()
            prior = [x for x in dates if x < nxt]
            if not prior:
                res["status"] = "pending"
                out.append(res)
                continue
            res["exit_date"] = prior[-1]
            res["status"] = "closed"
        else:
            res["exit_date"] = dates[-1]
            res["status"] = "open (marked to latest close)"
        res["exit"] = by_date[res["exit_date"]]["close"]
        move = (res["exit"] / res["entry"] - 1.0) * 100.0
        direction = 1 if call == "Long" else -1 if call == "Short" else 0
        res["move_pct"] = move
        res["pnl_pct"] = move * direction
        if direction == 0:
            res["status"] = "no call (counts as wrong in the game)"
            res["pnl_pct"] = -abs(move)
        if res["status"] == "closed":
            balance *= 1 + res["pnl_pct"] / 100.0
        out.append(res)
    closed = [r for r in out if r["status"] == "closed"]
    hits = sum(1 for r in closed if (r["pnl_pct"] or 0) > 0)
    return {"entries": out, "balance": balance, "start": start_balance,
            "closed": len(closed), "hits": hits}
