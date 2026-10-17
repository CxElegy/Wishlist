"""裏で動く仕組みの実行ログ（管理ページ「バックグラウンド → ログ」）。

仕組みごとに別のファイル（state/log/<proc>.json）に書く。GitHub Actions と Claude の定時タスクが同じファイルに書くと、
push のときにぶつかる（rebase の衝突）ので、書く人ごとに分ける：
  collect  ニュース収集（GitHub Actions）
  publish  出刊（GitHub Actions の自動出刊）
  edit     AI 編集の出刊（Claude の定時タスク）
  emblem   小元素の自動補完（GitHub Actions の後台）
  gate     後台のゲート（仕事があるか・Claude を起こすか。GitHub Actions）
各ファイルは新しい KEEP 件だけ残す。
"""

import datetime as dt
import json
import pathlib

LOG_DIR = pathlib.Path(__file__).resolve().parent.parent / "state" / "log"
KEEP = 60
PROCS = {"collect": "ニュース収集", "publish": "出刊", "edit": "AI 編集", "emblem": "小元素の自動補完", "photos": "写真から愿望",
         "gate": "後台のゲート"}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load(proc, log_dir=None):
    try:
        data = json.loads(((log_dir or LOG_DIR) / f"{proc}.json").read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def add(proc, text, level="info", log_dir=None, **extra):
    """1 行足す。level：info / ok / warn / error。失敗しても本体の処理は止めない。"""
    try:
        d = log_dir or LOG_DIR
        rows = load(proc, d) + [{"at": _now(), "text": str(text)[:200], "level": level, **extra}]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{proc}.json").write_text(json.dumps(rows[-KEEP:], ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    except OSError:
        pass


def typical(proc, key="secs", default=None, n=10, log_dir=None):
    """その仕組みの最近 n 回の key（かかった秒数など）の中央値。記録がなければ default。
    版面の「更新中」の帯の「あと約 N 分」は、固定の値ではなくこれで決める（回を重ねるほど実際に合う）。"""
    vals = sorted([v for v in (r.get(key) for r in load(proc, log_dir)) if isinstance(v, (int, float)) and v > 0][-n:])
    return vals[len(vals) // 2] if vals else default


def recent(n=40, log_dir=None):
    """全部の仕組みのログを新しい順に n 件。各行に proc（仕組みの id）と name（表示名）を付ける。"""
    rows = []
    for proc, name in PROCS.items():
        rows += [{**r, "proc": proc, "name": name} for r in load(proc, log_dir)]
    return sorted(rows, key=lambda r: r.get("at") or "", reverse=True)[:n]


def main():
    """Claude の定時タスクから 1 行書く：python scripts/runlog.py <proc> "文" [--tokens N] [--level ok]
    サーバーの様子（resources.snapshot）を自動で付ける。--tokens はそのセッションで使ったトークンの目安。"""
    import argparse
    import resources
    ap = argparse.ArgumentParser(description="実行ログに 1 行書く")
    ap.add_argument("proc", choices=sorted(PROCS))
    ap.add_argument("text")
    ap.add_argument("--level", default="info", choices=["info", "ok", "warn", "error"])
    ap.add_argument("--tokens", type=int, help="このセッションで使ったトークン（目安）")
    a = ap.parse_args()
    extra = {"res": resources.snapshot()}
    if a.tokens:
        extra["tokens"] = a.tokens
    add(a.proc, a.text, a.level, **extra)


if __name__ == "__main__":
    main()
