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


def fetch(feeds: list[dict], max_age_hours: int = 36, limit: int = 40) -> list[dict]:
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
                if when and now - when > timedelta(hours=max_age_hours):
                    continue
                items.append({"headline": title, "url": link, "source": source,
                              "dateISO": (when or now).date().isoformat(), "ts": (when or now).isoformat(),
                              "blurb": _text(desc, 280)})
        except Exception as exc:  # noqa: BLE001
            log.warning("feed failed %s: %s", url, exc)
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["ts"], reverse=True):
        k = re.sub(r"\W+", "", it["headline"].lower())[:80]
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    log.info("news: %d headlines from %d feeds", len(out), len(feeds or []))
    return out[:limit]


def about(items: list[dict], words: list[str], n: int = 6) -> list[dict]:
    pat = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")", re.I)
    return [i for i in items if pat.search(i["headline"] + " " + i.get("blurb", ""))][:n]
