"""TEMPORARY quick test (2026-11-23): one full video, three ways in parallel, one try each, no clipping.
Prints only our summaries and token counts, never transcript text. Delete after the test."""
import json, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
client = genai.Client(http_options={"timeout": 300_000, "api_version": "v1beta"})
VID = "eqe3ainzPtM"
URL = f"https://www.youtube.com/watch?v={VID}"
common = (ROOT / "prompts" / "common.md").read_text(encoding="utf-8").strip()
PROMPT = f"""Summarise this YouTube video for a Chinese-speaking ML researcher, from what is said in it.
TITLE: Why Would Anyone Learn to Code in 2027?
CHANNEL: Stefan Mischook

{common}

Reply with ONLY a JSON object with keys "brief_zh", "background_zh", "points_zh", "conclusion_zh", \
"brief_en", "background_en", "points_en", "conclusion_en", "topics"."""

CASES = [("transcript", "gemini-3.5-flash-lite"), ("agentic", "gemini-3.5-flash-lite")]


def run(case):
    mode, model = case
    kw = {"file_data": types.FileData(file_uri=URL, mime_type="video/mp4")}
    if mode == "transcript":
        kw["video_metadata"] = types.VideoMetadata(content_layers=[types.VideoMetadataContentLayer.TRANSCRIPT])
    if mode == "agentic":
        kw["media_processing"] = types.MediaProcessing.AGENTIC
    t0 = time.time()
    for attempt in range(4):
        try:
            return once(mode, model, kw, t0, attempt)
        except Exception as e:  # noqa: BLE001
            err = str(e).replace("\n", " ")[:600]
            if "503" not in err or attempt == 3:
                return {"case": f"{mode} {model}", "attempts": attempt + 1, "seconds": round(time.time() - t0), "error": err}
            time.sleep(60)


def once(mode, model, kw, t0, attempt):
    if True:
        r = client.models.generate_content(
            model=model, contents=types.Content(parts=[types.Part(**kw), types.Part(text=PROMPT)]),
            config=types.GenerateContentConfig(response_mime_type="application/json"))
        u = r.usage_metadata
        return {"case": f"{mode} {model}", "attempts": attempt + 1, "seconds": round(time.time() - t0),
                "usage_full": u.model_dump(exclude_none=True, mode="json"),
                "usage": {"prompt": u.prompt_token_count, "output": u.candidates_token_count,
                          "thoughts": u.thoughts_token_count, "total": u.total_token_count,
                          "by_modality": {str(d.modality): d.token_count for d in (u.prompt_tokens_details or [])}},
                "summary": json.loads(r.text)}


with ThreadPoolExecutor(2) as ex:
    for res in ex.map(run, CASES):
        print("RESULT_JSON " + json.dumps(res, ensure_ascii=False), flush=True)
