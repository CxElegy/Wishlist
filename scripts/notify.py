"""Discord 通知。

changes    推送了新功能（代码、工作流、编辑手册、skill 有改动）时，把这些提交的说明发一条「功能更新」；
           已经发过的位置记在 state/announced_commit.txt
wishlist   wishlist.yaml 里新加的东西（图、价格、链接）发一条通知；发过的记在 state/known_wishlist.json
hesitate   纠结名单里的东西搜到了类似的新产品 / 新消息，发一条通知；发过的链接记在 state/known_hesitate.json
new-items  items.yaml 里新加 / 删掉了关注项，发一条通知；已知的关注项记在 state/known_items.json
urgent  要紧消息（ingest 标记的 urgent 条目、状态变化）当天立刻发；发过的记在 state/notified.json，不重复发
weekly  每周一发一次：过去 7 天各关注项的要点 + 简报网页链接

需要环境变量 DISCORD_WEBHOOK_URL（Discord 频道设置 → 整合 → Webhook → 复制网址）。
没设置时只把要发的内容打印出来，方便本地检查。
"""

import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

import digest
import sitedir
import sources

NOTIFIED_FILE = digest.STATE_DIR / "notified.json"
ANNOUNCED_FILE = digest.STATE_DIR / "announced_commit.txt"
# 改了这些地方才算“功能更新”；只改数据（inbox / reports / state / docs）或关注清单的不算
FEATURE_PATHS = ["scripts", ".github", "EDITING.md", ".claude", "requirements.txt", "README.md"]
KNOWN_WISH_FILE = digest.STATE_DIR / "known_wishlist.json"
KNOWN_HESITATE_FILE = digest.STATE_DIR / "known_hesitate.json"
HESITATE_PER_WISH = 3  # 每件纠结的东西一次最多报几条
KNOWN_FILE = digest.STATE_DIR / "known_items.json"
TYPE_NAMES = {"product": "商品", "category": "一类产品", "game": "游戏", "anime": "动画 / 漫画", "show": "影视剧", "event": "艺人演出"}
MAX_LINES = 6  # 每个关注项最多列几条


def _color(item_name, themes):
    """嵌入卡片左侧色条用作品的强调色：items.yaml 手写的优先，其次是自动取色的缓存。"""
    _, items = digest.load_config()
    manual = next(((i.get("theme") or {}).get("accent") for i in items if i["name"] == item_name), None)
    if manual:
        return int(manual.lstrip("#"), 16)
    for key, t in themes.items():
        if key.split("|")[0] == item_name:
            return int(t["accent"].lstrip("#"), 16)
    return 0xB83A17


def _today():
    tz = digest.load_config()[0].get("timezone", "Asia/Shanghai")
    return dt.datetime.now(digest.zoneinfo.ZoneInfo(tz)).date()


def _cut(text, n):
    return text if len(text) <= n else text[: n - 1] + "…"


