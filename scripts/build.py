"""Step 3: render the static site from data/ into site/.

Pages: index.html (latest day), <date>.html (every day), archive.html, sources.html.
Every visible string is written in both Chinese and English; the page shows one at a time.
"""

import base64
import hashlib
import re
import shutil
import sys
from datetime import date as Date
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from common import DAYS, ROOT, SITE, STATUS_FILE, VIDEO_STATUS_FILE, VIDEOS, load_json, load_yaml

WEEKDAY_ZH = "一二三四五六日"
MOON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>')
SUN = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
       'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="5"/>'
       '<line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>'
       '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
       '<line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>'
       '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>')
ARROW = ('<svg class="back-to-top__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" '
         'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="19" x2="12" y2="5"/>'
         '<polyline points="5 12 12 5 19 12"/></svg>')

# Runs before first paint, right after the color-scheme meta: swaps no-js for js, restores a pinned
# colour scheme (shared with the homepage: same origin, key "theme") and the language, so the
# page never flashes the wrong scheme or language. Page background hexes match --bg-page in
# style.css.
PREPAINT = """<script>(function(){var r=document.documentElement;r.className=r.className.replace(/\\bno-js\\b/,'js');
window.syncThemeColor=function(t){var m=document.querySelectorAll('meta[name="theme-color"]');
for(var i=0;i<m.length;i++){var s=t||(m[i].media.indexOf('dark')>-1?'dark':'light');m[i].setAttribute('content',s==='dark'?'#151410':'#f4f1ea');}};
var t=null,l=null;try{t=localStorage.getItem('theme');l=localStorage.getItem('feed-lang');}catch(e){}
if(t==='light'||t==='dark'){document.querySelector('meta[name="color-scheme"]').content=t;window.syncThemeColor(t);}
if(l==='en'){r.dataset.lang='en';r.lang='en';}else{r.dataset.lang='zh';}})();</script>"""

DESCRIPTION = "鹏宇的每日阅读摘要：博客和 YouTube 视频的中英文转述。"

# The frame is the homepage's: the same tab bar (its four pages plus Feed), footer and
# back-to-top. The homepage tabs are root-absolute links (same origin, another repository);
# Feed's own pages are relative, so the site works under any path.
SITE_TABS = [("/", "Home"), ("/experience/", "Experience"), ("/publications/", "Publications"),
             ("/beyond/", "Beyond")]
RECENT = []       # dates of all days, latest first; filled in main()
SOURCE_LANG = {}  # source name -> language of its titles, from an optional `lang` key in sources.yml

_CJK = re.compile(r"[㐀-鿿]")


def bi(zh, en):
    """Both languages, CSS shows the one picked."""
    return f'<span data-l="zh">{escape(zh)}</span><span data-l="en" lang="en">{escape(en)}</span>'


def bi_any(zh, en):
    """Like bi(), for text that can be missing in one language: the other one fills in and is
    marked with its own language."""
    z = f'<span data-l="zh">{escape(zh)}</span>' if zh else f'<span data-l="zh" lang="en">{escape(en)}</span>'
    e = (f'<span data-l="en" lang="en">{escape(en)}</span>' if en
         else f'<span data-l="en" lang="zh-CN">{escape(zh)}</span>')
    return z + e


def hidden(zh, en):
    """Text for screen readers only (the name of an icon button), in the language on display."""
    return f'<span class="visually-hidden">{bi(zh, en)}</span>'


def lang_attr(text, source=None):
    """Titles and source names are in the source's language, whatever the page language is."""
    lang = SOURCE_LANG.get(source) or ("zh" if _CJK.search(text) else "en")
    return f' lang="{escape(lang)}"'


def date_label(iso):
    d = Date.fromisoformat(iso)
    zh = f"{d.month} 月 {d.day} 日 周{WEEKDAY_ZH[d.weekday()]}"
    en = f"{d.strftime('%A')}, {d.day} {d.strftime('%B')}"
    return zh, en


