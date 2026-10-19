"""いまの Claude Code のセッションが使ったトークン（本物の数字。推定ではない）。

Claude Code はセッションの記録（~/.claude/projects/<作業ディレクトリ>/<セッション>.jsonl）に、
Claude の返事 1 回ごとの usage（input / cache_creation / cache_read / output）を書いている。いちばん新しい記録を読んで合計する。
同じ返事が何行かに分かれて書かれる（ストリーミング）ので、message.id ごとに最後の 1 行だけ数える。
AI 編集（Claude の定時タスク）が出刊のたびに呼び、前の出刊からの差を「このバッチで使ったトークン」として実行ログに書く
（digest.logged_publish → state/log/edit.json → 管理ページ）。GitHub Actions には記録がないので None。
"""

import json
import os
import pathlib

KEYS = {"in": "input_tokens", "cw": "cache_creation_input_tokens", "cr": "cache_read_input_tokens", "out": "output_tokens"}


def transcript(root=None):
    """いちばん新しいセッションの記録ファイル。なければ None。"""
    base = pathlib.Path(root or os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude") / "projects"
    files = [p for p in base.glob("*/*.jsonl") if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def session_usage(path=None):
    """→ {"in", "cw", "cr", "out", "calls", "model"}（このセッションのここまでの合計）。記録がなければ None。"""
    path = path or transcript()
    if not path:
        return None
    by = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                m = d.get("message") if isinstance(d, dict) else None
                if d.get("type") == "assistant" and isinstance(m, dict) and isinstance(m.get("usage"), dict) and m.get("id"):
                    by[m["id"]] = (m.get("model") or "", m["usage"])
    except OSError:
        return None
    out = {k: sum(int(u.get(v) or 0) for _, u in by.values()) for k, v in KEYS.items()}
    models = [m for m, _ in by.values() if m]
    out.update(calls=len(by), model=max(set(models), key=models.count) if models else "")
    return out


def diff(now, before):
    """2 つの合計の差（before がなければ now のまま）。"""
    if not now:
        return None
    return {k: (now.get(k) or 0) - ((before or {}).get(k) or 0) for k in (*KEYS, "calls")} | {"model": now.get("model", "")}


def total(u):
    """表示用の合計（新しい入力 + キャッシュ書き + キャッシュ読み + 出力）。"""
    return sum(int((u or {}).get(k) or 0) for k in KEYS)


def short(u):
    """ログ 1 行用：『token 入力 1.2万・キャッシュ読み 34万・出力 3,100』。"""
    if not u:
        return ""
    man = lambda n: f"{n / 10000:.1f}万" if n >= 10000 else f"{n:,}"
    return f"token 新規入力 {man(u['in'] + u['cw'])}・キャッシュ読み {man(u['cr'])}・出力 {man(u['out'])}"
