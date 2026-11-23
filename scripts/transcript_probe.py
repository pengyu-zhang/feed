"""Summarise one YouTube transcript with Claude models, for comparison with Gemini watching the video.

The transcript arrives gzip+base64 in TRANSCRIPT_B64 (copied from the page's "Show transcript" panel).
It is only used in memory and never written to the repo or the log.
Prints one RESULT_JSON line per model in the same shape as gemini_probe.py.
"""

import base64
import gzip
import json
import os
import subprocess
import time

VID = os.environ["VIDEO_ID"]
TITLE = os.environ.get("VIDEO_TITLE", "")
CHANNEL = os.environ.get("VIDEO_CHANNEL", "")
MODELS = os.environ.get("MODELS", "claude-sonnet-5-5 claude-opus-5-5").split()
TEXT = gzip.decompress(base64.b64decode(os.environ["TRANSCRIPT_B64"])).decode("utf-8")

PROMPT = """You write a daily digest for one reader: a machine learning researcher whose first \
language is Chinese. He wants to understand this video well in Chinese without watching it. Below \
is the video's transcript. Auto-generated subtitles often misspell names; use the title and channel \
to get names right. Write:

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

Reply with ONLY a JSON object with keys "brief_zh", "detail_zh", "brief_en", "detail_en", "topics".

TITLE: {title}
CHANNEL: {channel}
TRANSCRIPT:
{text}
"""


def parse_json(s):
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(s[s.find("{"): s.rfind("}") + 1])


prompt = PROMPT.format(title=TITLE, channel=CHANNEL, text=TEXT)
print(f"VIDEO {VID}: transcript {len(TEXT)} characters")
for model in MODELS:
    cmd = ["claude", "-p", "--model", model, "--output-format", "json",
           "--disallowedTools", "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task",
           "Follow the instructions in the input exactly and reply with JSON only."]
    t0 = time.time()
    try:
        out = json.loads(subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                        timeout=600, check=True).stdout)
        summary = parse_json(out.get("result", ""))
        u = out.get("usage", {})
        usage = {"prompt": (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                            + u.get("cache_creation_input_tokens", 0)),
                 "output": u.get("output_tokens", 0)}
        res = {"model": model, "id": VID, "seconds": round(time.time() - t0), "usage": usage,
               "summary": summary, "via": "transcript"}
        print(f"VIDEO {VID}: model={model} seconds={res['seconds']} {json.dumps(usage)}")
    except Exception as e:
        res = {"model": model, "id": VID, "error": str(e)[:200]}
        print(f"VIDEO {VID}: model={model} ERROR {e}")
    print("RESULT_JSON " + json.dumps(res, ensure_ascii=False))