def date_short(iso):
    """For the side panel: the English date with a short weekday, so that it fits one line."""
    d = Date.fromisoformat(iso)
    return date_label(iso)[0], f"{d.strftime('%a')}, {d.day} {d.strftime('%B')}"


def stack(zh, en):
    """Both languages in one grid cell, the hidden one still taking its space: the box is as
    tall as the taller text, so nothing below it moves when the language is switched."""
    return f'<span class="stack">{bi(zh, en)}</span>'


# IBM Plex Sans SC is 648 @font-face rules (216 unicode-range chunks in three weights, 500 KB of
# CSS). A page uses a small part of them, so each page gets only the rules whose range holds a
# character of that page, inline in its head, instead of the whole file as a stylesheet.
_FACE = re.compile(r"@font-face\{[^}]*\}")
_RANGE = re.compile(r"U\+([0-9A-Fa-f]+)(?:-([0-9A-Fa-f]+))?")
_SC_RULES, _SC_INDEX = [], {}


def load_sc_faces():
    css = (ROOT / "assets" / "fonts" / "plex-sans-sc.css").read_text(encoding="utf-8")
    # The three weights of one chunk have the same long unicode-range. Next to each other they
    # compress to about a third (in the file each weight is a block of its own, too far apart
    # for gzip to see the repetition), so order the rules by chunk number, then by weight.
    chunk = lambda rule: re.search(r"-(\d+)\.woff2", rule).group(1)
    for n, rule in enumerate(sorted(_FACE.findall(css), key=chunk)):
        for lo, hi in _RANGE.findall(rule.split("unicode-range:", 1)[1]):
            for cp in range(int(lo, 16), int(hi or lo, 16) + 1):
                _SC_INDEX.setdefault(cp, []).append(n)
        # the files only: one local() name for three weights would give every weight the Regular
        # face on a computer that has the family installed
        rule = rule.replace('local("IBM Plex Sans SC"),', "").replace('url("sc/', 'url("assets/fonts/sc/')
        _SC_RULES.append(rule)


def sc_faces(html):
    used = set()
    for ch in set(html):
        used.update(_SC_INDEX.get(ord(ch), ()))
    return "".join(_SC_RULES[n] for n in sorted(used))


INTRO = ("每天早上自动收集一批科技和 AI 博客、YouTube 频道的新内容，由模型写成中英文摘要。只转述原文，不加评价。",
         "Tech and AI blogs and YouTube channels, collected every morning and summarised by a model "
         "in Chinese and English. The summaries report the source and add no opinion.")


def feed_side(active):
    """Feed's side panel, in the column where the homepage has the profile card. It is the same
    on every page: the title (the page's h1, as the name is on the homepage), the language
    switch, what Feed is (for a visitor who lands here), and three links of equal rank: the
    latest day (the way back from the other pages), All days, Sources. The link of the page on
    display is marked. On one-column screens it becomes a short header under the tab bar
    (style.css)."""
    # both languages stay visible in the button and the one in use is underlined: nothing in it
    # changes size or place when it is pressed
    lang_btn = ('<button type="button" class="lang-toggle"><span class="lang-toggle__opt" data-lang-opt="zh" lang="zh-CN">中文</span>'
                '<span class="lang-toggle__opt" data-lang-opt="en" lang="en">EN</span>'
                f'{hidden("：切换语言", ": switch language")}</button>')
    pages = [("archive.html", bi("全部日期", "All days")), ("sources.html", bi("来源", "Sources"))]
    if RECENT:
        pages.insert(0, ("./", bi(*date_short(RECENT[0]))))
    links = []
    for href, label in pages:
        cur = ' aria-current="page"' if href == active else ""
        links.append(f'<li><a href="{href}"{cur}>{label}</a></li>')
    return ('<div class="feed-side card">'
            f'<div class="feed-side__top"><h1 class="feed-side__title">{stack("每日阅读摘要", "Daily digest")}</h1>{lang_btn}</div>'
            f'<p class="feed-side__intro">{stack(*INTRO)}</p>'
            f'<nav class="feed-side__pages" aria-label="Feed"><ul class="feed-side__links" role="list">{"".join(links)}</ul></nav></div>')


