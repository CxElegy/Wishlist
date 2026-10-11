"""把各期数据渲染成一张报纸式简报网页（docs/index.html），新一期在最上面。

版式规则：
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
.pic img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.hero{grid-column:span 12;display:grid;grid-template-columns:7fr 5fr;gap:24px;padding:24px}
.hero .pic{height:420px}
.hero .txt{display:flex;flex-direction:column;justify-content:center;gap:16px}
.tag{font:700 12px 'JetBrains Mono',monospace;letter-spacing:.25em;color:var(--ac)}
.hero h2{margin:0;font-weight:900;font-size:46px;line-height:1.2}
.lead{grid-column:span 8}.lead .pic{height:380px}
.lead h2{margin:0;font-weight:900;font-size:36px;line-height:1.25}
.side{grid-column:span 4;display:flex;flex-direction:column;gap:1px}
.side .card{flex:1}.side .pic{height:150px}
.side h3{margin:0;font-weight:900;font-size:22px;line-height:1.35}
.row .pic{height:170px}
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
@media (max-width:760px){
 .page{padding:20px 12px}.mast h1{font-size:30px;padding:12px}.mast .logo{display:none}.mast .meta{width:110px}.mast .no{font-size:20px}
 .band .title{font-size:34px}.band .sub{margin-left:0}
 .band.split{background:var(--abg)}.band.split .sub{color:var(--afg)}
 .hero{grid-template-columns:1fr}.hero .pic,.lead .pic,.side .pic,.row .pic{height:200px}
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
    tag = (
        f'<img src="{e(img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">'
        if img else ""
    )
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


def _section(block):
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
    return (f'<section class="sec {"serif" if t.get("font") == "serif" else "sans"}{quiet}" style="{style}">'
            f'<div class="{band_cls}"><span class="title">{e(block["name"])}</span>{sub}</div>'
            f"{facts}{grid}</section>")


def render(issues):
    """issues：按时间倒序的各期数据。"""
    latest = issues[0]
    parts = []
    for i, issue in enumerate(issues):
        label = ("今 日" if i == 0 else "往 期") + f" · {issue['date'].replace('-', '.')}"
        parts.append(f'<div class="issue" id="issue-{issue["date"]}"><div class="issue-head"><span>{label}</span></div>'
                     + "".join(_section(b) for b in issue["items"]) + "</div>")
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
{''.join(parts)}
</div>
</body>
</html>
"""
