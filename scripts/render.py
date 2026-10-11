"""把各期数据渲染成一张报纸式简报网页（docs/index.html），新一期在最上面。

版式规则：
- 顶部悬浮目录：按板块分组列出每个作品，滚动时当前所在的一项放大并换成板块色，点击直达；可跳往期
- 每期最上面一张「头版」：重磅头条大图 + 按板块（游戏 / 影视 / 运动 / 好物）的彩色索引 + 今日要闻
- 报头中性；每个关注项一个板块，配色取自该作品（theme.py）
- weight=hero 的消息（直接回答你最关心的问题，如定档、测试日期）独占整行大图
- 其余第一条做头条（8 栏大图），接着两条做侧栏，剩下的三栏一排
- 本期没有新消息的关注项（quiet）只留一个小栏：标题条 + 现状 + 往期最近一条
"""

import html
import re

FONTS = (
    "https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@700;900"
    "&family=Noto+Serif+SC:wght@500;700;900&family=Cormorant+Garamond:wght@600"
    "&family=JetBrains+Mono:wght@500;700&display=swap"
)

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#EDEBE6;color:#1A1C22;font-family:'Noto Serif SC',serif}
a{color:inherit;text-decoration:none}
.page{max-width:1200px;margin:0 auto;padding:40px 24px;display:flex;flex-direction:column;gap:28px}
.mast{border:3px solid #1A1C22;padding:5px}
.mast>div{border:1px solid #1A1C22;display:flex}
.mast .logo{width:100px;background:#1A1C22;display:flex;align-items:center;justify-content:center}
.mast h1{flex:1;margin:0;padding:14px 28px;font:900 56px/1 'Noto Sans SC',sans-serif;letter-spacing:.04em}
.mast .meta{width:190px;border-left:1px solid #1A1C22;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:2px}
.mast .no{font:900 32px/1 'Noto Sans SC',sans-serif}
.mono{font-family:'JetBrains Mono',monospace;font-size:13px}
.issue{display:flex;flex-direction:column;gap:28px}
.issue-head{display:flex;align-items:center;gap:16px}
.issue-head::before,.issue-head::after{content:"";flex:1;border-top:2px solid #1A1C22}
.issue-head span{font:700 13px 'JetBrains Mono',monospace;letter-spacing:.3em}
.sec{background:var(--bg);color:var(--fg);border:1px solid var(--bg)}
.band{min-height:92px;display:flex;align-items:center;flex-wrap:wrap;gap:6px 18px;padding:16px 28px;background:var(--bg)}
.band.split{background:linear-gradient(162deg,var(--abg) 0 55%,var(--bg) 55% 100%)}
.band .title{font-size:50px;line-height:1;color:var(--fg)}
.band.split .title{color:var(--afg)}
.band .sub{margin-left:auto;font-size:15px;letter-spacing:.1em;color:var(--fg);opacity:.85}
.serif .title{font-family:'Cormorant Garamond','Noto Serif SC',serif;font-weight:600}
.sans .title{font-family:'Noto Sans SC',sans-serif;font-weight:900;font-size:40px}
.facts{display:flex;flex-wrap:wrap;gap:1px;background:var(--line)}
.fact{flex:1 1 280px;padding:14px 22px;background:var(--abg);color:var(--afg);display:flex;flex-direction:column;gap:4px}
.fact .label{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.75}
.fact .new{color:var(--aac);opacity:1}
.fact a{text-decoration:underline;text-underline-offset:3px}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:1px;background:var(--line)}
.card{padding:20px;display:flex;flex-direction:column;gap:12px}
.card.m{background:var(--bg);color:var(--fg);--ac:var(--acc)}
.card.a{background:var(--abg);color:var(--afg);--ac:var(--aacc)}
.card:hover h2,.card:hover h3{text-decoration:underline;text-underline-offset:5px;text-decoration-thickness:1px}
.hl{color:var(--ac)}
.pic{position:relative;overflow:hidden;border:1px solid color-mix(in srgb,currentColor 35%,transparent);
 background:repeating-linear-gradient(135deg,color-mix(in srgb,currentColor 7%,transparent) 0 14px,transparent 14px 28px)}
.pic{aspect-ratio:16/9}
.pic img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
.pic img.bg{object-fit:cover;filter:blur(18px) brightness(.8);transform:scale(1.15)}
.hero{grid-column:span 12;display:grid;grid-template-columns:7fr 5fr;gap:24px;padding:24px}
.hero .pic{align-self:center}
.s12 .pic{aspect-ratio:auto;height:260px}.s12 .pic:empty{display:none}
.hero .txt{display:flex;flex-direction:column;justify-content:center;gap:16px}
.tag{font:700 12px 'JetBrains Mono',monospace;letter-spacing:.25em;color:var(--ac)}
.hero h2{margin:0;font-weight:900;font-size:46px;line-height:1.2}
.lead{grid-column:span 8}
.lead h2{margin:0;font-weight:900;font-size:36px;line-height:1.25}
.side{grid-column:span 4;display:flex;flex-direction:column;gap:1px}
.side .card{flex:1}
.side h3{margin:0;font-weight:900;font-size:22px;line-height:1.35}
.row h3{margin:0;font-weight:900;font-size:21px;line-height:1.4}
.s12{grid-column:span 12}.s6{grid-column:span 6}.s4{grid-column:span 4}
.blurb{margin:0;font-size:16px;line-height:1.75;opacity:.85}
.quiet .band{min-height:64px;padding:10px 24px}
.quiet .band .title{font-size:32px}
.sans.quiet .band .title{font-size:26px}
.calm{display:flex;align-items:center;gap:20px;padding:12px 24px;background:var(--bg);color:var(--fg);border-top:3px solid var(--acc)}
.calm .pic{flex:0 0 120px;height:62px}
.calm .txt{flex:1;display:flex;flex-direction:column;gap:4px;min-width:0}
.calm .tag{color:var(--acc)}
.calm .status{font-size:15px;line-height:1.6}
.calm .last{flex:0 1 40%;display:flex;flex-direction:column;gap:2px;font-size:15px;line-height:1.5;border-left:1px solid color-mix(in srgb,currentColor 25%,transparent);padding-left:20px}
.calm .last .mono{font-size:11px;letter-spacing:.15em;opacity:.7}
.calm a.last:hover b{text-decoration:underline;text-underline-offset:4px}
/* ---------- 头版 ---------- */
.front{background:#FBF8F1;border:3px solid #1A1C22;box-shadow:6px 6px 0 #1A1C22;display:flex;flex-direction:column;
 background-image:radial-gradient(#1A1C22 .8px,transparent .9px);background-size:7px 7px;background-position:0 0}
.front>*{background:#FBF8F1}
.fbar{display:flex;align-items:center;gap:14px;padding:8px 18px;background:#1A1C22;color:#FBF8F1;font:700 12px 'JetBrains Mono',monospace;letter-spacing:.25em}
.fbar b{font:900 15px 'Noto Sans SC',sans-serif;letter-spacing:.3em;color:#FFD23F}
.fbar span:last-child{margin-left:auto}
.fbody{display:grid;grid-template-columns:7fr 5fr;gap:0;border-bottom:3px solid #1A1C22}
.top{position:relative;padding:22px;border-right:3px solid #1A1C22;display:flex;flex-direction:column;gap:14px;color:#1A1C22}
.top .pic{border:3px solid #1A1C22;color:#1A1C22}
.top .badge{position:absolute;left:8px;top:8px;z-index:2;padding:6px 14px 6px 12px;background:#D7261E;color:#FFF;
 font:900 20px/1 'Noto Sans SC',sans-serif;letter-spacing:.08em;clip-path:polygon(0 0,100% 0,88% 100%,0 100%);border:none}
.top .kicker{display:flex;align-items:center;gap:10px;font:700 12px 'JetBrains Mono',monospace;letter-spacing:.2em}
.top .kicker i{font-style:normal;padding:2px 10px;color:#FFF;letter-spacing:.15em}
.top h2{margin:0;font:900 44px/1.2 'Noto Sans SC',sans-serif;color:#D7261E;letter-spacing:.01em;
 text-shadow:2px 2px 0 #FFD23F}
.top p{margin:0;font-size:16px;line-height:1.75}
.top:hover h2{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:6px}
.boards{display:flex;flex-direction:column}
.board{border-bottom:3px solid #1A1C22;display:flex;flex-direction:column}
.board:last-child{border-bottom:none;flex:1}
.board h3{margin:0;display:flex;align-items:center;gap:10px;padding:8px 16px;background:var(--sc);color:#FFF;
 font:900 20px/1.2 'Noto Sans SC',sans-serif;letter-spacing:.3em}
.board h3 small{margin-left:auto;font:700 11px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.9}
.entry{display:grid;grid-template-columns:96px 1fr;gap:12px;align-items:center;padding:10px 16px;border-top:1px dashed color-mix(in srgb,#1A1C22 35%,transparent)}
.entry:first-of-type{border-top:none}
.entry .pic{aspect-ratio:16/10;border:2px solid #1A1C22;color:#1A1C22}
.entry .nm{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.12em;color:var(--sc)}
.entry b{display:block;font-size:15px;line-height:1.45;margin-top:2px}
.entry.q b{font-weight:500;opacity:.6}
.entry:hover b{text-decoration:underline;text-underline-offset:3px}
.board .none{padding:10px 16px;font-size:13px;opacity:.55}
.heads{display:flex;flex-direction:column}
.heads h4{margin:0;display:flex;align-items:baseline;gap:14px;padding:10px 18px;border-bottom:2px solid #1A1C22;
 font:900 26px/1 'Noto Sans SC',sans-serif;letter-spacing:.06em}
.heads h4 small{font:700 12px 'JetBrains Mono',monospace;letter-spacing:.3em;color:#D7261E}
.heads ol{list-style:none;margin:0;padding:6px 18px 14px;columns:2;column-gap:32px}
.heads li{break-inside:avoid;padding:7px 0;border-bottom:1px dotted color-mix(in srgb,#1A1C22 40%,transparent);display:flex;gap:10px;align-items:baseline}
.heads li i{flex:none;font:900 11px/1.6 'Noto Sans SC',sans-serif;font-style:normal;color:#FFF;background:var(--sc);padding:0 6px;letter-spacing:.1em}
.heads li a{font-size:15px;line-height:1.5}
.heads li a:hover{text-decoration:underline;text-underline-offset:3px}
/* ---------- 悬浮目录 ---------- */
html{scroll-behavior:smooth}
[data-k]{scroll-margin-top:84px}
.nav{position:sticky;top:env(safe-area-inset-top,0px);z-index:50;background:#1A1C22;color:#FBF8F1;
 border:3px solid #1A1C22;box-shadow:0 6px 0 rgba(26,28,34,.12)}
.nav-in{display:flex;align-items:center;gap:14px;padding:8px 14px}
.nav .here{flex:none;display:flex;flex-direction:column;gap:1px;padding-right:14px;border-right:1px solid rgba(251,248,241,.25)}
.nav .here b{font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.35em;color:#FFD23F}
.nav .here span{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.12em;font-variant-numeric:tabular-nums;opacity:.8}
.nav .rail{flex:1;min-width:0;display:flex;align-items:center;gap:6px;overflow-x:auto;scrollbar-width:none;padding:6px 4px}
.nav .rail::-webkit-scrollbar{display:none}
.nav .grp{flex:none;margin-left:8px;font:900 11px 'Noto Sans SC',sans-serif;letter-spacing:.2em;color:var(--sc);
 filter:brightness(1.6) saturate(.9)}
.nav .grp:first-child{margin-left:0}
.nav .pill{flex:none;padding:4px 10px;border:1px solid rgba(251,248,241,.28);font:700 13px/1.3 'Noto Sans SC',sans-serif;
 white-space:nowrap;transform-origin:center;transition:transform .25s cubic-bezier(.3,1.6,.5,1),background .2s,color .2s,border-color .2s}
.nav .pill:hover{border-color:#FBF8F1}
.nav .pill:focus-visible,.nav select:focus-visible{outline:2px solid #FFD23F;outline-offset:2px}
.nav .pill.on{background:var(--sc);border-color:var(--sc);color:#FFF;transform:scale(1.18);margin:0 6px;
 box-shadow:2px 2px 0 #FBF8F1}
.nav .pill.front-k{--sc:#D7261E}
.nav select{flex:none;background:transparent;color:#FBF8F1;border:1px solid rgba(251,248,241,.28);padding:4px 6px;
 font:700 12px 'JetBrains Mono',monospace;color-scheme:dark}
.nav .bar{height:3px;background:var(--cur,#D7261E);width:0;transition:width .15s linear,background .2s}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.nav .pill,.nav .bar{transition:none}}
@media (max-width:760px){
 .nav .here{display:none}.nav-in{padding:6px 8px;gap:8px}[data-k]{scroll-margin-top:64px}
 .fbody{grid-template-columns:1fr}.top{border-right:none;border-bottom:3px solid #1A1C22}
 .top h2{font-size:30px}.heads ol{columns:1}.fbar span:nth-child(2){display:none}
 .page{padding:20px 12px}.mast h1{font-size:30px;padding:12px}.mast .logo{display:none}.mast .meta{width:110px}.mast .no{font-size:20px}
 .band .title{font-size:34px}.band .sub{margin-left:0}
 .band.split{background:var(--abg)}.band.split .sub{color:var(--afg)}
 .hero{grid-template-columns:1fr}
 .hero h2,.lead h2{font-size:28px}
 .lead,.side,.s12,.s6,.s4{grid-column:span 12}
 .quiet .band .title{font-size:26px}
 .calm{flex-wrap:wrap;gap:12px;padding:12px 16px}.calm .pic{display:none}
 .calm .last{flex:1 1 100%;border-left:0;padding-left:0}
}
"""

LOGO = (
    '<svg width="62" height="62" viewBox="0 0 92 92" aria-hidden="true" fill="none" stroke="#EDEBE6" stroke-width="2">'
    '<circle cx="46" cy="46" r="40"/><circle cx="46" cy="46" r="31" stroke-dasharray="3 4"/>'
    '<path d="M46 18 L51 41 L74 46 L51 51 L46 74 L41 51 L18 46 L41 41 Z" fill="#EDEBE6" stroke="none"/></svg>'
)

e = html.escape


def _md_links(text):
    """把状态文字里的 [文字](链接) 转成 <a>。"""
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', e(text, quote=False))


def _headline(story):
    text = e(story["headline"])
    hl = story.get("highlight")
    if hl and e(hl) in text:
        text = text.replace(e(hl), f'<span class="hl">{e(hl)}</span>', 1)
    return text


def _pic(story):
    img = story.get("image")
    # 底层模糊铺满，上层完整显示：图片不裁切，也不留空白条
    tag = "".join(
        f'<img{cls} src="{e(img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">'
        for cls in (' class="bg"', "")
    ) if img else ""
    return f'<div class="pic">{tag}</div>'


def _card(story, cls, side, level="h3", blurb=False):
    body = f'<{level}>{_headline(story)}</{level}>'
    if blurb and story.get("blurb"):
        body += f'<p class="blurb">{e(story["blurb"])}</p>'
    return (f'<a class="card {side} {cls}" href="{e(story["url"])}" target="_blank" rel="noopener">'
            f'{_pic(story)}{body}</a>')


def _hero(story, side):
    return (f'<a class="card {side} hero" href="{e(story["url"])}" target="_blank" rel="noopener">{_pic(story)}'
            f'<div class="txt"><span class="tag">重 大</span><h2>{_headline(story)}</h2>'
            + (f'<p class="blurb">{e(story["blurb"])}</p>' if story.get("blurb") else "")
            + "</div></a>")


def _grid(stories):
    heroes = [s for s in stories if s.get("weight") == "hero"]
    rest = [s for s in stories if s.get("weight") != "hero"]
    out = [_hero(s, "m" if i % 2 == 0 else "a") for i, s in enumerate(heroes)]

    if len(rest) == 1:
        out.append(_card(rest[0], "hero" if not heroes else "s12 row", "m" if not heroes else "a",
                         level="h2" if not heroes else "h3", blurb=True))
        return "".join(out)
    if rest:
        lead, side, others = rest[0], rest[1:3], rest[3:]
        out.append(_card(lead, "lead", "m", level="h2", blurb=True))
        out.append('<div class="side">' + "".join(_card(s, "", "a") for s in side) + "</div>")
        for start in range(0, len(others), 3):
            chunk = others[start:start + 3]
            span = {1: "s12", 2: "s6", 3: "s4"}[len(chunk)]
            out += [_card(s, f"row {span}", "a" if (start + i) % 2 == 0 else "m") for i, s in enumerate(chunk)]
    return "".join(out)


def _calm(block):
    """没有新消息时的小栏：封面小图、现状、往期最近一条。"""
    pic = _pic({"image": block.get("cover")}) if block.get("cover") else ""
    status = f'<span class="status">{_md_links(block["status"])}</span>' if block.get("status") else ""
    last = block.get("last")
    tail = ""
    if last:
        tail = (f'<a class="last" href="{e(last["url"])}" target="_blank" rel="noopener">'
                f'<span class="mono">最近 · {e(last["date"].replace("-", "."))}</span><b>{e(last["headline"])}</b></a>')
    return (f'<div class="calm">{pic}<div class="txt"><span class="tag">暂 无 新 消 息</span>{status}</div>'
            f"{tail}</div>")


def _section(block, anchor=""):
    t = block["theme"]
    style = (f"--bg:{t['bg']};--fg:{t['fg']};--acc:{t['accent']};--abg:{t['alt_bg']};"
             f"--afg:{t['alt_fg']};--aacc:{t['alt_accent']};--aac:{t['alt_accent']};"
             f"--line:color-mix(in srgb,{t['fg']} 22%,{t['bg']})")
    band_cls = "band split" if t.get("split") else "band"
    sub = f'<span class="sub">{e(block["subtitle"])}</span>' if block.get("subtitle") else ""
    # 状态只在有变化时上版面，没变化就是不必要的信息
    changed = [f for f in block.get("facts") or [] if f["changed"]]
    facts = ""
    if changed:
        facts = '<div class="facts">' + "".join(
            f'<div class="fact"><span class="label{" new" if f["changed"] else ""}">'
            f'{e(f["label"])}{" · 有变化" if f["changed"] else ""}</span><span>{_md_links(f["text"])}</span></div>'
            for f in changed
        ) + "</div>"
    grid = f'<div class="grid">{_grid(block["stories"])}</div>' if block.get("stories") else ""
    if block.get("quiet"):
        grid = _calm(block)
    quiet = " quiet" if block.get("quiet") else ""
    return (f'<section id="{anchor}" data-k="{e(block["name"])}" class="sec {"serif" if t.get("font") == "serif" else "sans"}{quiet}" style="{style}">'
            f'<div class="{band_cls}"><span class="title">{e(block["name"])}</span>{sub}</div>'
            f"{facts}{grid}</section>")


# 头版板块：固定的几个先排，颜色各不相同；items.yaml 里自己起的新板块用灰色
SECTIONS = {"游戏": "#2F5BD3", "影视": "#9B3FB5", "运动": "#1F9D6B", "好物": "#E07A1F"}
SECTION_EN = {"游戏": "GAMES", "影视": "SCREEN", "运动": "SPORTS", "好物": "GOODS"}


def _sec_color(name):
    return SECTIONS.get(name, "#5B5F6B")


def _top_story(issue):
    """头条：先找 hero（直接回答最关心问题的新消息），没有就用第一个有消息的关注项的头条。"""
    blocks = [b for b in issue["items"] if b.get("stories")]
    for b in blocks:
        for s in b["stories"]:
            if s.get("weight") == "hero":
                return b, s
    return (blocks[0], blocks[0]["stories"][0]) if blocks else (None, None)


def _front(issue):
    date = issue["date"]
    tb, top = _top_story(issue)
    sections = {}
    for i, b in enumerate(issue["items"]):
        sections.setdefault(b.get("section") or "其他", []).append((i, b))
    order = [n for n in SECTIONS] + [n for n in sections if n not in SECTIONS]
    count = sum(len(b.get("stories") or []) for b in issue["items"])

    head = (f'<div class="fbar"><b>头 版</b><span>FRONT PAGE · No.{issue["no"]:03d}</span>'
            f'<span>{date.replace("-", ".")} · 今日 {count} 条</span></div>')

    if top:
        sc = _sec_color(tb.get("section"))
        badge = "重 磅" if top.get("weight") == "hero" else "头 条"
        top_html = (f'<a class="top" href="{e(top["url"])}" target="_blank" rel="noopener">'
                    f'<span class="badge">{badge}</span>{_pic(top)}'
                    f'<span class="kicker"><i style="background:{sc}">{e(tb.get("section") or "")}</i>{e(tb["name"])}</span>'
                    f'<h2>{e(top["headline"])}</h2>'
                    + (f'<p>{e(top["blurb"])}</p>' if top.get("blurb") else "") + "</a>")
    else:
        top_html = '<div class="top"><h2>今天没有新消息</h2></div>'

    boards = []
    for name in order:
        members = sections.get(name, [])
        sc = _sec_color(name)
        rows = []
        for i, b in members:
            first = (b.get("stories") or [None])[0]
            if first:
                text, img, cls = first["headline"], first.get("image") or b.get("cover"), "entry"
            else:
                text, img, cls = b.get("status") or "暂无新消息", b.get("cover"), "entry q"
            rows.append(f'<a class="{cls}" href="#issue-{date}-{i}">{_pic({"image": img})}'
                        f'<span><span class="nm">{e(b["name"])}</span><b>{e(text)}</b></span></a>')
        body = "".join(rows) or '<div class="none">还没有关注项</div>'
        boards.append(f'<div class="board" style="--sc:{sc}"><h3>{e(name)}<small>{SECTION_EN.get(name, "")}</small></h3>{body}</div>')

    heads = []
    for b in issue["items"]:
        for s in b.get("stories") or []:
            if s is top:
                continue
            heads.append(f'<li style="--sc:{_sec_color(b.get("section"))}"><i>{e(b.get("section") or "")}</i>'
                         f'<a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["headline"])}</a></li>')
    heads_html = ""
    if heads:
        heads_html = (f'<div class="heads"><h4>今日要闻<small>TODAY\'S HEADLINES</small></h4>'
                      f'<ol>{"".join(heads[:12])}</ol></div>')
    return (f'<section class="front" data-k="front">{head}<div class="fbody">{top_html}'
            f'<div class="boards">{"".join(boards)}</div></div>{heads_html}</section>')


def _nav(issues):
    """顶部悬浮目录：以最新一期为准，按板块分组；往期用下拉跳转。"""
    latest = issues[0]
    groups = {}
    for b in latest["items"]:
        groups.setdefault(b.get("section") or "其他", []).append(b)
    order = [n for n in SECTIONS if n in groups] + [n for n in groups if n not in SECTIONS]
    date = latest["date"]
    rail = [f'<a class="pill front-k" data-for="front" href="#issue-{date}">头版</a>']
    for name in order:
        sc = _sec_color(name)
        rail.append(f'<span class="grp" style="--sc:{sc}">{e(name)}</span>')
        rail += [f'<a class="pill" style="--sc:{sc}" data-for="{e(b["name"])}" href="#issue-{date}-{latest["items"].index(b)}">'
                 f'{e(b["name"])}</a>' for b in groups[name]]
    past = ""
    if len(issues) > 1:
        opts = "".join(f'<option value="issue-{i["date"]}">{i["date"][5:].replace("-", ".")}</option>' for i in issues[1:])
        past = (f'<select id="nav-past" aria-label="跳到往期"><option value="">往期</option>{opts}</select>')
    return (f'<nav class="nav" aria-label="目录"><div class="nav-in">'
            f'<div class="here"><b>目 录</b><span id="nav-here">今日 · {date.replace("-", ".")}</span></div>'
            f'<div class="rail" id="nav-rail">{"".join(rail)}</div>{past}</div><div class="bar" id="nav-bar"></div></nav>')


NAV_JS = """
(() => {
  const rail = document.getElementById('nav-rail'), bar = document.getElementById('nav-bar'),
        here = document.getElementById('nav-here'), nav = document.querySelector('.nav');
  const marks = [...document.querySelectorAll('[data-k]')];
  const pills = [...rail.querySelectorAll('.pill')];
  let cur = null, ticking = false;
  function update() {
    ticking = false;
    const y = nav.getBoundingClientRect().bottom + 24;
    let m = marks[0];
    for (const el of marks) { if (el.getBoundingClientRect().top <= y) m = el; else break; }
    if (!m) return;
    const r = m.getBoundingClientRect();
    bar.style.width = Math.min(100, Math.max(0, (y - r.top) / r.height * 100)) + '%';
    if (m === cur) return;
    cur = m;
    const issue = m.closest('.issue');
    here.textContent = issue ? issue.dataset.label : '';
    const today = issue === document.querySelector('.issue');
    let on = null;
    pills.forEach(p => {
      const hit = today && p.dataset.for === m.dataset.k;
      p.classList.toggle('on', hit);
      if (hit) on = p;
    });
    bar.style.setProperty('--cur', on ? getComputedStyle(on).getPropertyValue('--sc') : '#8C8678');
    if (on) {
      const left = on.offsetLeft - rail.clientWidth / 2 + on.offsetWidth / 2;
      rail.scrollTo({ left, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }
  }
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  addEventListener('resize', update);
  const past = document.getElementById('nav-past');
  if (past) past.addEventListener('change', () => {
    if (past.value) document.getElementById(past.value).scrollIntoView();
    past.value = '';
  });
  update();
})();
"""


def render(issues):
    """issues：按时间倒序的各期数据。"""
    latest = issues[0]
    parts = []
    for i, issue in enumerate(issues):
        label = ("今 日" if i == 0 else "往 期") + f" · {issue['date'].replace('-', '.')}"
        short = ("今日" if i == 0 else "往期") + f" · {issue['date'].replace('-', '.')}"
        parts.append(f'<div class="issue" id="issue-{issue["date"]}" data-label="{short}"><div class="issue-head"><span>{label}</span></div>'
                     + _front(issue)
                     + "".join(_section(b, f"issue-{issue['date']}-{n}") for n, b in enumerate(issue["items"])) + "</div>")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>关注清单通信 No.{latest['no']:03d}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}</style>
</head>
<body>
<div class="page">
<header class="mast"><div>
<div class="logo">{LOGO}</div>
<h1>关注清单通信</h1>
<div class="meta"><div class="no">No.{latest['no']:03d}</div><div class="mono">{latest['date'].replace('-', '.')}</div></div>
</div></header>
{_nav(issues)}
{''.join(parts)}
</div>
<script>{NAV_JS}</script>
</body>
</html>
"""
