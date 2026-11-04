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


def _ping(text):
    """状態が変わった瞬間だけ Discord に 1 通（DISCORD_WEBHOOK_URL が無ければ何もしない・失敗しても続ける）。"""
    import os
    import urllib.request
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return False
    try:
        req = urllib.request.Request(url, data=json.dumps({"content": text, "allowed_mentions": {"parse": []}}).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "wishlist-sbstate"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def _announce(path=None):
    """Discord に 1 通は「状態を git に残す回」だけが送る（SBSTATE_PING=1・digest.yml）。ほかの回は状態を書くだけで送らない。
    告げた状態は told に残す。git に残らない回が毎回「まだ告げていない」と見て送り直すのを防ぐ（2026-11-04）。"""
    import os
    if not os.environ.get("SBSTATE_PING"):
        return
    cur = load(path)
    st = cur.get("status", "ok")
    if st == cur.get("told", "ok"):
        return
    if st == "limited":
        text = "Supabase が制限中（402・無料枠超過）に入りました。ページは静的のまま、👍・ログインは休止します。収集は止まらず、解けた次の回が送り直します。管理ページ https://cxelegy.github.io/Wishlist/home/admin.html"
    else:
        text = f"Supabase の制限（402）が解けました（{cur.get('since') or cur.get('was_limited_since', '?')} から）。通常に戻ります。"
    _ping(text)
    _write({**cur, "told": st}, path)


def mark_limited(where="", path=None):
    """402 を見た。状態が変わるときだけ書く（since は最初に見た時刻のまま）。告げるのは _announce。"""
    global LIMITED
    LIMITED = True
    cur = load(path)
    if cur.get("status") != "limited":
        _write({"status": "limited", "since": _now(), "at": _now(), "where": where[:80], "told": cur.get("told", "ok")}, path)
    _announce(path)


def mark_ok(path=None):
    """成功した。制限中だったときだけ「正常」に戻す（毎回は書かない・読むのも 1 処理に 1 回）。"""
    global _OK
    if _OK and path is None:
        return
    _OK = path is None
    cur = load(path)
    if cur.get("status") == "limited":
        _write({"status": "ok", "at": _now(), "was_limited_since": cur.get("since"), "told": cur.get("told", "ok")}, path)
    _announce(path)


# 書けなかった公開データの置き場（state/sb_outbox.json）。印（db_news.json など）で送り直せるもの〔news・stories・価格〕は要らない。
# 印のない一過性の行〔live_log〕だけ、制限中は ここに溜め、次に書けた回が先に送る。お客さまのデータ〔👍・本人のページ〕は溜めない。
OUTBOX = FILE.parent / "sb_outbox.json"
OUTBOX_CAP = 400


def outbox_put(name, rows, path=None):
    p = path or OUTBOX
    d = load(p)
    d[name] = (d.get(name, []) + list(rows))[-OUTBOX_CAP:]
    _write(d, p)


def outbox_take(name, path=None):
    """溜めた行を取り出す（空にする）。無ければ []（ファイルは作らない）。"""
    p = path or OUTBOX
    d = load(p)
    rows = d.pop(name, [])
    if rows:
        _write(d, p)
    return rows


_MEMO = {}


def memo(key, ttl, fn):
    """同じ処理の中で同じ読み取りを何度も網に出さない（Actions の見回りの API 回数を減らす）。
    Actions（SUPABASE_SERVICE_KEY あり）のときだけ ttl 秒覚える。試験・手元では毎回 fn。"""
    import os
    import time
    if not os.environ.get("SUPABASE_SERVICE_KEY"):
        return fn()
    hit = _MEMO.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _MEMO[key] = (time.time(), val)
    return val


def need_db(msg):
    """DB が要る道具が DB を得られなかったとき：制限中（402）なら緑で終える（次の回が拾う）、それ以外は今までどおり落とす。"""
    if LIMITED:
        print(f"Supabase が制限中（402）なので何もせず終える：{msg}")
        raise SystemExit(0)
    raise SystemExit(msg)


def sb_open(req, timeout=30):
    """Supabase（rest・rpc・storage）へ出る urlopen の入口。402 は Limited にして状態へ書き、以後は網に出ない。
    直に urlopen すると 402 を見落として呼び続ける（tests/test_sb_degrade の「直書きは名簿の外 0」が数える）。"""
    import urllib.error
    import urllib.request
    where = req.full_url.split("?")[0].split("/v1/")[-1][:80]
    if LIMITED:
        raise Limited(where)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as err:
        if err.code == 402:
            mark_limited(where)
            raise Limited(where) from None
        raise


def is_limit(err):
    """HTTPError / RuntimeError('HTTP 402：…') が 402 か。"""
    return getattr(err, "code", None) == 402 or str(err).startswith("HTTP 402")
