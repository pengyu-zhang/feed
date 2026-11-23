"""Rewrite the summaries of past days with the current prompt (prompts/blog.md).

Usage: python resummarize.py [YYYY-MM-DD ...]   (no dates = every day in data/days)
Fetches each blog post's text again, only in memory, and never stores it. Video items are left
alone: their transcripts are not available here.
"""

import sys

from common import DAYS, load_json, load_yaml, save_json
from fetch import page_text
from summarize import summarize


def main(dates):
    cfg = load_yaml("config.yml")
    files = [DAYS / f"{d}.json" for d in dates] if dates else sorted(DAYS.glob("*.json"))
    for f in files:
        day = load_json(f, None)
        if not day:
            continue
        blogs = [it for it in day["items"] if it.get("kind") != "video"]
        todo = []
        for it in blogs:
            text = page_text(it["url"])
            if len(text) < 200:
                print(f"{f.stem}: no text for {it['url']}, keeping the old summary")
                continue
            it["text"] = text
            todo.append(it)
        summarize(todo, cfg)
        for it in todo:
            it.pop("text", None)  # never publish article text
        if not cfg.get("picks_enabled", True):
            day["picks"] = {"important": [], "liked": []}
        save_json(f, day)
        done = sum(1 for it in todo if it.get("points_zh"))
        print(f"{f.stem}: rewrote {done}/{len(blogs)} blog summaries")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
