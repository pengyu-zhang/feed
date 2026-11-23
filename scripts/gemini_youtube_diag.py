"""TEMPORARY diagnostic (2026-11-23): which Gemini YouTube paths work at all? Small requests only.
Never prints transcript text. Delete after the test."""
import json, time
from google import genai
from google.genai import types

client = genai.Client(http_options={"timeout": 300_000, "api_version": "v1beta"})
URL = "https://www.youtube.com/watch?v=gXoqed9VdL8"
ASK = ("List the people's names and company names you hear or see in this clip, as a JSON list of strings. "
       "Nothing else.")


def part(mode, clip=True):
    meta = {}
    if clip:
        meta.update(start_offset="0s", end_offset="90s")
    if mode == "transcript":
        meta["content_layers"] = [types.VideoMetadataContentLayer.TRANSCRIPT]
    kw = {"file_data": types.FileData(file_uri=URL, mime_type="video/mp4" if mode == "agentic" else None)}
    if meta:
        kw["video_metadata"] = types.VideoMetadata(**meta)
    if mode == "agentic":
        kw["media_processing"] = types.MediaProcessing.AGENTIC
    return types.Part(**kw)


def usage(r):
    u = r.usage_metadata
    return {"prompt": u.prompt_token_count, "output": u.candidates_token_count, "total": u.total_token_count,
            "by_modality": {str(d.modality): d.token_count for d in (u.prompt_tokens_details or [])}}


CASES = [
    ("static", "gemini-3.5-flash-lite", True),
    ("transcript", "gemini-3.5-flash-lite", True),
    ("agentic", "gemini-3.5-flash-lite", True),
    ("static", "gemini-3.6-flash", True),
    ("transcript", "gemini-3.6-flash", True),
    ("agentic", "gemini-3.6-flash", True),
]
for mode, model, clip in CASES:
    for attempt in range(2):
        t0 = time.time()
        try:
            r = client.models.generate_content(model=model, contents=types.Content(parts=[part(mode, clip), types.Part(text=ASK)]))
            print(f"CASE {mode} {model}: OK {time.time()-t0:.0f}s usage={json.dumps(usage(r))} answer={(r.text or '')[:400]!r}")
            break
        except Exception as e:  # noqa: BLE001
            msg = str(e).replace("\n", " ")[:1500]
            print(f"CASE {mode} {model}: attempt {attempt+1} after {time.time()-t0:.0f}s ERROR {msg}")
            if "503" not in msg:
                break
            time.sleep(30)
    time.sleep(15)
