"""Have Gemini watch a few YouTube videos and report token usage.

Usage: GEMINI_API_KEY=... VIDEO_IDS="id1 id2" GEMINI_MODEL=... MEDIA_RES=LOW FPS=0.05 python gemini_probe.py
For each video prints the token counts by modality, then one line starting with RESULT_JSON
holding the summary in the same shape the site uses (brief_zh, detail_zh, brief_en, detail_en).
"""

import json
import os
import time

import requests

KEY = os.environ["GEMINI_API_KEY"]
BASE = "https://generativelanguage.googleapis.com/v1beta"
H = {"x-goog-api-key": KEY, "Content-Type": "application/json"}
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
RES = os.environ.get("MEDIA_RES", "LOW")
FPS = os.environ.get("FPS", "").strip()

PROMPT = """You write a daily digest for one reader: a machine learning researcher whose first \
language is Chinese. He wants to understand this video well in Chinese without watching it. \
Listen to what is said and look at what is shown. Write:

- "brief_zh": one sentence in natural Chinese saying what the video is about and its main point.
- "detail_zh": a list of 2 to 5 Chinese paragraphs that retell the video in your own words: the \
question or situation, the main arguments or findings, the key examples, numbers or steps, and the \
speakers' conclusions. Scale the length to the content: a short clip gets one or two paragraphs, a \
long interview gets four or five. For an interview, say who the guest is and what they argue. Do not \
transcribe and do not quote long passages. Keep names, product names and technical terms in their \
original form where that is clearer. Skip sponsor reads and channel promotion. Only report what the \
video says: do not add your own judgement or commentary.
- "brief_en" and "detail_en": the same in plain, short English sentences. No em dashes.
- "topics": 1-3 short English topic tags.

Chinese style: plain spoken Chinese, not translated-sounding, no hype, no filler such as \
"本视频介绍了" or "总的来说", Chinese full-width punctuation, simplified characters even if the \
video uses traditional ones.

Reply with ONLY a JSON object with keys "brief_zh", "detail_zh", "brief_en", "detail_en", "topics"."""


def video_part(vid):
    part = {"file_data": {"file_uri": f"https://www.youtube.com/watch?v={vid}"}}
    if FPS:
        part["video_metadata"] = {"fps": float(FPS)}
    return part


for i, vid in enumerate(os.environ.get("VIDEO_IDS", "").split()):
    if i:
        time.sleep(65)  # free tier: 250K input tokens per minute
    body = {
        "contents": [{"parts": [video_part(vid), {"text": PROMPT}]}],
        "generationConfig": {"mediaResolution": f"MEDIA_RESOLUTION_{RES}",
                             "responseMimeType": "application/json"},
    }
    t0 = time.time()
    r = requests.post(f"{BASE}/models/{MODEL}:generateContent", headers=H, json=body, timeout=900)
    dt = time.time() - t0
    if r.status_code != 200:
        print(f"VIDEO {vid}: HTTP {r.status_code} {r.text[:600]}")
        print("RESULT_JSON " + json.dumps({"model": MODEL, "id": vid, "error": f"HTTP {r.status_code}"}))
        continue
    j = r.json()
    u = j.get("usageMetadata", {})
    detail = {d.get("modality"): d.get("tokenCount") for d in u.get("promptTokensDetails", [])}
    text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"]
                   if not p.get("thought"))
    usage = {"prompt": u.get("promptTokenCount"), "output": u.get("candidatesTokenCount"),
             "thoughts": u.get("thoughtsTokenCount", 0), "total": u.get("totalTokenCount"),
             "by_modality": detail}
    print(f"VIDEO {vid}: model={MODEL} res={RES} fps={FPS or 1} seconds={dt:.0f} {json.dumps(usage)}")
    try:
        summary = json.loads(text)
    except ValueError:
        summary = {"raw": text}
    print("RESULT_JSON " + json.dumps({"model": MODEL, "id": vid, "seconds": round(dt),
                                       "fps": FPS or "1", "res": RES, "usage": usage,
                                       "summary": summary}, ensure_ascii=False))