def page(title, active, body):
    """`title` is what stands before " | Pengyu Zhang" in the browser tab, as on the homepage."""
    site_tabs = "".join(f'<li><a class="tabbar__tab" href="{href}">{label}</a></li>' for href, label in SITE_TABS)
    # Feed is the current section on every Feed page; on the latest day it is the very page
    cur = "page" if active == "./" else "true"
    site_tabs += f'<li><a class="tabbar__tab" href="./" aria-current="{cur}">Feed</a></li>'
    html = f"""<!doctype html>
<html lang="zh-CN" class="no-js">
<head>
<meta charset="utf-8">
<!--csp-->
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="text-scale" content="scale">
<title>{escape(title)} | Pengyu Zhang</title>
<meta name="description" content="{escape(DESCRIPTION)}">
<meta name="robots" content="noindex">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f4f1ea">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#151410">
<meta name="color-scheme" content="light dark">
{PREPAINT}
<link rel="preload" href="assets/fonts/ibm-plex-sans-latin-var.woff2" as="font" type="font/woff2" crossorigin>
<!--sc-faces-->
<link rel="stylesheet" href="assets/style.css">
<link rel="icon" type="image/png" sizes="32x32" href="/images/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/images/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/images/apple-touch-icon.png">
</head>
<body>
<a class="skip-link" href="#content">{bi("跳到正文", "Skip to content")}</a>
<div id="main" class="layout">
<aside class="layout__left">{feed_side(active)}</aside>
<main id="content" class="layout__center">
<nav class="tabbar" aria-label="Primary">
<ul class="tabbar__tabs">{site_tabs}</ul>
<button type="button" id="theme-toggle" class="icon-btn theme-toggle"><span class="theme-toggle__action theme-toggle__action--dark">{MOON}{hidden("切换到暗色", "Switch to dark theme")}</span><span class="theme-toggle__action theme-toggle__action--light">{SUN}{hidden("切换到亮色", "Switch to light theme")}</span></button>
</nav>
{body}
</main>
<footer class="site-footer">{bi("摘要由模型生成，可能有误，以原文为准。每条都附原文链接。",
             "Summaries are machine-written and may be wrong. The original is the source of truth; every item links to it.")}</footer>
</div>
<button type="button" id="back-to-top" class="back-to-top">{ARROW}{hidden("回到顶部", "Back to top")}</button>
<script>{APP_JS}</script>
</body>
</html>
"""
    html = html.replace("<!--sc-faces-->", f"<style>{sc_faces(html)}</style>", 1)
    return html.replace("<!--csp-->", csp_meta(html), 1)


# The page's script, inline (at the end of the body, where the DOM above it is parsed), so that
# the Content-Security-Policy can name every script by its hash and needs no allowlist.
APP_JS = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
assert "</script" not in APP_JS


def csp_meta(html):
    """A strict, hash-based Content-Security-Policy (GitHub Pages cannot send headers, so it is
    a meta element, first in the head): only the inline scripts of this very page run, no
    plugins, no <base>. The hashes are computed from the page itself, so they never go stale."""
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.S)
    hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(s.encode("utf-8")).digest()).decode() + "'"
                      for s in scripts)
    policy = f"script-src {hashes}; object-src 'none'; base-uri 'none'"
    return f'<meta http-equiv="Content-Security-Policy" content="{policy}">'


def paragraphs(items):
    if isinstance(items, str):  # models sometimes return one string instead of a list
        items = [x.strip() for x in re.split(r"\n\s*\n", items) if x.strip()]
    return "".join(f"<p>{escape(x)}</p>" for x in items)


LABELS = {"zh": ("背景：", "要点：", "结论："), "en": ("Background: ", "Key points:", "Takeaway: ")}
LANG_CODE = {"zh": "zh-CN", "en": "en"}


