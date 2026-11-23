"""YouTube videos: the part of the daily digest that runs on the owner's PC, not on GitHub.

YouTube often refuses subtitle requests from cloud machines, so a scheduled task in the Claude
desktop app does this every morning while the PC is on. The task reads each transcript itself in
the app's browser (the "Show transcript" panel of the video page) and writes the summary itself;
this script does the mechanical parts around it. Python standard library plus PyYAML only.

    python scripts/youtube.py list      # which videos to summarise now -> work/youtube/todo.json
    (the task writes work/youtube/<video id>.json for each video, see below)
    python scripts/youtube.py save      # check those files, add the good ones to data/videos/<date>.json
    python scripts/youtube.py publish   # commit data/ and push (pull --rebase first)

What "list" picks: every video the channels published since the last run (the same rule as the
blogs: since the last successful run, never a fixed 24 hours, so nothing falls in a gap), plus
videos from earlier runs that are still waiting (their subtitles were not ready yet, or the cap
was reached). Newest first, at most `youtube.max_videos_per_run` (config.yml). Shorts are skipped.
A video waits at most `youtube.max_tries` runs and `max_catchup_hours`, then it is dropped.

The file the task writes for one video, work/youtube/<video id>.json, is either the JSON object
that prompts/video.md asks for (brief_zh, background_zh, points_zh, conclusion_zh, brief_en,
background_en, points_en, conclusion_en, topics), or {"no_transcript": true} when the page has
no transcript (yet).
"""

import json
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from common import (ROOT, VIDEO_STATE_FILE as STATE, VIDEO_STATUS_FILE as STATUS, VIDEOS, WORK, load_json,
                    load_yaml, local_date, now_utc, save_json)
from summarize import SUMMARY_FIELDS, as_paragraphs

# VIDEOS: data/videos/<date>.json, merged into the day pages by build.py
# STATE: last run, the waiting list, what is done; STATUS: per channel, for the Sources page
TODO_DIR = WORK / "youtube"
TODO = TODO_DIR / "todo.json"
NS = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/",
      "yt": "http://www.youtube.com/xml/schemas/2015"}
UA = {"User-Agent": "Mozilla/5.0 (feed digest; reads the public channel feeds)"}


def settings():
    cfg = load_yaml("config.yml")
    yt = cfg.get("youtube") or {}
    return cfg, yt.get("max_videos_per_run", 20), yt.get("max_tries", 3)


def read_channel(src):
    """All entries of one channel's official feed (the newest 15), or an error."""
    try:
        req = urllib.request.Request(src["feed"], headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"[:200]
    out = []
    for e in root.findall("a:entry", NS):
        link = e.find("a:link", NS).get("href", "")
        group = e.find("media:group", NS)
        out.append({
            "video_id": e.findtext("yt:videoId", "", NS),
            "title": e.findtext("a:title", "", NS),
            "url": link,
            "published": e.findtext("a:published", "", NS),
            "description": group.findtext("media:description", "", NS) if group is not None else "",
            "channel": src["name"],
            "channel_url": src.get("site", ""),
            "short": "/shorts/" in link,
        })
    return out, None


def cmd_list():
    cfg, cap, _ = settings()
    sources = [s for s in (load_yaml("sources.yml").get("youtube") or []) if s.get("feed")]
    state = load_json(STATE, {})
    done = state.get("done", {})
    waiting = state.get("waiting", {})
    old_status = load_json(STATUS, {})

    now = now_utc()
    oldest = now - timedelta(hours=cfg.get("max_catchup_hours", 168))
    last = state.get("last_run")
    since = max(datetime.fromisoformat(last) - timedelta(hours=1), oldest) if last else \
        now - timedelta(hours=cfg.get("first_run_hours", 26))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(read_channel, sources))

    status, new = {}, 0
    for src, (entries, err) in zip(sources, results):
        prev = old_status.get(src["name"], {})
        if err:
            status[src["name"]] = {**{k: v for k, v in prev.items() if k in ("ok", "last_post")}, "error": err}
            continue
        latest = max((x["published"] for x in entries), default=prev.get("last_post", ""))
        status[src["name"]] = {"ok": now.isoformat(), "last_post": latest}
        for v in entries:
            vid = v["video_id"]
            if v["short"] or not vid or vid in done or vid in waiting:
                continue
            if datetime.fromisoformat(v["published"]) > since:
                v["url"] = f"https://www.youtube.com/watch?v={vid}"
                waiting[vid] = {**v, "tries": 0}
                new += 1

    # drop what waited too long
    for vid in list(waiting):
        if datetime.fromisoformat(waiting[vid]["published"]) < oldest:
            waiting.pop(vid)

    todo = sorted(waiting.values(), key=lambda v: v["published"], reverse=True)[:cap]
    # summary files left by an unfinished earlier run stay: save picks them up
    save_json(TODO, {"listed_at": now.isoformat(),
                     "videos": [{k: v[k] for k in ("video_id", "url", "title", "channel", "published", "description")}
                                for v in todo]})
    state.update(last_run=now.isoformat(), waiting=waiting, done=done)
    save_json(STATE, state)
    save_json(STATUS, status)
    failed = sum(1 for s in status.values() if "error" in s)
    print(f"{len(sources)} channels read ({failed} failed), {new} new videos, {len(waiting)} waiting, "
          f"{len(todo)} to do now -> {TODO.relative_to(ROOT)}")
    for v in todo:
        print(f"  {v['video_id']}  {v['channel']}: {v['title']}")
    return 0