def send(payload):
    payload.setdefault("allowed_mentions", {"parse": []})
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("未设置 DISCORD_WEBHOOK_URL，以下是将要发送的内容：", file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return False
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": sources.USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        # 发送失败不中断工作流（后面还要提交网页）；没标记为已通知，下次运行会重试
        print(f"[警告] Discord 发送失败：{e}", file=sys.stderr)
        return False


def urgent(page_url):
    """把还没通知过的要紧消息立刻发出去。看最近两天的 inbox（防止跨过午夜漏掉）。"""
    notified = digest.load_json(NOTIFIED_FILE)
    themes = digest.load_json(digest.THEMES_FILE)
    today = _today()
    embeds, keys = [], []
    for path in sorted(digest.INBOX_DIR.glob("????-??-??.json"))[-2:]:
        inbox = digest.load_json(path)
        anchor = f"{page_url}#issue-{inbox['date']}"
        for item in inbox["items"]:
            lines = []
            for f in item["facts"]:
                key = f"fact:{item['name']}:{f['label']}:{f['text']}"
                if f["changed"] and key not in notified:
                    lines.append(f"**{f['label']}有变化**：{f['text']}")
                    keys.append(key)
            for e in item["entries"]:
                if e.get("urgent") and e["url"] not in notified:
                    link = e.get("link") or sources.resolve_url(e["url"])
                    lines.append(f"• [{_cut(e['title'], 90)}]({link}) — {e['source']}")
                    keys.append(e["url"])
            if lines:
                embeds.append({
                    "title": f"{item['name']} · 要紧消息",
                    "url": anchor,
                    "color": _color(item["name"], themes),
                    "description": "\n".join(lines[:MAX_LINES]),
                })
    if not embeds:
        print("没有新的要紧消息", file=sys.stderr)
        return
    mention = digest.load_config()[0].get("discord_mention")
    payload = {
        "username": "关注清单通信",
        "content": (f"<@{mention}> " if mention else "") + f"**【要紧】关注清单有新消息**\n简报：{page_url}",
        "embeds": embeds[:10],
        # 只允许 @ 设置里的这个人，防止标题里的 @everyone 之类被触发
        "allowed_mentions": {"users": [str(mention)] if mention else []},
    }
    if send(payload):
        notified.update({k: today.isoformat() for k in keys})
        # 只保留 30 天的记录（更早的消息早已不会再被收集），文件不会无限变大
        cutoff = (today - dt.timedelta(days=30)).isoformat()
        digest.save_json(NOTIFIED_FILE, {k: d for k, d in notified.items() if d >= cutoff})


def _git(*args):
    return subprocess.run(["git", *args], cwd=digest.ROOT, capture_output=True, text=True, check=True).stdout


def changes(page_url):
    """上次通知之后新加的功能（提交说明的第一行）发 Discord。机器人自己的提交和合并提交不算。"""
    head = _git("rev-parse", "HEAD").strip()
    if not ANNOUNCED_FILE.exists():
        ANNOUNCED_FILE.write_text(head + "\n")
        return
    since = ANNOUNCED_FILE.read_text().strip()
    try:
        log = _git("log", "--no-merges", "--reverse", "--format=%H%x1f%s%x1f%an", f"{since}..{head}", "--", *FEATURE_PATHS)
    except subprocess.CalledProcessError as e:
        print(f"[警告] 读不到提交记录：{e.stderr.strip()}", file=sys.stderr)
        return
    repo = os.environ.get("GITHUB_REPOSITORY", "CxElegy/Wishlist")
    lines = []
    for row in log.splitlines():
        sha, subject, author = row.split("\x1f")
        if author == "github-actions[bot]":
            continue
        lines.append(f"• [{_cut(subject, 150)}](https://github.com/{repo}/commit/{sha[:7]})")
    if not lines:
        ANNOUNCED_FILE.write_text(head + "\n")
        return
    desc = "\n".join(lines)
    if len(desc) > 3800:
        desc = desc[:3800] + "\n……"
    payload = {
        "username": "关注清单通信",
        "content": f"**【功能更新】关注清单加了新功能**\n简报：{page_url}",
        "embeds": [{"title": f"本次更新 · {len(lines)} 项", "url": f"https://github.com/{repo}/commits",
                    "color": 0x2F5BD3, "description": desc}],
    }
    if send(payload):
        ANNOUNCED_FILE.write_text(head + "\n")


def wishlist(page_url):
    """愿望清单里新加的东西：每件一张卡片（大图 + 价格 + 规格 + 链接）。"""
    wishes = digest.load_wishlist()
    known = digest.load_json(KNOWN_WISH_FILE) if KNOWN_WISH_FILE.exists() else []
    new = [x for x in wishes if x["name"] not in known]
    if not new:
        return
    embeds = []
    for x in new[:10]:
        img = x.get("image") or ""
        if img and not img.startswith("http"):
            # 用仓库里的原文件地址：推送后立刻能访问，不用等 GitHub Pages 发布
            repo = os.environ.get("GITHUB_REPOSITORY", "CxElegy/Wishlist")
            branch = os.environ.get("GITHUB_REF_NAME", "main")
            img = f"https://raw.githubusercontent.com/{repo}/{branch}/docs/{sitedir.SLUG}/wishlist/{urllib.parse.quote(img)}"
        lines = []
        if x.get("price") not in (None, ""):
            lines.append(f"**{x.get('currency', '')} {x['price']}**")
        lines += [f"{k}：{v}" for k, v in (x.get("specs") or {}).items()]
        if x.get("note"):
            lines.append(x["note"])
        if x.get("watch"):
            lines.append(f"会在「{x['watch']}」版面持续追踪相关消息")
        st = x.get("status") or "想要"
        embed = {"title": f"♥ {x['name']}" + ("" if st == "想要" else f"（{st}）"), "url": x.get("url") or f"{page_url}wishlist.html",
                 "color": 0xB8336A, "description": "\n".join(lines),
                 "footer": {"text": " · ".join(str(v) for v in (x.get("shop"), x.get("added")) if v)}}
        if img:
            embed["image"] = {"url": img}
        embeds.append(embed)
    if send({"username": "关注清单通信", "content": f"**愿望清单新加了 {len(new)} 件**\n{page_url}wishlist.html",
             "embeds": embeds}):
        digest.save_json(KNOWN_WISH_FILE, [x["name"] for x in wishes])


def hesitate(page_url):
    """纠结名单：每天搜到的类似新产品 / 新消息（state/discover.json 里带 wish 的条目），没报过的发一条通知。"""
    torn = {x["name"] for x in digest.load_wishlist() if x.get("status") == digest.HESITATE}
    finds = [x for x in (digest.load_json(digest.DISCOVER_FILE) or {}).get("entries", []) if x.get("wish") and x["item"] in torn]
    known = digest.load_json(KNOWN_HESITATE_FILE) if KNOWN_HESITATE_FILE.exists() else []
    new = [x for x in finds if x["url"] not in known]
    if not new:
        return
    embeds = []
    for name in dict.fromkeys(x["item"] for x in new):
        mine = sorted((x for x in new if x["item"] == name), key=lambda x: x.get("date") or "", reverse=True)
        lines = [f"[{x['title']}]({x['url']}) · {x['source']}" for x in mine[:HESITATE_PER_WISH]]
        embeds.append({"title": f"纠结中：{name}", "url": f"{page_url}wishlist.html", "color": 0xB5650D,
                       "description": "\n".join(lines)})
    if send({"username": "关注清单通信", "content": f"**纠结名单里的东西有类似的新发现**\n{page_url}wishlist.html",
             "embeds": embeds[:10]}):
        digest.save_json(KNOWN_HESITATE_FILE, sorted(set(known) | {x["url"] for x in finds}))


def new_items(page_url):
    """items.yaml 里新加的关注项发 Discord 通知（删掉的也顺带说一声）。
    第一次运行时没有记录，只把现有的关注项记下来，不发通知。"""
    _, items = digest.load_config()
    names = [i["name"] for i in items]
    if not KNOWN_FILE.exists():
        digest.save_json(KNOWN_FILE, names)
        print(f"记录现有关注项：{'、'.join(names)}", file=sys.stderr)
        return
    known = digest.load_json(KNOWN_FILE) or []
    added = [i for i in items if i["name"] not in known]
    removed = [n for n in known if n not in names]
    if not added and not removed:
        return
    themes = digest.load_json(digest.THEMES_FILE)
    embeds = []
    for i in added:
        lines = [f"类型：{TYPE_NAMES.get(i.get('type', 'product'), i.get('type'))}"]
        if i.get("keywords"):
            lines.append("关键词：" + "、".join(i["keywords"][:6]))
        if i.get("priority"):
            lines.append("最关心：" + _cut(i["priority"].strip(), 120))
        if i.get("site"):
            lines.append(f"官网：{i['site']}")
        lines.append("下一次收集（2 小时内）开始追踪，消息会出现在简报里。")
        embeds.append({
            "title": f"新增关注 · {i['name']}" + (f"（{i['subtitle']}）" if i.get("subtitle") else ""),
            "url": page_url,
            "color": _color(i["name"], themes),
            "description": "\n".join(lines),
        })
    content = "**关注清单有变动**"
    if removed:
        content += "\n已取消关注：" + "、".join(removed)
    if send({"username": "关注清单通信", "content": content + f"\n简报：{page_url}", "embeds": embeds[:10]}):
        digest.save_json(KNOWN_FILE, names)


def weekly(page_url):
    """过去 7 天的周报。"""
    themes = digest.load_json(digest.THEMES_FILE)
    end = _today()
    start = end - dt.timedelta(days=6)
    stories, facts = {}, {}
    for path in sorted(digest.REPORTS_DIR.glob("????-??-??.json")):
        if not (start.isoformat() <= path.stem <= end.isoformat()):
            continue
        for block in digest.load_json(path)["items"]:
            if block.get("quiet"):
                continue
            stories.setdefault(block["name"], []).extend(block["stories"])
            facts.setdefault(block["name"], []).extend(f for f in block["facts"] if f["changed"])

    period = f"{start.month}/{start.day}–{end.month}/{end.day}"
    if not stories and not facts:
        return send({"username": "关注清单通信", "content": f"**关注清单周报 · {period}**\n本周没有新消息。\n{page_url}"})
    embeds = []
    for name in sorted(set(stories) | set(facts)):
        items = sorted(stories.get(name, []), key=lambda s: {"hero": 0, "lead": 1}.get(s["weight"], 2))
        lines = [f"**{f['label']}有变化**：{f['text']}" for f in facts.get(name, [])]
        lines += [("**[重大]** " if s["weight"] == "hero" else "• ") + f"[{_cut(s['headline'], 90)}]({s['url']})"
                  for s in items[:MAX_LINES]]
        more = len(items) - MAX_LINES
        if more > 0:
            lines.append(f"……另有 {more} 条，见简报")
        embeds.append({
            "title": name,
            "url": page_url,
            "color": _color(name, themes),
            "description": "\n".join(lines),
        })
    head = f"**关注清单周报 · {period}**\n简报：{page_url}"
    ok = True
    for k, part in enumerate(split_embeds(embeds)):   # Discord：1 通に embed 10 個・合計 6,000 字まで。超えると 400 で全部拒まれる
        ok = send({"username": "关注清单通信", "content": head if k == 0 else f"**关注清单周报 · {period}**（续 {k + 1}）",
                   "embeds": part}) and ok
    return ok


EMBED_MAX, EMBEDS_PER_MSG, MSG_CHARS = 4096, 10, 5800   # Discord の上限（description 4,096 字・1 通 embed 10 個・合計 6,000 字）より少し下


def split_embeds(embeds):
    """embed を Discord の上限に収まる束に分ける（2026-10-22 全体の検査 H5：週報が 7,478 字で 400、黙って送れていなかった）。"""
    out, cur, size = [], [], 0
    for em in embeds:
        em = {**em, "description": _cut(em.get("description") or "", EMBED_MAX)}
        n = len(em.get("title") or "") + len(em["description"])
        if cur and (len(cur) >= EMBEDS_PER_MSG or size + n > MSG_CHARS):
            out.append(cur)
            cur, size = [], 0
        cur.append(em)
        size += n
    return out + [cur] if cur else out
