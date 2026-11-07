"""店長の PC の自前版 Supabase が外から届くかを見て、変わったときだけ Discord へ知らせる。

PC が止まると PC 自身では知らせられないので、GitHub Actions の外側から見る（pc_watch.yml）。
/auth/v1/health は鍵なしだと 401、鍵ありだと 200 を返す。どちらも「届いている」と数える。

    python scripts/pc_watch.py .pc_watch_state.json
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

UP_CODES = {200, 401}
TRIES = 3
RETRY_S = 60
REMIND_H = 6


def base_url(path="items.yaml"):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    m = re.search(r"^\s*supabase_url:\s*[\"']?(https://[^\s\"']+)", text, re.M)
    if not m:
        raise SystemExit("items.yaml に supabase_url がない")
    return m.group(1).rstrip("/")


def probe(url):
    """(届いたか, 説明)。"""
    req = urllib.request.Request(url + "/auth/v1/health", headers={"User-Agent": "wishlist-pc-watch"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:
        return False, f"接続できない（{type(e).__name__}）"
    return code in UP_CODES, f"HTTP {code}"


def check(url, tries=TRIES, wait=RETRY_S, probe_fn=probe, sleep=time.sleep):
    """一瞬の揺れで知らせないよう、続けて失敗したときだけ「止まっている」とする。"""
    why = ""
    for i in range(tries):
        ok, why = probe_fn(url)
        if ok:
            return True, why
        if i + 1 < tries:
            sleep(wait)
    return False, why


def decide(prev, up, now, remind_h=REMIND_H):
    """前の状態と今の結果から (次の状態, 知らせる種類 or None)。初回は届いていれば黙る。"""
    prev = prev or {}
    if up:
        kind = "up" if prev.get("down_since") else None
        return {"checked": now.isoformat(timespec="seconds")}, kind
    since = prev.get("down_since") or now.isoformat(timespec="seconds")
    told = prev.get("told")
    if not told:
        kind = "down"
    elif now - dt.datetime.fromisoformat(told) >= dt.timedelta(hours=remind_h):
        kind = "still"
    else:
        kind = None
    return {"checked": now.isoformat(timespec="seconds"), "down_since": since,
            "told": now.isoformat(timespec="seconds") if kind else told}, kind


def message(kind, why, state, prev):
    if kind == "up":
        return f"🟢 PC のサーバーが戻りました（{prev.get('down_since', '?')} UTC から止まっていました）"
    head = "🔴 PC のサーバーに届きません" if kind == "down" else "🔴 PC のサーバーはまだ止まっています"
    return (f"{head}（{why}、{state['down_since']} UTC から）。"
            "ログイン・👍👎・設定の保存が止まります。記事は読めます。")


def send(text):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("DISCORD_WEBHOOK_URL が無いので送らない：", text)
        return False
    req = urllib.request.Request(url, data=json.dumps({"content": text, "allowed_mentions": {"parse": []}}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "wishlist-pc-watch"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return 200 <= r.status < 300


def main():
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".pc_watch_state.json")
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    up, why = check(base_url())
    state, kind = decide(prev, up, dt.datetime.now(dt.timezone.utc))
    print("届いている" if up else "届かない", why, kind or "知らせない")
    if kind:
        send(message(kind, why, state, prev))
    path.write_text(json.dumps(state), encoding="utf-8")


if __name__ == "__main__":
    main()