def four_parts(it, lang):
    """Background, numbered key points and conclusion, as in DIGEST_写作规范 (brief is shown above)."""
    other = "en" if lang == "zh" else "zh"

    def get(k):
        """The part in this language; if it is missing, the other language's, marked as such."""
        v = it.get(f"{k}_{lang}")
        if v:
            return v, ""
        v = it.get(f"{k}_{other}")
        return v or "", (f' lang="{LANG_CODE[other]}"' if v else "")

    def text(value, lang_mark):
        return f"<span{lang_mark}>{escape(value)}</span>" if lang_mark else escape(value)

    (bg, bg_l), (pts, pts_l), (end, end_l) = get("background"), get("points"), get("conclusion")
    lb = LABELS[lang]
    html = []
    if bg:
        html.append(f'<p><b class="tag">{lb[0]}</b>{text(bg, bg_l)}</p>')
    if pts:
        html.append(f'<p class="tag-line"><b class="tag">{lb[1]}</b></p><ol class="points"{pts_l}>'
                    + "".join(f"<li>{escape(p)}</li>" for p in pts) + "</ol>")
    if end:
        html.append(f'<p><b class="tag">{lb[2]}</b>{text(end, end_l)}</p>')
    return "".join(html)


def item_html(it, compact=False, detail=True):
    src_lang = lang_attr(it["source"], it["source"])
    src = escape(it["source"])
    if it.get("source_url"):
        src = f'<a class="src" href="{escape(it["source_url"])}" target="_blank" rel="noopener"{src_lang}>{src}</a>'
    else:
        src = f'<span class="src"{src_lang}>{src}</span>'
    meta = [src]
    if compact and it.get("basis") == "short":
        meta.append(f"<span>{bi('原文较短', 'short source text')}</span>")
    brief_zh = it.get("brief_zh") or it.get("summary_zh") or ""
    brief_en = it.get("brief_en") or it.get("summary_en") or ""
    structured = bool(it.get("points_zh") or it.get("points_en"))
    if brief_zh or brief_en:
        brief = bi_any(brief_zh, brief_en)
        if structured:
            brief = f'<b class="tag">{bi("一句话：", "In one line: ")}</b>{brief}'
    else:
        brief = bi("这条没有生成摘要，点标题看原文。", "No summary for this one. Open the title to read the original.")
    more = ""
    if detail and structured:
        more = (f'<div class="detail"><div data-l="zh">{four_parts(it, "zh")}</div>'
                f'<div data-l="en" lang="en">{four_parts(it, "en")}</div></div>')
    dz, de = it.get("detail_zh") or [], it.get("detail_en") or []
    if detail and not structured and (dz or de):  # older items written before the four-part structure
        zh_l = "" if dz else ' lang="en"'
        en_l = "en" if de else "zh-CN"
        more = (f'<div class="detail"><div data-l="zh"{zh_l}>{paragraphs(dz or de)}</div>'
                f'<div data-l="en" lang="{en_l}">{paragraphs(de or dz)}</div></div>')
    # the title is the item's heading (h3, under the h2 of its list)
    return (f'<article class="item"><div class="meta">{"".join(meta)}</div><div class="item__body">'
            f'<h3 class="title"{lang_attr(it["title"], it["source"])}><a href="{escape(it["url"])}" target="_blank" rel="noopener">'
            f'{escape(it["title"])}</a></h3><p class="brief">{brief}</p>{more}</div></article>')


