"""Step 1: read every feed in sources.yml and collect posts published since the last run.

Writes work/items.json (with article text, never committed) and data/sources_status.json.
"""

import hashlib
import html
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import requests
import trafilatura

from common import (ITEMS_FILE, STATE_FILE, STATUS_FILE, load_json, load_yaml,
                    now_utc, save_json)

UA = "pengyu-zhang-feed/1.0 (+https://pengyu-zhang.github.io/feed/)"
TIMEOUT = 25


def item_id(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def html_to_text(fragment):
    if not fragment:
        return ""
    text = trafilatura.extract(f"<html><body>{fragment}</body></html>") or ""
    if not text:
        text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+\n", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def page_text(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
        return trafilatura.extract(r.text, include_comments=False) or ""
    except Exception:
        return ""


def fetch_source(src, since, seen, cap):
    status = {"feed": src["feed"]}
    try:
        try:
            r = requests.get(src["feed"], headers={"User-Agent": UA}, timeout=TIMEOUT)
            r.raise_for_status()
        except requests.RequestException:  # one retry for flaky hosts
            time.sleep(5)
            r = requests.get(src["feed"], headers={"User-Agent": UA}, timeout=TIMEOUT)
            r.raise_for_status()
        parsed = feedparser.parse(r.content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"unparseable feed: {parsed.bozo_exception}")
    except Exception as e:  # one broken feed must not stop the others
        status["error"] = str(e)[:200]
        return [], status

    status["ok"] = now_utc().isoformat()
    latest = None
    items = []
    for entry in parsed.entries:
        url = entry.get("link")
        when = entry_time(entry)
        if not url or not when:
            continue
        if latest is None or when > latest:
            latest = when
        if when <= since or url in seen:
            continue
        content = ""
        if entry.get("content"):
            content = entry.content[0].get("value", "")
        text = html_to_text(content or entry.get("summary", ""))
        if len(text) < 600:  # feed only has a teaser: read the page itself
            full = page_text(url)
            if len(full) > len(text):
                text = full
        items.append({
            "id": item_id(url),
            "kind": "blog",
            "source": src["name"],
            "source_url": src.get("site", ""),
            "title": html.unescape(entry.get("title", "")).strip() or url,
            "url": url,
            "published": when.isoformat(),
            "basis": "full" if len(text) >= 1500 else "short",
            "text": text,
        })
    if latest:
        status["last_post"] = latest.isoformat()
    items.sort(key=lambda x: x["published"], reverse=True)
    if len(items) > cap:
        status["capped"] = len(items) - cap
        items = items[:cap]
    return items, status


def main():
    cfg = load_yaml("config.yml")
    sources = load_yaml("sources.yml")["blogs"]
    state = load_json(STATE_FILE, {})
    seen = set(state.get("seen", {}))

    now = now_utc()
    oldest = now - timedelta(hours=cfg.get("max_catchup_hours", 72))
    if state.get("last_run"):
        since = datetime.fromisoformat(state["last_run"]) - timedelta(hours=1)
    else:
        since = now - timedelta(hours=cfg.get("first_run_hours", 26))
    since = max(since, oldest)

    cap = cfg.get("max_per_source", 5)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda s: fetch_source(s, since, seen, cap), sources))

    old_status = load_json(STATUS_FILE, {})
    status, items = {}, []
    for src, (got, st) in zip(sources, results):
        prev = old_status.get(src["name"], {})
        if "error" in st:  # keep the last good facts next to the new error
            st = {**{k: v for k, v in prev.items() if k in ("ok", "last_post")}, **st}
        status[src["name"]] = st
        items.extend(got)

    # same post reachable from two feeds: keep one
    unique = {}
    for it in items:
        unique.setdefault(it["id"], it)
    items = sorted(unique.values(), key=lambda x: x["published"], reverse=True)

    save_json(STATUS_FILE, status)
    save_json(ITEMS_FILE, {"since": since.isoformat(), "run_at": now.isoformat(), "items": items})
    errors = sum(1 for s in status.values() if "error" in s)
    print(f"since {since.isoformat()}: {len(items)} new posts, {errors}/{len(sources)} feeds failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
