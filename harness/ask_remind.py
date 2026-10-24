"""会話の Claude がユーザーに選んでもらう質問を出したとき、Discord に @ 付きで知らせ、返事がなければ繰り返す。
2 時間ごとの「いま何をしているか」（30 字）もここから送る（2026-10-24，用户定的）。

ask_remind.yml が呼ぶ：
  ask "<質問の要約>"  会話の Claude が質問を出したとき（workflow_dispatch）。すぐ @ 付きで送り、待ちに入れる
  clear               ユーザーが答えたとき（workflow_dispatch）。待ちを消す
  say "<30 字>"       2 時間ごとの報告（workflow_dispatch）。そのまま送る（@ なし）
  tick                5 分ごと（schedule）。待ちがあれば、最初の 1 時間は 5 分おき・そのあと 30 分おきに @ 付きで繰り返す。夜（日本時間 0〜8 時）は休む
待ちの記録は STATE（Actions の cache）。宛先は DISCORD_MENTION（<@番号>。なければ @here）。
BACKLOG の [?]（何日もかかる決めごと）は送らない（2026-10-24，用户定的：知らせるのは会話の中の質問だけ）。

    python harness/ask_remind.py STATE.json tick|clear|ask TEXT|say TEXT
"""
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.request

JST = dt.timezone(dt.timedelta(hours=9))
FAST_EVERY = 5 * 60       # 最初の 1 時間：5 分おき
FAST_TIMES = 12
SLOW_EVERY = 30 * 60      # そのあと：30 分おき
NIGHT = range(0, 8)       # 日本時間 0〜8 時は繰り返さない


def due(st, now):
    if not st:
        return False
    if dt.datetime.fromtimestamp(now, JST).hour in NIGHT:
        return False
    gap = now - st["last"]
    return gap >= (FAST_EVERY if st["count"] < FAST_TIMES else SLOW_EVERY) - 20   # 5 分ごとの起こしの揺れを許す


def step(cmd, text, state, now, mention):
    """(送る本文 or None, 次の state)"""
    if cmd == "ask":
        return f"{mention} ❓ 選んでほしい質問があります：{text}", {"text": text, "first": now, "last": now, "count": 1}
    if cmd == "clear":
        return None, {}
    if cmd == "say":
        return f"🕑 {text}", state
    if due(state, now):
        mins = int((now - state["first"]) // 60)
        return f"{mention} ⏰ まだお返事待ちです（{mins} 分）：{state['text']}", {**state, "last": now, "count": state["count"] + 1}
    return None, state


def send(content):
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    body = {"content": content[:1950], "allowed_mentions": {"parse": ["users", "everyone"]}}
    if not hook:
        print(json.dumps(body, ensure_ascii=False))
        return
    req = urllib.request.Request(hook, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": "wishlist-ask"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print("Discord:", r.status)


def main(argv):
    sp, cmd, text = pathlib.Path(argv[0]), argv[1], " ".join(argv[2:]).strip()
    state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    content, nxt = step(cmd, text, state, now, os.environ.get("DISCORD_MENTION") or "@here")
    sp.write_text(json.dumps(nxt, ensure_ascii=False), encoding="utf-8")
    if content:
        send(content)
    else:
        print("送るものなし")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
