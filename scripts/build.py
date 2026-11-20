"""Step 3: render the static site from data/ into site/.

Pages: index.html (latest day), <date>.html (every day), archive.html, sources.html.
Every visible string is written in both Chinese and English; the page shows one at a time.
"""

import re
import shutil
import sys
from datetime import date as Date
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from common import DAYS, ROOT, SITE, STATUS_FILE, load_json, load_yaml

WEEKDAY_ZH = "一二三四五六日"
FONTS = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500"
         "&family=IBM+Plex+Sans:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&display=swap")

MOON = ('<svg class="icon--moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>')
SUN = ('<svg class="icon--sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
       'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="5"/>'
       '<line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>'
       '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
       '<line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>'
       '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>')

# Runs before first paint so the page never flashes the wrong theme or language.
PREPAINT = """<script>(function(){var r=document.documentElement,t=null,l=null;
try{t=localStorage.getItem('theme');l=localStorage.getItem('feed-lang');}catch(e){}
if(t!=='light'&&t!=='dark'){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
r.dataset.theme=t;r.dataset.lang=(l==='en')?'en':'zh';if(l==='en')r.lang='en';})();</script>"""


def bi(zh, en):
    """Both languages, CSS shows the one picked."""
    return f'<span data-l="zh">{escape(zh)}</span><span data-l="en" lang="en">{escape(en)}</span>'


def date_label(iso):
    d = Date.fromisoformat(iso)
    zh = f"{d.month} 月 {d.day} 日 · 周{WEEKDAY_ZH[d.weekday()]}"
    en = f"{d.strftime('%A')}, {d.day} {d.strftime('%B')}"
    return zh, en


def page(title_zh, title_en, active, body):
    tabs = [("index.html", "今天", "Today"), ("archive.html", "往期", "Archive"),
            ("sources.html", "来源", "Sources")]
    nav = "".join(
        f'<li><a class="tabbar__tab{" is-active" if href == active else ""}" href="{href}"'
        f'{" aria-current=\"page\"" if href == active else ""}>{bi(zh, en)}</a></li>'
        for href, zh, en in tabs)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title_en)} · Feed</title>
{PREPAINT}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<div class="wrap">
<nav class="tabbar" aria-label="Feed">
<ul class="tabbar__tabs">{nav}</ul>
<button type="button" id="lang-toggle" class="icon-btn" aria-label="切换语言 / Switch language" title="切换语言 / Switch language"><span data-l="zh">EN</span><span data-l="en">中</span></button>
<button type="button" id="theme-toggle" class="icon-btn" aria-label="切换亮色和暗色 / Toggle light and dark" title="切换亮色和暗色 / Toggle light and dark">{MOON}{SUN}</button>
</nav>
<main style="display:flex;flex-direction:column;gap:1.5em">
{body}
</main>
<footer>{bi("摘要由模型生成，可能有误，以原文为准。每条都附原文链接。",
             "Summaries are machine-written and may be wrong. The original is the source of truth; every item links to it.")}</footer>
