"""版面の「更新中」の帯（render.BUSY_JS）に、いま裏でどの版面を作り直しているかを知らせる。

書き先は Supabase の live_status 表（db/live_status.sql）。網页は live_boards() を 30 秒ごとに読む。
  ・収集（GitHub Actions）は secret key で直接書く（digest.live_mark）。
  ・AI 編集・小元素の自動補完（Claude の定時タスク）は secret key を持たないので、ここから live_report() を呼ぶ。
    live_report() は proc = edit / emblem、版面は sizes にある名前、言葉 40 文字・予想 90 分までしか受け付けない。
帯は人に見せるだけなので、失敗しても本体の処理は止めない（何も返さない）。
"""

import json
import pathlib
import sys
import urllib.request

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sitedir  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _db():
    try:
        s = (yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")) or {}).get("settings") or {}
        return (s.get("supabase_url") or "").rstrip("/"), s.get("supabase_key") or ""
    except (OSError, yaml.YAMLError):
        return "", ""


def report(board, proc, state, note=None, eta_min=None):
    """state：work（作業中）/ wait（終わって反映待ち）/ clear（帯を消す。board="*" でその proc の全部）。"""
    url, key = _db()
    if not (url and key):
        return
    body = {"p_account": sitedir.NAME, "p_board": board, "p_proc": proc, "p_state": state, "p_note": note,
            "p_eta_min": None if eta_min is None else max(1, round(eta_min))}
    req = urllib.request.Request(f"{url}/rest/v1/rpc/live_report", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"apikey": key, "Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as err:  # noqa: BLE001
        print(f"  （版面の状態を書けなかった：{board} {state}：{err}）", file=sys.stderr)


def clear(proc, board="*"):
    report(board, proc, "clear")
