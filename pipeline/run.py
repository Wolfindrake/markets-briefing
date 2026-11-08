"""Daily build: fetch -> merge imports -> compute -> history -> site data -> sheet (PDF+XLSX).

Usage
  python -m pipeline.run              # normal run (needs internet)
  python -m pipeline.run --offline    # no downloads: uses history/seed/imports only (for testing)
  python -m pipeline.run --draft      # also ask the AI for a first draft (needs ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import calendar, dashboard, extras, fetch, history, importers, journal, macro, method, narrative, news, verify
from .compute import PERF_KEYS, base_row, display, fill_perf_from_history, is_rate, row_from_series, row_from_values
from .config import (CONTENT_DIR, DATA_DIR, DOWNLOADS, HISTORY_FILE, IMPORTS_DIR, JOURNAL_FILE, MANUAL_DIR, SEED_FILE, SITE_DATA,
                     instruments, load_yaml, settings)
from .sheet import build_pdf, build_xlsx

log = logging.getLogger("run")


def _tz_label(dt: datetime) -> str:
    name = dt.tzname() or ""
    return {"CET": "CET", "CEST": "CEST"}.get(name, name)


def as_of_string(cfg) -> str:
    now = datetime.now(ZoneInfo("UTC"))
    loc = now.astimezone(ZoneInfo(cfg["timezones"]["local"]))
    mkt = now.astimezone(ZoneInfo(cfg["timezones"]["market"]))
    return f"{loc:%H:%M} {_tz_label(loc)} ({mkt:%H:%M} New York)"


def build_rows(insts, cfg, offline: bool):
    stored = history.load(HISTORY_FILE)
    fetched: dict[str, list[dict]] = {}
    if not offline:
        fetched.update(fetch.yahoo({i["key"]: i["ticker"] for i in insts if i["source"] == "yahoo" and i.get("ticker")}))
        fetched.update(fetch.treasury({i["key"]: i["ticker"] for i in insts if i["source"] == "treasury" and i.get("ticker")}))
        fetched.update(fetch.bundesbank({i["key"]: i["ticker"] for i in insts if i["source"] == "bundesbank" and i.get("ticker")}))
        fetched.update(fetch.mof_japan({i["key"]: i["ticker"] for i in insts if i["source"] == "mof" and i.get("ticker")}))
        # Align everything to the latest US equity close: futures and crypto keep trading (and Yahoo opens a new
        # bar on Sunday evening), which would otherwise show a near-zero "change" for the next, unfinished session.
        us_close = max((s[-1]["date"] for k, s in fetched.items() if k in ("spx", "ixic", "dji") and s), default=None)
        if us_close:
            fetched = {k: [r for r in s if r["date"] <= us_close] for k, s in fetched.items()}
            fetched = {k: s for k, s in fetched.items() if s}

    csv_vals, csv_date, csv_name = {}, None, None
    f = importers.latest_investing_csv(IMPORTS_DIR)
    if f:
        csv_vals, csv_date = importers.read_values(f, insts)
        csv_name = f.name
        log.info("Investing CSV %s (%s): %d instruments", f.name, csv_date, len(csv_vals))
    man_vals, man_date = {}, None
    mf = MANUAL_DIR / "latest.csv"
    if mf.exists():
        man_vals, man_date = importers.read_values(mf, insts)

    seed = {}
    if SEED_FILE.exists():
        seed = {r["key"]: r for r in json.loads(SEED_FILE.read_text())["rows"]}

    rows = []
    for inst in insts:
        k = inst["key"]
        series = history.merge_series(stored.get(k, []), fetched.get(k, []))
        auto = row_from_series(inst, fetched[k], inst["source"]) if fetched.get(k) else None
        auto_date = auto["date"] if auto else ""
        row = None
        if k in csv_vals and (csv_vals[k].get("date") or csv_date) >= auto_date:
            row = row_from_values(inst, csv_vals[k], "investing_csv", csv_date)
        elif auto:
            row = auto
        elif k in man_vals and (man_vals[k].get("date") or man_date):
            row = row_from_values(inst, man_vals[k], "manual", man_date)
        elif series:
            row = row_from_series(inst, series, "history")
            row["flags"].append("last stored value")
        elif k in seed and offline:
            row = seed[k]
            row["flags"] = list(row.get("flags", [])) + ["seed data"]
        else:
            row = base_row(inst)
            row["flags"].append("missing: add it to data/manual/latest.csv or upload the Investing.com CSV")
        if row["source"] in ("investing_csv", "manual"):
            fill_perf_from_history(row, [r for r in series if r["date"] < (row["date"] or "9999")])
        rows.append(row)
    return rows, stored, fetched, {"csv_file": csv_name, "csv_date": csv_date, "manual_date": man_date, "csv_vals": csv_vals}


def quality(rows, cfg, market_date):
    q = cfg.get("quality", {})
    md = date.fromisoformat(market_date)
    for r in rows:
        if r["date"]:
            age = (md - date.fromisoformat(r["date"])).days
            if age > q.get("stale_after_days", 4):
                r["flags"].append(f"stale: last value {r['date']}")
        if r["chg"] is not None:
            if is_rate(r["unit"]):
                bp = abs(r["chg"]) * (100 if r["unit"] == "yield" else 1)
                if bp > q.get("big_move_bp", 25):
                    r["flags"].append(f"check: {bp:.0f} bp move")
            elif r["chg_pct"] is not None and abs(r["chg_pct"]) > q.get("big_move_pct", 5):
                r["flags"].append(f"check: {r['chg_pct']:+.1f}% move")
    return [{"key": r["key"], "name": r["name"], "flags": r["flags"]} for r in rows if r["flags"]]


def market_date_of(rows):
    core = [r["date"] for r in rows if r["key"] in ("spx", "ixic", "dji") and r["date"]]
    if core:
        return max(core)
    dates = [r["date"] for r in rows if r["date"]]
    return max(dates) if dates else date.today().isoformat()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--draft", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = settings()
    insts = instruments()
    rows, stored, fetched, inputs = build_rows(insts, cfg, args.offline)
    sheet_rows = [r for r in rows if r.get("sheet", True)]   # the 35 instruments printed on the sheet
    market_date = market_date_of(rows)
    issues = quality(sheet_rows, cfg, market_date)
    as_of = as_of_string(cfg) if not args.offline else f"saved data (no download), market date {market_date}"

    if not args.offline:
        history.save(HISTORY_FILE, rows, stored)

    brief = load_yaml(CONTENT_DIR / "briefing.yaml") if (CONTENT_DIR / "briefing.yaml").exists() else {}
    brief_current = bool(brief) and str(brief.get("date", "")) == market_date
    week_user = [e for e in (brief or {}).get("week_ahead") or [] if isinstance(e, dict)]
    cal_up, cal_rel = ([], []) if args.offline else calendar.build(market_date)
    week_all = calendar.merge(week_user, cal_up + cal_rel)   # your entries win; the calendar fills the gaps
    upcoming = [e for e in week_all if str(e.get("actual", "") or "").strip() == ""
                and (not e.get("date") or str(e.get("date")) > market_date)]

    # ---- the professor's top-down toolkit: macro dashboard, data surprises, reaction-map read of the day
    macro_ = macro.dashboard(rows, args.offline, (brief or {}).get("macro_extra"))
    surprises_ = macro.surprises(week_all, rows, market_date, macro_.get("cpiYoy"))
    tape_ = method.tape(rows)

    # ---- news (public RSS headlines) and the dashboard text (automatic, optionally improved by AI)
    feeds = (cfg.get("news") or {}).get("feeds", [])
    # headlines from the market session (New York midnight of the market date) up to the next open
    ny = ZoneInfo("America/New_York")
    md_ = date.fromisoformat(market_date)
    nxt = md_ + timedelta(days=3 if md_.weekday() == 4 else 1)
    since = datetime(md_.year, md_.month, md_.day, tzinfo=ny).astimezone(ZoneInfo("UTC"))
    until = datetime(nxt.year, nxt.month, nxt.day, 9, 30, tzinfo=ny).astimezone(ZoneInfo("UTC"))
    heads = [] if args.offline else news.fetch(feeds, since=since, until=until, session_date=market_date)
    text = narrative.auto(rows, market_date, as_of, heads, upcoming, tape_, surprises_)
    if not args.offline:
        text = narrative.merge(text, narrative.ai(rows, market_date, heads, upcoming, cfg, tape_, surprises_, macro_),
                               {h["url"] for h in heads})
    # ---- cross-checks (shown on the site as a scorecard)
    sh = text["sheet"]
    claims = [sh.get("overview", "")] + [h for h in sh.get("highlights", []) if "expected" in h] + \
             [b for v in (sh.get("performance") or {}).values() for b in v]
    cross = verify.run(rows, market_date, inputs.get("csv_vals"), inputs.get("csv_date"), texts=claims,
                       calendar_rows=week_all, headlines=None if args.offline else heads, offline=args.offline)
    log.info("cross-checks: %d/%d passed", cross["passed"], cross["total"])
    trump_heads = news.about(heads, ["Trump", "White House", "tariff", "Bessent", "Warsh"], 10)

    # ---- the one-page sheet: your own text if current, else the AI/automatic text
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    prefix = cfg["sheet"].get("file_prefix", "Market-Briefing")
    pdf_name, xlsx_name = f"{prefix}-{market_date}.pdf", f"{prefix}-{market_date}.xlsx"
    meta = {"title": cfg["sheet"]["title"], "market_date": market_date, "as_of": as_of,
            "source_note": cfg["sheet"]["source_note"], "team_label": cfg["site"].get("team_label", "")}
    if brief_current:
        sheet_brief = {**brief, "week_ahead": upcoming[:7]}
    else:
        sheet_brief = {**text["sheet"], "week_ahead": upcoming[:7], "sp500_view": {}}
    fs = build_pdf(DOWNLOADS / pdf_name, meta, sheet_rows, sheet_brief)
    build_xlsx(DOWNLOADS / xlsx_name, meta, sheet_rows, sheet_brief)
    shutil.copyfile(DOWNLOADS / pdf_name, DOWNLOADS / f"{prefix}-latest.pdf")
    shutil.copyfile(DOWNLOADS / xlsx_name, DOWNLOADS / f"{prefix}-latest.xlsx")
    log.info("sheet built: %s (font %.1f pt, %s text)", pdf_name, fs,
             "your" if brief_current else ("AI" if text.get("ai_used") else "automatic"))
    downloads = {"pdf": f"downloads/{prefix}-latest.pdf", "xlsx": f"downloads/{prefix}-latest.xlsx",
                 "archive": sorted((f.name for f in DOWNLOADS.glob(f"{prefix}-20*.pdf")), reverse=True)[:60]}

    # ---- price history for charts
    keep = cfg.get("history", {}).get("keep_days_in_site", 800)
    stored_after = history.load(HISTORY_FILE)
    hist_out = {}
    for inst in insts:
        k = inst["key"]
        ser = [r for r in history.merge_series(stored_after.get(k, []), fetched.get(k, [])) if r["date"] <= market_date]
        hist_out[k] = {"name": inst["name"], "unit": inst["unit"], "points": [[r["date"], round(r["close"], 6)] for r in ser][-keep:]}

    # ---- Lords of Finance journal (real game rules)
    entries = journal.load(JOURNAL_FILE)
    view = (brief or {}).get("sp500_view") or {}
    if view.get("call") and view.get("session_date") and str(view["session_date"]) not in {e["session_date"] for e in entries}:
        # the call typed in content/briefing.yaml counts as a journal entry (no need to edit journal.csv too)
        entries = sorted(entries + [{"session_date": str(view["session_date"]), "call": str(view["call"]),
                                     "reason": str(view.get("reason", "")), "conviction": str(view.get("conviction", ""))}],
                         key=lambda e: e["session_date"])
    spx_series = history.merge_series(stored_after.get("spx", []), fetched.get("spx", []))
    scored = journal.score(entries, spx_series) if spx_series else {"entries": [dict(e, status="no S&P data") for e in entries]}

    over = method.overshoot(rows, spx_series)
    reading = {"tape": tape_, "internals": method.internals(rows), "overshoot": over,
               "lessons": method.lessons(rows, tape_, surprises_, macro_), "library": method.library(),
               "steps": method.steps(rows, tape_, surprises_, over, upcoming, view, heads, text["simple"].get("forces"))}

    data = dashboard.build(rows=sheet_rows, week=upcoming, macro=macro_, surprises=surprises_, reading=reading, cross=cross, market_date=market_date, as_of=as_of, text=text, brief=brief, scored=scored,
                           issues=issues, headlines=heads, trump_heads=trump_heads, inputs=inputs, downloads=downloads, cfg=cfg,
                           prev_path=SITE_DATA / "dashboard.json", snaps_path=DATA_DIR / "snapshots.json", history=hist_out)
    (SITE_DATA / "dashboard.json").write_text(json.dumps(data, default=str, ensure_ascii=False), encoding="utf-8")

    if args.draft:
        extras.draft_commentary(rows, market_date, cfg, CONTENT_DIR / "draft.yaml")
    extras.supabase_sync(rows)

    log.info("done: market date %s, %d data checks, text: %s", market_date, len(issues), "AI" if text.get("ai_used") else "automatic")
    for i in issues:
        log.info("  %s: %s", i["name"], "; ".join(i["flags"]))


if __name__ == "__main__":
    main()
