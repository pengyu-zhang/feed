"""Health check for every feed in sources.yml, run from GitHub's network (same as the daily job).

Prints one line per feed: status with our bot user agent, status with a browser user agent,
number of entries, newest entry date, and how many entries carry no date. Writes nothing.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import feedparser
import requests

from common import load_yaml

BOT = "pengyu-zhang-feed/1.0 (+https://pengyu-zhang.github.io/feed/)"
BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def get(url, ua):
    try:
        r = requests.get(url, headers={"User-Agent": ua, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"},
                         timeout=25, allow_redirects=True)
        return r.status_code, r
    except Exception as e:
        return type(e).__name__, None


def check(src):
    bot, rb = get(src["feed"], BOT)
    br, rr = get(src["feed"], BROWSER)
    r = rb if bot == 200 else rr if br == 200 else None
    n = newest = undated = ""
    if r is not None:
        p = feedparser.parse(r.content)
        n = len(p.entries)
        dates = []
        undated = 0
        for e in p.entries:
            t = e.get("published_parsed") or e.get("updated_parsed")
            if t:
                dates.append(datetime(*t[:6], tzinfo=timezone.utc))
            else:
                undated += 1
        newest = max(dates).date().isoformat() if dates else "-"
        if r.url != src["feed"]:
            newest += f"  redirected to {r.url}"
    return f"{src['name']:<40} bot={bot!s:<22} browser={br!s:<22} entries={n!s:<4} undated={undated!s:<4} newest={newest}"


def main():
    sources = load_yaml("sources.yml")["blogs"]
    extra = os.environ.get("EXTRA_FEEDS", "").split()
    if extra:  # check only these URLs (for trying alternatives)
        sources = [{"name": u, "feed": u} for u in extra]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for line in pool.map(check, sources):
            print(line)


if __name__ == "__main__":
    main()
