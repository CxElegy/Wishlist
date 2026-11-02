"""Supabase が 402（無料枠超過・Fair Use）で返さないときの縮退（2026-11-03，用户定的：11/5 以降は全 API が 402 になりうる）。

Actions の書き込み・読み込みは、402 が来たら「データベースなし」と同じに扱う（supabase() が None を返す＝どの呼び元も
今ある「没配置数据库」の道に入る）。ジョブは落とさず続け、同じ回で二度と呼び直さない。書けなかった分は
state の印（db_news.json など）が進まないので、制限が外れた次の回が自動でまとめて送り直す。
状態は state/supabase_status.json に 1 つだけ（正常⇄制限中が変わったときだけ書く＝コミットが増えない）。管理ページの 1 行が読む。
"""
import datetime as dt
import json
import pathlib

FILE = pathlib.Path(__file__).resolve().parent.parent / "state" / "supabase_status.json"
_OK = False
LIMITED = False   # この処理の中で 402 を見たか（見たら、あとの呼び出しは網に出ずに None）


class Limited(Exception):
    """402 で続けられない（呼び元は飛ばして終わる）。"""


def load(path=None):
    try:
        return json.loads((path or FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(d, path=None):
    p = path or FILE
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mark_limited(where="", path=None):
    """402 を見た。状態が変わるときだけ書く（since は最初に見た時刻のまま）。"""
    global LIMITED
    LIMITED = True
    cur = load(path)
    if cur.get("status") != "limited":
        _write({"status": "limited", "since": _now(), "at": _now(), "where": where[:80]}, path)


def mark_ok(path=None):
    """成功した。制限中だったときだけ「正常」に戻す（毎回は書かない・読むのも 1 処理に 1 回）。"""
    global _OK
    if _OK and path is None:
        return
    _OK = path is None
    cur = load(path)
    if cur.get("status") == "limited":
        _write({"status": "ok", "at": _now(), "was_limited_since": cur.get("since")}, path)


def is_limit(err):
    """HTTPError / RuntimeError('HTTP 402：…') が 402 か。"""
    return getattr(err, "code", None) == 402 or str(err).startswith("HTTP 402")
