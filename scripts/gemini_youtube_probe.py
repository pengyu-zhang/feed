"""TEMPORARY test (2026-11-23): can Gemini summarise a YouTube video from its transcript layer?

Runs each video through several modes and prints, per run, one RESULT_JSON line with the four-part
summary (same fields as prompts/video.md), token usage and seconds. Transcript text itself is never
printed: the provenance check prints only which spellings occur. Delete this file after the test.
"""

import json
import os
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
client = genai.Client(http_options={"timeout": 600_000, "api_version": "v1beta"})

VIDEOS = [
    {"id": "eqe3ainzPtM", "title": "Why Would Anyone Learn to Code in 2027?", "channel": "Stefan Mischook",
     "description": "Developer Bootcamp & Mentoring Program (unclestef.com). #LearnToCode #AI #Programming"},
    {"id": "Hy7iE1iLmxw", "title": "別再省著用了！退訂 Claude 後，我開始了 Token 揮霍無度的人生", "channel": "HC AI說人話",
     "description": "比較 Claude、GPT 與高性價比開源模型（MiniMax、Kimi），並示範用 Codex、Ollama、Open Code、Hermes Agent、Pi agent 安裝與設定 AI Agent。"},
    {"id": "gXoqed9VdL8", "title": "Entity Resolution at Scale: Graphs, LLMs, and Real-World Data Messiness",
     "channel": "Data Engineering Podcast",
     "description": "In this episode, I spoke with Steven Renwick, CEO and co-founder of Tilores, about the realities of entity-oriented data processing and the practical role of LLMs in entity resolution."},
]

MODES = [
    ("transcript-only", "gemini-3.5-flash-lite"),
    ("agentic", "gemini-3.5-flash-lite"),
]

common = (ROOT / "prompts" / "common.md").read_text(encoding="utf-8").strip()
PROMPT = f"""You write a daily digest for one reader: a machine learning researcher whose first language is \
Chinese. He wants to understand this YouTube video well in Chinese without watching it. Use what is said in \
the video (its transcript). Auto-generated subtitles often misspell names: use the title and description to \
get names right; if you cannot, keep the spelling you hear and do not guess.

{common}

Reply with ONLY a JSON object with keys "brief_zh", "background_zh", "points_zh", "conclusion_zh", \
"brief_en", "background_en", "points_en", "conclusion_en", "topics". No other text.
"""


def video_part(vid, mode, start=None, end=None):
    url = f"https://www.youtube.com/watch?v={vid}"
    meta = {}
    if mode == "transcript-only":
        meta["content_layers"] = [types.VideoMetadataContentLayer.TRANSCRIPT]
    if start is not None:
        meta["start_offset"], meta["end_offset"] = f"{start}s", f"{end}s"
    kw = {"file_data": types.FileData(file_uri=url, mime_type="video/mp4" if mode == "agentic" else None)}
    if meta:
        kw["video_metadata"] = types.VideoMetadata(**meta)
    if mode == "agentic":
        kw["media_processing"] = types.MediaProcessing.AGENTIC
    return types.Part(**kw)


def usage_of(r):
    u = r.usage_metadata
    if not u:
        return {}
    return {"prompt": u.prompt_token_count, "output": u.candidates_token_count,
            "thoughts": u.thoughts_token_count, "total": u.total_token_count,
            "by_modality": {str(d.modality): d.token_count for d in (u.prompt_tokens_details or [])}}


def call(model, parts, json_out=True):
    cfg = types.GenerateContentConfig(response_mime_type="application/json") if json_out else None
    for attempt in range(2):
        try:
            t0 = time.time()
            r = client.models.generate_content(model=model, contents=types.Content(parts=parts), config=cfg)
            return r, time.time() - t0, None
        except Exception as e:  # noqa: BLE001
            err = str(e)[:300]
            print(f"  attempt {attempt + 1}: {err}")
            if not any(c in err for c in ("503", "500", "UNAVAILABLE")):
                return None, 0, err
            time.sleep(30)
    return None, 0, err


# 2. Summaries
for model_mode, model in MODES:
    for v in VIDEOS:
        header = f"TITLE: {v['title']}\nCHANNEL: {v['channel']}\nDESCRIPTION:\n{v['description']}"
        parts = [video_part(v["id"], model_mode), types.Part(text=PROMPT + "\n" + header)]
        r, dt, err = call(model, parts)
        res = {"mode": model_mode, "model": model, "id": v["id"]}
        if err:
            res["error"] = err
        else:
            res.update({"seconds": round(dt), "usage": usage_of(r)})
            try:
                res["summary"] = json.loads(r.text)
            except Exception:  # noqa: BLE001
                res["summary"] = {"raw": (r.text or "")[:3000]}
            tools = [p.tool_call.tool_type if p.tool_call else None
                     for c in (r.candidates or []) for p in (c.content.parts or []) if getattr(p, "tool_call", None)]
            res["tool_calls"] = [str(t) for t in tools]
        print(f"RUN {model_mode} {model} {v['id']}: seconds={res.get('seconds')} usage={json.dumps(res.get('usage'))} "
              f"error={res.get('error')}")
        print("RESULT_JSON " + json.dumps(res, ensure_ascii=False))
        time.sleep(20)
