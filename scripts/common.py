"""Shared paths and helpers for the daily feed pipeline."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DAYS = DATA / "days"
WORK = ROOT / "work"          # scratch, not committed (holds article text)
SITE = ROOT / "site"          # build output, deployed to GitHub Pages
STATE_FILE = DATA / "state.json"
STATUS_FILE = DATA / "sources_status.json"
# YouTube, written on the owner's PC by youtube.py, never by the GitHub runs
VIDEOS = DATA / "videos"
VIDEO_STATE_FILE = DATA / "youtube_state.json"
VIDEO_STATUS_FILE = DATA / "youtube_status.json"
ITEMS_FILE = WORK / "items.json"


def load_yaml(name):
    with open(ROOT / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    tmp.replace(path)


def now_utc():
    return datetime.now(timezone.utc)


def local_date(cfg, dt=None):
    tz = ZoneInfo(cfg.get("timezone", "Europe/Amsterdam"))
    return (dt or now_utc()).astimezone(tz).date().isoformat()


_CJK = re.compile(r"[㐀-鿿]")


def read_minutes(text):
    """Rough reading time: 230 English words or 450 CJK characters per minute."""
    if not text:
        return None
    cjk = len(_CJK.findall(text))
    words = len(re.findall(r"[A-Za-z0-9']+", text))
    minutes = cjk / 450 + words / 230
    return max(1, round(minutes))