</div>
<script src="assets/app.js"></script>
</body>
</html>
"""


def paragraphs(items):
    if isinstance(items, str):  # models sometimes return one string instead of a list
        items = [x.strip() for x in re.split(r"\n\s*\n", items) if x.strip()]
    return "".join(f"<p>{escape(x)}</p>" for x in items)


def item_html(it, compact=False, detail=True):
    kind = bi("博客", "Blog") if it.get("kind") == "blog" else bi("视频", "Video")
    src = escape(it["source"])
    if it.get("source_url"):
        src = f'<a class="src" href="{escape(it["source_url"])}" target="_blank" rel="noopener">{src}</a>'
    else:
        src = f'<span class="src">{src}</span>'
    meta = [f'<span class="kind">{kind}</span>', src]
    if compact and it.get("basis") == "short":
        meta.append(f"<span>{bi('原文较短', 'short source text')}</span>")
    brief_zh = it.get("brief_zh") or it.get("summary_zh") or ""
    brief_en = it.get("brief_en") or it.get("summary_en") or ""
    if brief_zh or brief_en:
        brief = bi(brief_zh or brief_en, brief_en or brief_zh)
    else:
        brief = bi("这条没有生成摘要，点标题看原文。", "No summary for this one. Open the title to read the original.")
    out = [f'<article class="item"><div class="meta">{"".join(meta)}</div>',
           f'<a class="title" href="{escape(it["url"])}" target="_blank" rel="noopener">{escape(it["title"])}</a>',
           f'<p class="brief">{brief}</p>']
    dz, de = it.get("detail_zh") or [], it.get("detail_en") or []
    if detail and (dz or de):
        out.append(f'<div class="detail"><div data-l="zh">{paragraphs(dz or de)}</div>'
                   f'<div data-l="en" lang="en">{paragraphs(de or dz)}</div></div>')
    out.append("</article>")
    return "".join(out)


def day_body(day):
    items = {it["id"]: it for it in day["items"]}
    zh, en = date_label(day["date"])
    n = len(day["items"])
    sources = len({it["source"] for it in day["items"]})
    gen = day.get("generated_at")
    when = ""
    if gen:
        t = datetime.fromisoformat(gen).astimezone(ZoneInfo("Europe/Amsterdam")).strftime("%H:%M")
        when = t
    head = (f'<header class="card page-head"><div class="label label--accent">Feed</div>'
            f'<h1>{bi(zh, en)}</h1><p class="muted">'
            f'{bi(f"{sources} 个来源更新了 {n} 篇" + (f" · {when} 更新" if when else ""), f"{n} posts from {sources} sources" + (f" · updated {when}" if when else ""))}'
            f"</p></header>")

    def column(key, label, title, sub):
        ids = [p["id"] if isinstance(p, dict) else p for p in day.get("picks", {}).get(key, [])]
        inner = "".join(item_html(items[i]) for i in ids if i in items) or \
            f'<p class="empty">{bi("今天没有挑出来的。", "Nothing picked today.")}</p>'
        return (f'<section class="card" aria-label="{escape(title[1])}"><div class="label">{bi(*label)}</div>'
                f'<h2 class="col-title">{bi(*title)}</h2><p class="muted small">{bi(*sub)}</p>{inner}</section>')

    cols = ('<div class="cols">'
            + column("important", ("热门", "Trending"), ("该知道的", "Worth knowing"),
                     ("今天圈子里最受关注的，不管你平时看不看", "What people are talking about today, your usual topics or not"))
            + column("liked", ("为你挑选", "For you"), ("可能喜欢", "You might like"),
                     ("按你的兴趣挑的。打分功能上线后改按你的历史", "Picked by your interests; by your ratings once rating is added"))
            + "</div>")
    picked = {p["id"] if isinstance(p, dict) else p
              for col in day.get("picks", {}).values() for p in col}
    # posts already shown in full in the two columns above: title and one line only here
    listing = "".join(item_html(it, compact=True, detail=it["id"] not in picked)
                      for it in day["items"]) or \
        f'<p class="empty">{bi("这段时间没有新文章。", "No new posts in this period.")}</p>'
    all_sec = (f'<section class="card list"><h2 class="section-title">{bi("全部更新", "All updates")}'
               f' <span class="muted" style="font-weight:400">{n}</span></h2>{listing}</section>')
    return head + cols + all_sec


def archive_body(days):
    rows = "".join(
        f'<li><a href="{d["date"]}.html">{bi(*date_label(d["date"]))}</a>'
        f'<span class="muted">{bi(f"{len(d["items"])} 篇", f"{len(d["items"])} posts")}</span></li>'
        for d in days)
    return (f'<section class="card"><h1 class="section-title">{bi("往期", "Archive")}</h1>'
            f'<ul class="days">{rows}</ul></section>')


def source_rows(sources, status, connected=True):
    rows = []
    for s in sources:
        st = status.get(s["name"], {})
        last = st.get("last_post", "")[:10]
        if not connected:
            ok, cls = bi("还没接入", "not connected yet"), ' class="muted"'
        elif "error" in st:
            ok, cls = bi("抓取失败", "failed"), ' class="bad"'
        elif st.get("ok"):
            ok, cls = bi("正常", "ok"), ""
        else:
            ok, cls = bi("还没抓过", "not yet"), ' class="muted"'
        href = s.get("site") or s.get("feed")
        rows.append(f'<tr><td><a href="{escape(href)}" target="_blank" rel="noopener">'
                    f'{escape(s["name"])}</a></td><td class="muted">{escape(last)}</td><td{cls}>{ok}</td></tr>')
    return "".join(rows)


def source_table(title, note, rows, count):
    return (f'<h2 class="col-title" style="margin-top:1.4em">{bi(*title)}'
            f' <span class="muted" style="font-weight:400">{count}</span></h2>'
            f'<p class="muted small">{bi(*note)}</p>'
            f'<div class="table-scroll"><table class="sources"><thead><tr><th>{bi("名字", "Name")}</th>'
            f'<th>{bi("最近一篇", "Latest post")}</th><th>{bi("状态", "Status")}</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def sources_body(groups, status):
    blogs, videos = groups.get("blogs", []), groups.get("youtube", [])
    total = len(blogs) + len(videos)
    return (f'<section class="card"><h1 class="section-title">{bi("来源", "Sources")}'
            f' <span class="muted" style="font-weight:400">{total}</span></h1>'
            + source_table(("博客", "Blogs"),
                           ("Lil’Log，加上 Karpathy 推荐的 Hacker News 热门博客。",
                            "Lil’Log plus the popular Hacker News blogs Karpathy recommended."),
                           source_rows(blogs, status), len(blogs))
            + (source_table(("YouTube", "YouTube"),
                            ("已经列进来源，还没开始抓取。", "Listed, not fetched yet."),
                            source_rows(videos, status, connected=False), len(videos)) if videos else "")
            + "</section>")


MODEL_NAMES = {"gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite", "gemini-3.6-flash": "Gemini 3.6 Flash",
               "gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
               "gemini-3.8-flash": "Gemini 3.8 Flash"}


def yt_test_body(test):
    """Test page: each video summarised by several Gemini models, in the normal item style."""
    models = test["models"]
    res = {(r["model"], r["id"]): r for r in test["results"]}
    head = (f'<header class="card page-head"><div class="label label--accent">{bi("测试", "Test")}</div>'
            f'<h1>{bi("YouTube 视频摘要测试", "YouTube summary test")}</h1>'
            f'<p class="muted">{bi(test["note_zh"], test["note_en"])}</p></header>')
    rows = []
    for v in test["videos"]:
        cells = []
        for m in models:
            r = res.get((m, v["id"]), {})
            u = r.get("usage") or {}
            cells.append(f'<td>{u.get("prompt", 0) / 1000:.0f}K · {r.get("seconds", "?")}s</td>'
                         if u else f'<td class="bad">{escape(r.get("error", "—"))}</td>')
        rows.append(f'<tr><td>{bi(v["type_zh"], v["type_en"])}<br><span class="muted">'
                    f'{v["minutes"]:.0f} min</span></td>{"".join(cells)}</tr>')
    table = (f'<section class="card"><h2 class="col-title">{bi("用量", "Usage")}</h2>'
             f'<p class="muted small">{bi("输入 token · 出结果用的秒数", "input tokens · seconds to answer")}</p>'
             f'<div class="table-scroll"><table class="sources"><thead><tr><th>{bi("视频", "Video")}</th>'
             + "".join(f"<th>{escape(MODEL_NAMES.get(m, m))}</th>" for m in models)
             + f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>')
    cards = []
    for v in test["videos"]:
        items = []
        for m in models:
            r = res.get((m, v["id"]), {})
            if "error" in r or not r:
                items.append(f'<div class="label" style="margin-top:1.4em">{escape(MODEL_NAMES.get(m, m))}</div>'
                             f'<p class="muted">{bi("没有结果：", "No result: ")}{escape(r.get("error", "—"))}</p>')
                continue
            sm = r.get("summary") or {}
            it = {"kind": "video", "source": v["channel"], "source_url": v["channel_url"],
                  "url": f'https://www.youtube.com/watch?v={v["id"]}', "title": v["title"],
                  "brief_zh": sm.get("brief_zh", ""), "brief_en": sm.get("brief_en", ""),
                  "detail_zh": sm.get("detail_zh") or [], "detail_en": sm.get("detail_en") or []}
            items.append(f'<div class="label" style="margin-top:1.4em">{escape(MODEL_NAMES.get(m, m))}</div>'
                         + item_html(it))
        cards.append(f'<section class="card"><div class="label label--accent">{bi(v["type_zh"], v["type_en"])}'
                     f' · {v["minutes"]:.0f} min</div>{"".join(items)}</section>')
    return head + table + "".join(cards)


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "assets").mkdir(parents=True)
    for f in (ROOT / "assets").iterdir():
        shutil.copy(f, SITE / "assets" / f.name)

    days = sorted((load_json(p, None) for p in DAYS.glob("*.json")), key=lambda d: d["date"], reverse=True)
    days = [d for d in days if d]
    for d in days:
        zh, en = date_label(d["date"])
        (SITE / f"{d['date']}.html").write_text(page(zh, en, "", day_body(d)), encoding="utf-8")
    if days:
        latest = days[0]
        zh, en = date_label(latest["date"])
        index = page(zh, en, "index.html", day_body(latest))
    else:
        index = page("还没有内容", "Nothing yet", "index.html",
                     f'<section class="card"><p>{bi("第一次运行之后这里就有内容了。", "Content appears after the first run.")}</p></section>')
    (SITE / "index.html").write_text(index, encoding="utf-8")
    (SITE / "archive.html").write_text(page("往期", "Archive", "archive.html", archive_body(days)), encoding="utf-8")
    groups = load_yaml("sources.yml")
    (SITE / "sources.html").write_text(
        page("来源", "Sources", "sources.html", sources_body(groups, load_json(STATUS_FILE, {}))), encoding="utf-8")
    yt_test = load_json(ROOT / "data" / "yt_test.json", None)
    if yt_test:  # not linked from the tab bar; open /feed/yt-test.html directly
        (SITE / "yt-test.html").write_text(
            page("YouTube 测试", "YouTube test", "", yt_test_body(yt_test)), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"built {len(days)} day pages into {SITE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