def check(reply):
    """The problems in one summary file, or [] when it can go on the page."""
    # background and conclusion may be empty for a very short source (prompts/common.md)
    problems = [k for k in SUMMARY_FIELDS if not isinstance(reply.get(k), str)]
    problems += [k for k in ("brief_zh", "brief_en") if k not in problems and not reply[k].strip()]
    problems += [k for k in ("points_zh", "points_en") if not as_paragraphs(reply.get(k))]
    return problems


def cmd_save():
    cfg, _, max_tries = settings()
    state = load_json(STATE, {})
    waiting, done = state.get("waiting", {}), state.get("done", {})
    date = local_date(cfg)
    day_file = VIDEOS / f"{date}.json"
    day = load_json(day_file, {"date": date, "items": []})
    known = {it["id"] for it in day["items"]}
    added, no_text, bad = [], [], []

    for vid, v in list(waiting.items()):
        f = TODO_DIR / f"{vid}.json"
        if not f.exists():
            continue  # not done in this run: it stays on the waiting list
        try:
            reply = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            reply, problems = {}, [f"not JSON ({e})"]
        else:
            problems = [] if reply.get("no_transcript") else check(reply)
        if reply.get("no_transcript") or problems:
            v["tries"] = v.get("tries", 0) + 1
            (no_text if reply.get("no_transcript") else bad).append(f"{vid} {', '.join(problems)}".strip())
            if v["tries"] >= max_tries:
                waiting.pop(vid)
                done[vid] = date
            f.unlink()
            continue
        item = {"id": f"yt-{vid}", "kind": "video", "source": v["channel"], "source_url": v["channel_url"],
                "title": v["title"], "url": v["url"], "published": v["published"], "basis": "transcript"}
        for k in SUMMARY_FIELDS:
            item[k] = reply[k].strip()
        item["points_zh"] = as_paragraphs(reply["points_zh"])
        item["points_en"] = as_paragraphs(reply["points_en"])
        item["topics"] = [t for t in (reply.get("topics") or []) if isinstance(t, str)]
        if item["id"] not in known:
            day["items"].append(item)
            known.add(item["id"])
        added.append(vid)
        waiting.pop(vid)
        done[vid] = date
        f.unlink()

    if added:
        day["items"].sort(key=lambda x: x["published"], reverse=True)
        day["generated_at"] = now_utc().isoformat()
        save_json(day_file, day)
    cutoff = (now_utc() - timedelta(days=45)).date().isoformat()
    state.update(waiting=waiting, done={k: d for k, d in done.items() if d >= cutoff})
    save_json(STATE, state)
    print(f"{date}: {len(added)} videos added, {len(no_text)} without transcript, {len(bad)} unusable, "
          f"{len(waiting)} still waiting")
    for line in no_text:
        print(f"  no transcript: {line}")
    for line in bad:
        print(f"  unusable (will retry): {line}")
    return 0


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def cmd_publish():
    cfg = load_yaml("config.yml")
    git("add", "data")
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("nothing to publish")
        return 0
    r = git("commit", "-m", f"youtube {local_date(cfg)}")
    if r.returncode:
        print(r.stdout, r.stderr, file=sys.stderr)
        return 1
    # the blog run on GitHub may have pushed meanwhile; it never writes these files, so this rebases cleanly
    for step in (("pull", "--rebase"), ("push",)):
        r = git(*step)
        if r.returncode:
            print(f"git {' '.join(step)} failed:\n{r.stdout}{r.stderr}", file=sys.stderr)
            return 1
    print("pushed; GitHub builds and deploys the site in a few minutes (workflow 'build')")
    return 0


if __name__ == "__main__":
    commands = {"list": cmd_list, "save": cmd_save, "publish": cmd_publish}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(__doc__)
        sys.exit(2)
    sys.exit(commands[sys.argv[1]]())
