"""Step 2: write Chinese and English summaries with Claude, then pick the day's highlights.

Runs the Claude Code CLI (`claude -p`) authenticated by CLAUDE_CODE_OAUTH_TOKEN, so it uses
the owner's Claude subscription. Writes data/days/<date>.json and updates data/state.json.
Set FEED_FAKE_LLM=1 to skip Claude and fill placeholders (for local testing).
"""

import json
import os
import re
import subprocess
import sys
from datetime import timedelta

from common import (DAYS, ITEMS_FILE, STATE_FILE, load_json, load_yaml, local_date,
                    now_utc, save_json)

FAKE = os.environ.get("FEED_FAKE_LLM") == "1"

SUMMARY_PROMPT = """You write a daily reading digest for one reader: a machine learning researcher \
whose first language is Chinese. He wants to understand each post well in Chinese without opening \
the original. Below are {n} new blog posts. For each post write:

- "brief_zh": one sentence in natural Chinese saying what the post is about and its main point.
- "detail_zh": a list of 2 to 5 Chinese paragraphs that retell the post in your own words: the \
question or situation, the main arguments or findings, the key examples, numbers or steps, and the \
author's conclusion. Scale the length to the post: a short link post gets one paragraph, a long \
essay gets four or five. Do not translate sentence by sentence and do not quote long passages; \
explain it the way a well-read friend would. Keep names, product names and technical terms in \
their original form where that is clearer.
- "brief_en" and "detail_en": the same in plain, short English sentences. No em dashes.
- "topics": 1-3 short English topic tags.

Chinese style: plain spoken Chinese, not translated-sounding, no hype, no filler such as \
"本文介绍了" or "总的来说", Chinese full-width punctuation. If a post is only a short link or \
quote, explain what it points to and why the author shared it. If the text is cut off, cover what \
is there and do not invent the rest.

Reply with ONLY a JSON array, one object per post, in the same order, each with keys \
"id", "brief_zh", "detail_zh", "brief_en", "detail_en", "topics". No other text.

POSTS:
{posts}
"""

PICKS_PROMPT = """You are choosing highlights for a daily reading digest. The reader is a machine \
learning researcher (knowledge graphs, recommender systems, temporal and multimodal ML) who also \
reads widely beyond AI.

Today's posts (id, source, title, summary, topics):
{posts}

Pick two separate lists, with no post in both:
1. "important": up to {k} posts that matter most today for anyone following tech and AI, \
whether or not they fit the reader's interests (big news, widely discussed ideas, strong essays).
2. "liked": up to {k} posts this reader is most likely to enjoy, based on these interests:
{interests}

Reply with ONLY JSON: {{"important": ["id", ...], "liked": ["id", ...]}}, best first. No other text.
"""


def ask_claude(prompt, model):
    """Send one prompt through the Claude Code CLI and return the parsed JSON reply."""
    cmd = ["claude", "-p", "--model", model, "--output-format", "json",
           "--disallowedTools", "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task",
           "Follow the instructions in the input exactly and reply with JSON only."]
    last_err = None
    for _ in range(2):
        try:
            out = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                 timeout=600, check=True).stdout
            reply = json.loads(out).get("result", "")
            return parse_json(reply)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"claude failed: {last_err}")


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0], default=0)
    return json.loads(text[start:])


def as_paragraphs(x):
    if isinstance(x, str):
        x = [p for p in x.split("\n") if p.strip()]
    return [p.strip() for p in (x or []) if isinstance(p, str) and p.strip()]