def tab_card(remember, panels, after=""):
    """One card with Blogs / YouTube tabs on top, used by the day pages and by Sources.
    panels: (key, label, count, content) per tab, the first one selected. `after` goes at the
    end of the tab row, outside the tab list (which may hold tabs only). `remember` is the
    storage key under which app.js keeps the visitor's choice. Without JS both panels show, each
    under its own heading; with JS the tabs switch them and the headings stay for screen
    readers only (data-js-hidden keeps the other panels out of the first paint until app.js
    takes over)."""
    tabs, bodies = [], []
    for n, (key, label, count, content) in enumerate(panels):
        on = n == 0
        tabs.append(f'<button type="button" role="tab" id="tab-{key}" data-tab="{key}" data-panel="panel-{key}"'
                    f' aria-selected="{"true" if on else "false"}" tabindex="{0 if on else -1}">{label}'
                    f' <span class="count">{count}</span></button>')
        bodies.append(f'<div class="panel" id="panel-{key}" role="tabpanel" aria-labelledby="tab-{key}"{"" if on else " data-js-hidden"}>'
                      f'<h2 class="panel-title" id="title-{key}">{label} <span class="count-note">{count}</span></h2>'
                      f'{content}</div>')
    return (f'<section class="card lists"><div class="seg-row"><div class="seg" role="tablist" data-remember="{remember}">'
            f'{"".join(tabs)}</div>{after}</div>{"".join(bodies)}</section>')


def day_body(day, picks_on=True, latest=True):
    items = {it["id"]: it for it in day["items"]}
    blogs = [it for it in day["items"] if it.get("kind") != "video"]
    videos = [it for it in day["items"] if it.get("kind") == "video"]
    picks = day.get("picks", {}) if picks_on else {}

    def column(key, label, title):
        ids = [p["id"] if isinstance(p, dict) else p for p in picks.get(key, [])]
        inner = "".join(item_html(items[i]) for i in ids if i in items) or \
            f'<p class="empty">{bi("暂时空着。", "Empty for now.")}</p>'
        return (f'<section class="card"><div class="label">{bi(*label)}</div>'
                f'<h2 class="col-title">{bi(*title)}</h2>{inner}</section>')

    # the two recommendation columns exist only while picks are switched on (config.yml)
    cols = ('<div class="cols">'
            + column("important", ("热门", "Trending"), ("该知道的", "Worth knowing"))
            + column("liked", ("为你挑选", "For you"), ("可能喜欢", "You might like"))
            + "</div>") if picks_on else ""
    picked = {p["id"] if isinstance(p, dict) else p for col in picks.values() for p in col}

    def listing(rows, empty):
        # posts already shown in full in the two columns above: title and one line only here
        return "".join(item_html(it, compact=True, detail=it["id"] not in picked) for it in rows) or \
            f'<p class="empty">{bi(*empty)}</p>'

    # The side panel always names the latest day. On an older day's page the day is written at
    # the end of the tab row.
    which = "" if latest else f'<p class="seg-row__date">{bi(*date_label(day["date"]))}</p>'
    lists = tab_card("feed-tab", [
        ("blog", bi("博客", "Blogs"), len(blogs), listing(blogs, ("这段时间没有新文章。", "No new posts in this period."))),
        ("video", "YouTube", len(videos), listing(videos, ("这段时间没有新视频。", "No new videos in this period."))),
    ], which)
    return cols + lists


def archive_body(days):
    rows = "".join(
        f'<li><a href="{d["date"]}.html">{bi(*date_label(d["date"]))}</a>'
        f'<span class="muted">{bi(str(len(d["items"])) + " 条", str(len(d["items"])) + " items")}</span></li>'
        for d in days)
    # role="list": Safari drops the list semantics of a list without markers
    return (f'<section class="card"><h2 class="section-title">{bi("全部日期", "All days")}</h2>'
            f'<ul class="days" role="list">{rows}</ul></section>')


def source_rows(sources, status, connected=True):
    rows = []
    for s in sources:
        st = status.get(s["name"], {})
        last = st.get("last_post", "")[:10]
        if not connected:
            ok, cls = bi("还没接入", "not connected"), ' class="muted"'
        elif "error" in st:
            ok, cls = bi("抓取失败", "failed"), ' class="bad"'
        elif st.get("ok"):
            ok, cls = bi("正常", "ok"), ""
        else:
            ok, cls = bi("还没抓过", "not fetched yet"), ' class="muted"'
        href = s.get("site") or s.get("feed")
        # a long name may break after a dot or a slash on a phone, never inside a word
        name = re.sub(r"[./]", lambda m: m.group(0) + "<wbr>", escape(s["name"]))
        rows.append(f'<tr><td><a href="{escape(href)}" target="_blank" rel="noopener"{lang_attr(s["name"], s["name"])}>'
                    f'{name}</a></td><td class="muted">{escape(last)}</td><td{cls}>{ok}</td></tr>')
    return "".join(rows)


