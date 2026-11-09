"""Headlines from publishers' public RSS feeds (title, link, short summary as syndicated by the publisher).

Only what the publisher puts in its public feed is used, and every item links back to the original
article. Paywalled article text is never fetched or republished.
"""
from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")
log = logging.getLogger("news")
UA = {"User-Agent": "Mozilla/5.0 (compatible; markets-briefing/1.0)"}


def _text(s: str, limit: int = 300) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(re.sub(r"\s+", " ", s)).strip()
    return (s[: limit - 1] + "…") if len(s) > limit else s


def _date(s: str):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def fetch(feeds: list[dict], max_age_hours: int = 36, limit: int = 40, since=None, until=None, session_date: str | None = None) -> list[dict]:
    """since/until (UTC datetimes) anchor the headlines to the market session the data refers to."""
    items = []
    now = datetime.now(timezone.utc)
    for f in feeds or []:
        url, source = f.get("url"), f.get("source", "")
        try:
            r = requests.get(url, headers=UA, timeout=25)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            nodes = list(root.iter("item")) or list(root.iter("{http://www.w3.org/2005/Atom}entry"))
            for it in nodes:
                title = _text(it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or "", 220)
                link = (it.findtext("link") or "").strip()
                if not link:
                    ln = it.find("{http://www.w3.org/2005/Atom}link")
                    link = ln.get("href", "") if ln is not None else ""
                desc = it.findtext("description") or it.findtext("{http://www.w3.org/2005/Atom}summary") or ""
                when = _date(it.findtext("pubDate") or it.findtext("{http://www.w3.org/2005/Atom}updated") or "")
                if not title or not link.startswith("http"):
                    continue
                if when and since is not None and (when < since or (until is not None and when > until)):
                    continue
                if when and since is None and now - when > timedelta(hours=max_age_hours):
                    continue
                items.append({"headline": title, "url": link, "source": source,
                              "dateISO": (when or now).date().isoformat(), "ts": (when or now).isoformat(),
                              "blurb": _text(desc, 280),
                              "session": bool(session_date and when and when.astimezone(NY).date().isoformat() == session_date)})
        except Exception as exc:  # noqa: BLE001
            log.warning("feed failed %s: %s", url, exc)
    out = merge(items, limit=limit)
    log.info("news: %d headlines from %d feeds", len(out), len(feeds or []))
    return out


def merge(*lists, limit: int = 40) -> list[dict]:
    """Combine headline lists, drop duplicates (same headline or same link), session headlines first, newest first."""
    seen, out = set(), []
    allitems = [i for lst in lists for i in (lst or [])]
    for it in sorted(allitems, key=lambda x: (x.get("session", False), x["ts"]), reverse=True):
        k = re.sub(r"\W+", "", it["headline"].lower())[:80]
        u = it["url"].split("?")[0].rstrip("/")
        if k in seen or u in seen:
            continue
        seen.update({k, u})
        out.append(it)
    return out[:limit]


def from_imports(folder, since=None, until=None, session_date: str | None = None) -> list[dict]:
    """Headlines saved by the Chrome extension (data/imports/news_<date>.json): headline + link (+ date) read from
    the Bloomberg and FT markets pages in your own browser. Only titles and links, never article text."""
    import json
    from pathlib import Path
    files = sorted(Path(folder).glob("news_*.json"))
    if not files:
        return []
    try:
        data = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("extension headlines unreadable %s: %s", files[-1].name, exc)
        return []
    taken = _date(data.get("taken", "")) or datetime.now(timezone.utc)
    out = []
    for it in data.get("items", []):
        title, url = _text(it.get("headline", ""), 220), str(it.get("url", ""))
        if not title or not re.match(r"^https://www\.(bloomberg\.com|ft\.com)/", url):
            continue
        when = taken
        if it.get("date"):
            try:
                when = datetime.fromisoformat(it["date"] + "T12:00:00+00:00")
            except ValueError:
                pass
        if since is not None and (when < since or (until is not None and when > until)):
            continue
        out.append({"headline": title, "url": url, "source": it.get("source", ""), "dateISO": when.date().isoformat(),
                    "ts": when.isoformat(), "blurb": "", "via": "browser",
                    "session": bool(session_date and when.astimezone(NY).date().isoformat() == session_date)})
    log.info("news: %d headlines from the browser extension (%s)", len(out), files[-1].name)
    return out


def about(items: list[dict], words: list[str], n: int = 6) -> list[dict]:
    pat = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")", re.I)
    return [i for i in items if pat.search(i["headline"] + " " + i.get("blurb", ""))][:n]
