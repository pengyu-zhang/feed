"""Have Gemini watch a few YouTube videos and report token usage.

Usage: GEMINI_API_KEY=... VIDEO_IDS="id1 id2" GEMINI_MODEL=... MEDIA_RES=LOW python gemini_probe.py
Prints the models available to the key, then for each video the token counts by
modality and the first part of Gemini's Chinese summary.
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

PROMPT = ("请看完这个视频，用自然的中文写：第一行一句话概括视频讲什么；然后 2 到 5 段，"
          "转述视频里的主要内容、论点、例子和结论。跳过赞助广告。只转述，不加自己的评价。")

models = requests.get(f"{BASE}/models?pageSize=200", headers=H, timeout=30).json()
names = [m["name"].split("/")[-1] for m in models.get("models", [])
         if "generateContent" in m.get("supportedGenerationMethods", [])]
print("MODELS:", ", ".join(n for n in names if "flash" in n or "lite" in n))

def video_part(vid):
    part = {"file_data": {"file_uri": f"https://www.youtube.com/watch?v={vid}"}}
    if FPS:
        part["video_metadata"] = {"fps": float(FPS)}
    return part


for i, vid in enumerate(os.environ.get("VIDEO_IDS", "").split()):
    if i:
        time.sleep(65)  # free tier: 250K input tokens per minute
    body = {
        "contents": [{"parts": [
            video_part(vid),
            {"text": PROMPT}]}],
        "generationConfig": {"mediaResolution": f"MEDIA_RESOLUTION_{RES}"},
    }
    t0 = time.time()
    r = requests.post(f"{BASE}/models/{MODEL}:generateContent", headers=H, json=body, timeout=600)
    dt = time.time() - t0
    if r.status_code != 200:
        print(f"VIDEO {vid}: HTTP {r.status_code} {r.text[:600]}")
        continue
    j = r.json()
    u = j.get("usageMetadata", {})
    detail = {d.get("modality"): d.get("tokenCount") for d in u.get("promptTokensDetails", [])}
    text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
    print(f"VIDEO {vid}: model={MODEL} res={RES} fps={FPS or 1} seconds={dt:.0f} prompt={u.get('promptTokenCount')} "
          f"output={u.get('candidatesTokenCount')} thoughts={u.get('thoughtsTokenCount', 0)} "
          f"total={u.get('totalTokenCount')} by_modality={json.dumps(detail)}")
    print("SUMMARY:", text[:1500].replace("\n", " / "))
