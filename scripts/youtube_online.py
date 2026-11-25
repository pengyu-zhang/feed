"""YouTube on GitHub: Gemini gets each video's transcript, Claude writes the summary.

YouTube refuses subtitle requests from cloud machines, but the Gemini API can read a public
YouTube video itself. With content_layers=[TRANSCRIPT] it bills only the speech as text, no
frames. Gemini only hands over the transcript; the summary is written by Claude Sonnet from
prompts/video.md, the same way as the blogs.

    python youtube.py list        # new videos -> work/youtube/todo.json
    python youtube_online.py      # writes work/youtube/<video id>.json for each one it manages
    python youtube.py save        # adds them to data/videos/<date>.json

The transcript is used in memory only: never written to a file, never printed (the logs of a
public repository are public). A video Gemini refuses (403) counts as one failed try;
after youtube.max_tries runs (config.yml) it is dropped. A video it could not do because the
free tier was busy (503 "high demand") just waits for the next run, up to max_catchup_hours.

Needs GEMINI_API_KEY (AI Studio key) and CLAUDE_CODE_OAUTH_TOKEN.
"""

import json
import os
import sys
import time

from google import genai
from google.genai import types

from common import WORK, load_json, load_yaml
from summarize import ask_claude, load_prompt

TODO_DIR = WORK / "youtube"
TODO = TODO_DIR / "todo.json"
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
ROUNDS = 3            # tries per video over all models
WAIT = 45             # seconds between rounds after a 503
TIME_BUDGET = 35 * 60  # stop starting new videos after this, the rest waits for the next run
MAX_CHARS = 150_000   # a transcript longer than this is cut (a one-hour talk is about 60k characters)

ASK_TRANSCRIPT = ("Write out everything that is said in this video, in order, in the language it is "
                  "spoken in, as plain text. Keep every name, number and example. No timestamps, no "
                  "headings, no comments of your own.")
# used when the model refuses to repeat the speech word for word (finish reason RECITATION)
ASK_NOTES = ("Write detailed notes of everything that is said in this video, in order, in the language "
             "it is spoken in. Keep every name, number, example and argument; leave nothing out. Plain "
             "text, no comments of your own.")

client = genai.Client(http_options={"timeout": 600_000, "api_version": "v1beta"})


def gemini_text(model, url, ask):
    part = types.Part(file_data=types.FileData(file_uri=url, mime_type="video/mp4"),
                      video_metadata=types.VideoMetadata(
                          content_layers=[types.VideoMetadataContentLayer.TRANSCRIPT]))
    r = client.models.generate_content(model=model, contents=types.Content(parts=[part, types.Part(text=ask)]))
    reason = str(r.candidates[0].finish_reason) if r.candidates else "NO_CANDIDATE"
    return (r.text or "").strip(), reason


def transcript(url):
    """(text, None) or (None, short reason). Tries both models for a few rounds."""
    last = None
    for rnd in range(ROUNDS):
        for model in GEMINI_MODELS:
            try:
                text, reason = gemini_text(model, url, ASK_TRANSCRIPT)
                if "RECITATION" in reason or not text:
                    text, reason = gemini_text(model, url, ASK_NOTES)
                if text:
                    return text, None
                last = f"{model}: empty ({reason})"
            except Exception as e:  # noqa: BLE001
                last = f"{model}: {str(e)[:160]}"
                if "503" not in last and "UNAVAILABLE" not in last and "429" not in last:
                    return None, last  # a real error, retrying will not help
        if rnd < ROUNDS - 1:
            time.sleep(WAIT)
    return None, last


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set", file=sys.stderr)
        return 1
    cfg = load_yaml("config.yml")
    model = cfg["models"]["video"]
    videos = load_json(TODO, {}).get("videos", [])
    template = load_prompt("video")
    start, done, failed = time.time(), 0, 0
    for v in videos:
        out = TODO_DIR / f"{v['video_id']}.json"
        if out.exists():
            continue
        if time.time() - start > TIME_BUDGET:
            print(f"  time budget used, {v['video_id']} waits for the next run")
            continue
        t0 = time.time()
        text, err = transcript(v["url"])
        if text is None:
            failed += 1
            print(f"  {v['video_id']} {v['channel']}: no transcript this time ({err})")
            # a refusal (403 and the like) counts as one try; youtube.py save drops the video after
            # youtube.max_tries runs. "Busy" (503, 429) does not count: GitHub's late scheduled runs
            # land in the US daytime, when the free tier is often busy, and must not use up the tries.
            if not any(c in (err or "") for c in ("503", "UNAVAILABLE", "429")):
                out.write_text(json.dumps({"no_transcript": True}), encoding="utf-8")
            continue
        prompt = (template.replace("$TITLE", v["title"]).replace("$CHANNEL", v["channel"])
                  .replace("$DESCRIPTION", v.get("description") or "(none)").replace("$TRANSCRIPT", text[:MAX_CHARS]))
        try:
            reply = ask_claude(prompt, model)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  {v['video_id']} {v['channel']}: Claude failed ({str(e)[:160]})")
            continue
        out.write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        done += 1
        print(f"  {v['video_id']} {v['channel']}: done in {time.time() - t0:.0f}s "
              f"(transcript {len(text)} characters)")
    print(f"{done} videos summarised, {failed} left for the next run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
