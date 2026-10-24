"""あなた待ち（BACKLOG.md の [?]）を Discord で @ 付きで知らせ、返事がなければ繰り返す（2026-10-24，用户定的）。

ask_remind.yml が 5 分ごと・BACKLOG.md が変わったとき・手で起こしたときに呼ぶ。
- 新しい [?]：すぐ @ 付きで知らせる
- 残っている [?]：最初の 1 時間は 5 分おき（12 回まで）、そのあとは 3 時間おき。夜（日本時間 0〜8 時）は繰り返さない（新しいものは送る）
- [?] が消えた（答えて決まった・進んだ）ら止める
何をいつ送ったかは ASK_STATE（Actions の cache）に。宛先は DISCORD_MENTION（<@数字>。なければ @here）。

    python harness/ask_remind.py BACKLOG.md STATE.json
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.request

JST = dt.timezone(dt.timedelta(hours=9))
ITEM = re.compile(r"^- \[\?\] (.+)$")
FAST_EVERY = 5 * 60       # 最初の 1 時間：5 分おき
FAST_TIMES = 12
SLOW_EVERY = 3 * 3600     # そのあと：3 時間おき
NIGHT = range(0, 8)       # 日本時間 0〜8 時は繰り返さない


def asks(text):
    out = {}
    for line in (text or "").splitlines():
        m = ITEM.match(line.strip())
        if m:
            out[m.group(1).split(" — ")[0].strip()] = m.group(1)
    return out


def due(st, now):
    """{first, last, count} → いま送るか。"""
    if not st:
        return True
    gap = now - st["last"]
    if st["count"] < FAST_TIMES:
        return gap >= FAST_EVERY - 20   # 5 分ごとの起こしの揺れを許す
    return gap >= SLOW_EVERY - 60


def plan(items, state, now):
    """送る [(名前, 行, 新しいか)] と次の state。"""
    night = dt.datetime.fromtimestamp(now, JST).hour in NIGHT
    send, nxt = [], {}
    for name, line in items.items():
        st = state.get(name)
        if not st:
            send.append((name, line, True))
            nxt[name] = {"first": now, "last": now, "count": 1}
        elif not night and due(st, now):
            send.append((name, line, False))
            nxt[name] = {**st, "last": now, "count": st["count"] + 1}
        else:
            nxt[name] = st
    return send, nxt


def payload(send, mention):
    new = [s for s in send if s[2]]
    head = f"{mention} ❓ 確認をお願いします" if new else f"{mention} ⏰ まだお返事待ちです"
    lines = [f"・{'（新）' if n else ''}{line[:300]}" for _, line, n in send[:8]]
    return {"content": (head + "\n" + "\n".join(lines) + "\n一覧：https://github.com/CxElegy/Wishlist/blob/main/BACKLOG.md")[:1950],
            "allowed_mentions": {"parse": ["users", "everyone"]}}


def main(argv):
    text = pathlib.Path(argv[0]).read_text(encoding="utf-8")
    sp = pathlib.Path(argv[1])
    state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    send, nxt = plan(asks(text), state, now)
    sp.write_text(json.dumps(nxt, ensure_ascii=False), encoding="utf-8")
    if not send:
        print("送るものなし")
        return 0
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    body = payload(send, os.environ.get("DISCORD_MENTION") or "@here")
    if not hook:
        print(json.dumps(body, ensure_ascii=False))
        return 0
    req = urllib.request.Request(hook, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": "wishlist-ask"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print("Discord:", r.status, len(send), "件")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