def summarize(items, cfg):
    size = cfg.get("summary_batch_size", 4)
    limit = cfg.get("max_chars_per_item", 20000)
    model = cfg["models"]["summary"]
    for i in range(0, len(items), size):
        batch = items[i:i + size]
        if FAKE:
            for it in batch:
                it.update(brief_zh=f"[测试] {it['title']} 的一句话概括。",
                          detail_zh=["[测试] 第一段详细介绍。", "[测试] 第二段详细介绍。"],
                          brief_en=f"[Test] One-line summary of {it['title']}.",
                          detail_en=["[Test] First paragraph.", "[Test] Second paragraph."],
                          topics=["test"])
            continue
        posts = "\n\n".join(
            f"### id: {it['id']}\nsource: {it['source']}\ntitle: {it['title']}\n"
            f"text:\n{it['text'][:limit]}" for it in batch)
        try:
            reply = ask_claude(SUMMARY_PROMPT.format(n=len(batch), posts=posts), model)
            by_id = {r.get("id"): r for r in reply if isinstance(r, dict)}
            for it in batch:
                r = by_id.get(it["id"], {})
                it["brief_zh"] = (r.get("brief_zh") or "").strip()
                it["brief_en"] = (r.get("brief_en") or "").strip()
                it["detail_zh"] = as_paragraphs(r.get("detail_zh"))
                it["detail_en"] = as_paragraphs(r.get("detail_en"))
                it["topics"] = r.get("topics") or []
        except Exception as e:
            print(f"summary batch {i // size} failed: {e}", file=sys.stderr)


def pick(items, cfg):
    k = cfg.get("picks_per_column", 3)
    usable = [it for it in items if it.get("brief_en")]
    if not usable:
        return {"important": [], "liked": []}
    if FAKE:
        return {"important": [it["id"] for it in usable[:k]],
                "liked": [it["id"] for it in usable[k:2 * k]]}
    posts = "\n".join(
        f"- {it['id']} | {it['source']} | {it['title']} | {it['brief_en']} | "
        f"{', '.join(it.get('topics', []))}" for it in usable)
    interests = "\n".join(f"- {x}" for x in cfg.get("interests", []))
    try:
        reply = ask_claude(PICKS_PROMPT.format(posts=posts, k=k, interests=interests),
                           cfg["models"]["picks"])
    except Exception as e:
        print(f"picks failed: {e}", file=sys.stderr)
        return {"important": [], "liked": []}
    ids = {it["id"] for it in usable}
    out, used = {}, set()
    for col in ("important", "liked"):
        out[col] = []
        for p in reply.get(col, []):
            pid = p.get("id") if isinstance(p, dict) else p
            if pid in ids and pid not in used and len(out[col]) < k:
                used.add(pid)
                out[col].append(pid)
    return out


def main():
    cfg = load_yaml("config.yml")
    work = load_json(ITEMS_FILE, None)
    if work is None:
        print("no work/items.json: run fetch.py first", file=sys.stderr)
        return 1
    new = work["items"]
    summarize(new, cfg)

    date = local_date(cfg)
    day_file = DAYS / f"{date}.json"
    day = load_json(day_file, {"date": date, "items": []})
    known = {it["id"] for it in day["items"]}
    for it in new:
        if it["id"] not in known:
            day["items"].append({k: v for k, v in it.items() if k not in ("text", "undated")})  # never publish article text
    day["items"].sort(key=lambda x: x["published"], reverse=True)
    day["picks"] = pick(day["items"], cfg)
    day["generated_at"] = now_utc().isoformat()
    save_json(day_file, day)

    state = load_json(STATE_FILE, {})
    seen = state.get("seen", {})
    forever = set(state.get("seen_undated", []))  # links from feeds without dates: never forget
    for it in new:
        seen[it["url"]] = date
        if it.get("undated"):
            forever.add(it["url"])
    forever.update(work.get("quiet_urls", []))
    cutoff = (now_utc() - timedelta(days=45)).date().isoformat()
    state["seen"] = {u: d for u, d in seen.items() if d >= cutoff}
    state["seen_undated"] = sorted(forever)
    state["baselined"] = sorted(set(state.get("baselined", [])) | set(work.get("baselined", [])))
    state["last_run"] = work["run_at"]
    save_json(STATE_FILE, state)
    done = sum(1 for it in new if it.get("brief_zh"))
    print(f"{date}: {done}/{len(new)} summarised, day now has {len(day['items'])} posts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
