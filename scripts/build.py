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
MOON = ('<svg class="icon--moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>')
SUN = ('<svg class="icon--sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
       'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="5"/>'
       '<line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>'
       '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
       '<line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>'
       '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>')

# Runs before first paint, right after the color-scheme meta: swaps no-js for js, restores a pinned
# colour scheme (shared with the homepage: same origin, key "theme") and the language, so the page
# never flashes the wrong scheme or language. Page background hexes match --bg-page in style.css.
PREPAINT = """<script>(function(){var r=document.documentElement;r.className=r.className.replace(/\\bno-js\\b/,'js');
window.syncThemeColor=function(t){var m=document.querySelectorAll('meta[name="theme-color"]');
for(var i=0;i<m.length;i++){var s=t||(m[i].media.indexOf('dark')>-1?'dark':'light');m[i].setAttribute('content',s==='dark'?'#151410':'#f4f1ea');}};
var t=null,l=null;try{t=localStorage.getItem('theme');l=localStorage.getItem('feed-lang');}catch(e){}
if(t==='light'||t==='dark'){document.querySelector('meta[name="color-scheme"]').content=t;window.syncThemeColor(t);}
if(l==='en'){r.dataset.lang='en';r.lang='en';}else{r.dataset.lang='zh';}})();</script>"""