def source_table(key, rows):
    # The wrapper scrolls sideways on narrow screens: a focusable region, so that it can be
    # scrolled with the keyboard, named by the heading of its panel.
    return (f'<div class="table-scroll" role="region" tabindex="0" aria-labelledby="title-{key}">'
            f'<table class="sources"><thead><tr><th scope="col">{bi("名字", "Name")}</th>'
            f'<th scope="col">{bi("最近一篇", "Latest post")}</th><th scope="col">{bi("状态", "Status")}</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def sources_body(groups, status, video_status):
    blogs, videos = groups.get("blogs", []), groups.get("youtube", [])

    def content(key, rows, empty):
        return source_table(key, rows) if rows else f'<p class="empty">{bi(*empty)}</p>'

    return tab_card("feed-sources-tab", [
        ("src-blog", bi("博客", "Blogs"), len(blogs),
         content("src-blog", source_rows(blogs, status), ("还没有博客来源。", "No blog sources yet."))),
        ("src-video", "YouTube", len(videos),
         content("src-video", source_rows(videos, video_status), ("还没有 YouTube 来源。", "No YouTube sources yet."))),
    ])


def load_days():
    """The days, newest first: the blogs of data/days/ (GitHub) and the videos of data/videos/ (the
    owner's PC). Two folders, so that the two writers never change the same file."""
    by_date = {}
    for p in DAYS.glob("*.json"):
        d = load_json(p, None)
        if d:
            by_date[d["date"]] = d
    for p in VIDEOS.glob("*.json"):
        v = load_json(p, None)
        if not v:
            continue
        d = by_date.setdefault(v["date"], {"date": v["date"], "items": []})
        known = {it["id"] for it in d["items"]}
        d["items"] += [it for it in v["items"] if it["id"] not in known]
        d["items"].sort(key=lambda x: x["published"], reverse=True)
    return sorted(by_date.values(), key=lambda d: d["date"], reverse=True)


def main():
    # Overwrite in place when the old build cannot be removed (a folder where deleting is not allowed)
    shutil.rmtree(SITE, ignore_errors=True)
    # plex-sans-sc.css and app.js are inlined into every page, not loaded as files
    shutil.copytree(ROOT / "assets", SITE / "assets", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("plex-sans-sc.css", "app.js"))
    load_sc_faces()

    days = load_days()
    picks_on = load_yaml("config.yml").get("picks_enabled", True)
    groups = load_yaml("sources.yml")
    RECENT[:] = [d["date"] for d in days]
    SOURCE_LANG.update({s["name"]: s["lang"] for g in groups.values() for s in (g or []) if s.get("lang")})
    for d in days:
        day = Date.fromisoformat(d["date"])
        latest = d is days[0]
        title = "Feed" if latest else f"Feed, {day.day} {day.strftime('%B %Y')}"
        (SITE / f"{d['date']}.html").write_text(
            page(title, "./" if latest else "", day_body(d, picks_on, latest)), encoding="utf-8")
    if days:
        index = page("Feed", "./", day_body(days[0], picks_on))
    else:
        index = page("Feed", "./",
                     f'<section class="card"><h2 class="section-title">{bi("还没有内容", "Nothing yet")}</h2>'
                     f'<p>{bi("第一次运行之后这里就有内容了。", "Content appears after the first run.")}</p></section>')
    (SITE / "index.html").write_text(index, encoding="utf-8")
    (SITE / "archive.html").write_text(page("Feed, all days", "archive.html", archive_body(days)), encoding="utf-8")
    (SITE / "sources.html").write_text(
        page("Feed, sources", "sources.html",
             sources_body(groups, load_json(STATUS_FILE, {}), load_json(VIDEO_STATUS_FILE, {}))), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"built {len(days)} day pages into {SITE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
