"""Try to download YouTube subtitles from GitHub's network, to see whether YouTube blocks it.

Usage: VIDEO_IDS="id1 id2" python yt_probe.py
"""

import os

from youtube_transcript_api import YouTubeTranscriptApi

api = YouTubeTranscriptApi()
for vid in os.environ.get("VIDEO_IDS", "").split():
    try:
        t = api.fetch(vid, languages=["en", "zh-Hans", "zh-Hant", "zh", "zh-CN", "zh-TW"])
        text = " ".join(s.text for s in t)
        print(f"{vid}: OK {len(text)} chars | {text[:200]}")
    except Exception as e:
        print(f"{vid}: FAIL {type(e).__name__} | {str(e)[:300]}")
