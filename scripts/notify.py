"""Discord 通知。

urgent  要紧消息（ingest 标记的 urgent 条目、状态变化）当天立刻发；发过的记在 state/notified.json，不重复发
weekly  每周一发一次：过去 7 天各关注项的要点 + 简报网页链接

需要环境变量 DISCORD_WEBHOOK_URL（Discord 频道设置 → 整合 → Webhook → 复制网址）。
没设置时只把要发的内容打印出来，方便本地检查。
"""

import datetime as dt
import json
import os
import sys
import urllib.request

import digest
import sources

NOTIFIED_FILE = digest.STATE_DIR / "notified.json"
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
    with urllib.request.urlopen(req, timeout=30) as resp:
        return 200 <= resp.status < 300


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
                    link = sources.resolve_url(e["url"])
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
        digest.save_json(NOTIFIED_FILE, notified)


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
            stories.setdefault(block["name"], []).extend(block["stories"])
            facts.setdefault(block["name"], []).extend(f for f in block["facts"] if f["changed"])

    period = f"{start.month}/{start.day}–{end.month}/{end.day}"
    if not stories and not facts:
        send({"username": "关注清单通信", "content": f"**关注清单周报 · {period}**\n本周没有新消息。\n{page_url}"})
        return
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
    send({
        "username": "关注清单通信",
        "content": f"**关注清单周报 · {period}**\n简报：{page_url}",
        "embeds": embeds[:10],
    })