DESCRIPTION = "鹏宇的每日阅读摘要：博客和 YouTube 视频的中英文转述。"


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
    items = []
    for href, zh, en in tabs:
        on = href == active
        cls = "tabbar__tab is-active" if on else "tabbar__tab"
        cur = ' aria-current="page"' if on else ""
        items.append(f'<li><a class="{cls}" href="{href}"{cur}>{bi(zh, en)}</a></li>')
    nav = "".join(items)
    return f"""<!doctype html>
<html lang="zh-CN" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title_en)} · Feed</title>
<meta name="description" content="{escape(DESCRIPTION)}">
<meta name="robots" content="noindex">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f4f1ea">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#151410">
<meta name="color-scheme" content="light dark">
{PREPAINT}
<link rel="preload" href="assets/fonts/ibm-plex-sans-latin-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="assets/fonts/plex-sans-sc.css">
<link rel="stylesheet" href="assets/style.css">
<link rel="icon" type="image/png" sizes="32x32" href="/images/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/images/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/images/apple-touch-icon.png">
</head>
<body>
<a class="skip-link" href="#content">{bi("跳到正文", "Skip to content")}</a>
<div class="wrap">
<nav class="tabbar" aria-label="Feed">
<ul class="tabbar__tabs">{nav}</ul>
<button type="button" id="lang-toggle" class="icon-btn" aria-label="切换语言 / Switch language" title="切换语言 / Switch language"><span data-l="zh">EN</span><span data-l="en">中</span></button>
<button type="button" id="theme-toggle" class="icon-btn" aria-label="切换亮色和暗色 / Toggle light and dark" title="切换亮色和暗色 / Toggle light and dark">{MOON}{SUN}</button>
</nav>
<main id="content" style="display:flex;flex-direction:column;gap:1.5em">
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


LABELS = {"zh": ("背景：", "要点：", "结论："), "en": ("Background: ", "Key points:", "Takeaway: ")}


def four_parts(it, lang):
    """Background, numbered key points and conclusion, as in DIGEST_写作规范 (brief is shown above)."""
    other = "en" if lang == "zh" else "zh"
    get = lambda k: it.get(f"{k}_{lang}") or it.get(f"{k}_{other}") or ""
    bg, pts, end = get("background"), get("points"), get("conclusion")
    lb = LABELS[lang]
    html = []
    if bg:
        html.append(f'<p><b class="tag">{lb[0]}</b>{escape(bg)}</p>')
    if pts:
        html.append(f'<p class="tag-line"><b class="tag">{lb[1]}</b></p><ol class="points">'
                    + "".join(f"<li>{escape(p)}</li>" for p in pts) + "</ol>")
    if end:
        html.append(f'<p><b class="tag">{lb[2]}</b>{escape(end)}</p>')
    return "".join(html)


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
    structured = bool(it.get("points_zh") or it.get("points_en"))
    if brief_zh or brief_en:
        brief = bi(brief_zh or brief_en, brief_en or brief_zh)
        if structured:
            brief = f'<b class="tag">{bi("一句话：", "In one line: ")}</b>{brief}'
    else:
        brief = bi("这条没有生成摘要，点标题看原文。", "No summary for this one. Open the title to read the original.")
    out = [f'<article class="item"><div class="meta">{"".join(meta)}</div>',
           f'<a class="title" href="{escape(it["url"])}" target="_blank" rel="noopener">{escape(it["title"])}</a>',
           f'<p class="brief">{brief}</p>']
    if detail and structured:
        out.append(f'<div class="detail"><div data-l="zh">{four_parts(it, "zh")}</div>'
                   f'<div data-l="en" lang="en">{four_parts(it, "en")}</div></div>')
    dz, de = it.get("detail_zh") or [], it.get("detail_en") or []
    if detail and not structured and (dz or de):  # older items written before the four-part structure
        out.append(f'<div class="detail"><div data-l="zh">{paragraphs(dz or de)}</div>'
                   f'<div data-l="en" lang="en">{paragraphs(de or dz)}</div></div>')
    out.append("</article>")
    return "".join(out)


def day_body(day, picks_on=True):
    items = {it["id"]: it for it in day["items"]}
    blogs = [it for it in day["items"] if it.get("kind") != "video"]
    videos = [it for it in day["items"] if it.get("kind") == "video"]
    zh, en = date_label(day["date"])
    gen = day.get("generated_at")
    when = ""
    if gen:
        when = datetime.fromisoformat(gen).astimezone(ZoneInfo("Europe/Amsterdam")).strftime("%H:%M")
    head = (f'<header class="card page-head"><div class="label label--accent">Feed</div>'
            f'<h1>{bi(zh, en)}</h1><p class="muted">'
            f'{bi(f"博客 {len(blogs)} 篇 · 视频 {len(videos)} 个" + (f" · {when} 更新" if when else ""), f"{len(blogs)} posts · {len(videos)} videos" + (f" · updated {when}" if when else ""))}'
            f"</p></header>")
    picks = day.get("picks", {}) if picks_on else {}

    def column(key, label, title):
        ids = [p["id"] if isinstance(p, dict) else p for p in picks.get(key, [])]
        inner = "".join(item_html(items[i]) for i in ids if i in items) or \
            f'<p class="empty">{bi("暂时空着。", "Empty for now.")}</p>'
        return (f'<section class="card" aria-label="{escape(title[1])}"><div class="label">{bi(*label)}</div>'
                f'<h2 class="col-title">{bi(*title)}</h2>{inner}</section>')

    cols = ('<div class="cols">'
            + column("important", ("热门", "Trending"), ("该知道的", "Worth knowing"))
            + column("liked", ("为你挑选", "For you"), ("可能喜欢", "You might like"))
            + "</div>")
    picked = {p["id"] if isinstance(p, dict) else p for col in picks.values() for p in col}

    def listing(rows, empty):
        # posts already shown in full in the two columns above: title and one line only here
        return "".join(item_html(it, compact=True, detail=it["id"] not in picked) for it in rows) or \
            f'<p class="empty">{bi(*empty)}</p>'

    def tab(key, label, count, on):
        return (f'<button type="button" role="tab" id="tab-{key}" data-tab="{key}" data-panel="panel-{key}"'
                f' aria-selected="{"true" if on else "false"}" tabindex="{0 if on else -1}">{label}'
                f' <span class="count">{count}</span></button>')

    seg = (f'<div class="seg" role="tablist" aria-label="{escape("Blogs / YouTube")}">'
           + tab("blog", bi("博客", "Blogs"), len(blogs), True)
           + tab("video", "YouTube", len(videos), False) + "</div>")
    # Without JS both panels show, each under its own heading; with JS the tabs switch them
    # (data-js-hidden keeps the second one out of the first paint until app.js takes over).
    all_sec = (f'<section class="card list"><h2 class="section-title">{bi("全部更新", "All updates")}</h2>{seg}'
               f'<div class="panel" id="panel-blog" role="tabpanel" aria-labelledby="tab-blog">'
               f'<h3 class="panel-title">{bi("博客", "Blogs")}</h3>'
               f'{listing(blogs, ("这段时间没有新文章。", "No new posts in this period."))}</div>'
               f'<div class="panel" id="panel-video" role="tabpanel" aria-labelledby="tab-video" data-js-hidden>'
               f'<h3 class="panel-title">YouTube</h3>'
               f'{listing(videos, ("这段时间没有新视频。", "No new videos in this period."))}</div></section>')
    return head + cols + all_sec


def archive_body(days):
    rows = "".join(
        f'<li><a href="{d["date"]}.html">{bi(*date_label(d["date"]))}</a>'
        f'<span class="muted">{bi(str(len(d["items"])) + " 条", str(len(d["items"])) + " items")}</span></li>'
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


def main():
    # Overwrite in place when the old build cannot be removed (a folder where deleting is not allowed)
    shutil.rmtree(SITE, ignore_errors=True)
    shutil.copytree(ROOT / "assets", SITE / "assets", dirs_exist_ok=True)

    days = sorted((load_json(p, None) for p in DAYS.glob("*.json")), key=lambda d: d["date"], reverse=True)
    days = [d for d in days if d]
    picks_on = load_yaml("config.yml").get("picks_enabled", True)
    for d in days:
        zh, en = date_label(d["date"])
        (SITE / f"{d['date']}.html").write_text(page(zh, en, "", day_body(d, picks_on)), encoding="utf-8")
    if days:
        latest = days[0]
        zh, en = date_label(latest["date"])
        index = page(zh, en, "index.html", day_body(latest, picks_on))
    else:
        index = page("还没有内容", "Nothing yet", "index.html",
                     f'<section class="card"><p>{bi("第一次运行之后这里就有内容了。", "Content appears after the first run.")}</p></section>')
    (SITE / "index.html").write_text(index, encoding="utf-8")
    (SITE / "archive.html").write_text(page("往期", "Archive", "archive.html", archive_body(days)), encoding="utf-8")
    groups = load_yaml("sources.yml")
    (SITE / "sources.html").write_text(
        page("来源", "Sources", "sources.html", sources_body(groups, load_json(STATUS_FILE, {}))), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"built {len(days)} day pages into {SITE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
