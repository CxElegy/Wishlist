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


def clear_waits(before=None):
    """「反映を待っています」（state=wait）の行を消す：GitHub Pages の公開が終わった＝反映した（2026-10-25：AI 編集が公開済みなのに
    「反映を待っています」が残り、管理ページの図が「止まっているかも」と出していた）。live_clear.yml が page_build（Pages の公開）のたびに呼ぶ。
    before（ISO の時刻）より前に始まった行だけ。secret key（SUPABASE_SERVICE_KEY）があるときだけ。返り値：消した行の数（わからなければ None）。"""
    import os
    import urllib.parse
    url, _ = _db()
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and key):
        return None
    q = f"account=eq.{urllib.parse.quote(sitedir.NAME)}&state=eq.wait"
    if before:
        q += f"&started_at=lt.{urllib.parse.quote(before)}"
    h = {"apikey": key, "Prefer": "return=representation"}
    if key.startswith("eyJ"):
        h["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{url}/rest/v1/live_status?{q}", headers=h, method="DELETE")
    try:
        return len(json.loads(urllib.request.urlopen(req, timeout=15).read() or b"[]"))
    except Exception as err:  # noqa: BLE001
        print(f"  （反映待ちを消せなかった：{err}）", file=sys.stderr)
        return None


if __name__ == "__main__" and sys.argv[1:2] == ["clear-waits"]:
    print("反映待ちを消した：", clear_waits(sys.argv[2] if len(sys.argv) > 2 else None))


class Lines:
    """管理ページ「ライブログ」に作業の 1 行 1 行を流す（Supabase の live_log 表、db/live_log.sql）。
    secret key のある GitHub Actions だけが書く（ないとき・テストでは何もしない）。行はためて FLUSH 秒ごとにまとめて送る
    （画面は 3 秒ごとに読む）。送れなくても本体の処理は止めない。"""
    FLUSH = 1.5
    KEEP_DAYS = 2

    def __init__(self, proc, send=None):
        import os
        import threading
        self.proc, self.buf, self.lock = proc, [], threading.Lock()
        self.send = send if send is not None else (self._post if os.environ.get("SUPABASE_SERVICE_KEY") else None)
        self.send = self.send or None   # send=False：テスト（ネットに出ない）
        self.stop = threading.Event()
        self.th = None
        if self.send:
            self.th = threading.Thread(target=self._loop, name=f"live-{proc}", daemon=True)
            self.th.start()

    def add(self, text, board=None, level=None):
        if not self.send:
            return
        import datetime as dt
        text = " ".join(str(text).split())
        if not text:
            return
        if level is None:   # 行の言葉で色を決める（ライブログの lv-*）
            level = ("error" if "[失敗]" in text or "エラー" in text or text.startswith("→ 失敗") else "warn" if text.startswith("[外した]") or "時間切れ" in text
                     else "ok" if text.startswith("→ そろっている") or "目標に届いた" in text else "info")
        with self.lock:
            self.buf.append({"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"), "proc": self.proc,
                             "board": board, "level": level, "text": text[:400]})

    def _loop(self):
        while not self.stop.wait(self.FLUSH):
            self.flush()

    def flush(self):
        with self.lock:
            rows, self.buf = self.buf, []
        if rows:
            try:
                self.send(rows)
            except Exception as err:  # noqa: BLE001
                print(f"  （ライブログに書けなかった：{err}）", file=sys.stderr)

    def close(self):
        self.stop.set()
        if self.th:
            self.th.join(timeout=5)
        self.flush()

    def _post(self, rows):
        import digest
        digest.supabase("live_log", rows, "return=minimal", method="POST")

    def prune(self):
        """2 日より前の行を消す（書く側が自分で片付ける）。"""
        if not self.send or self.send != self._post:
            return
        import datetime as dt
        import digest
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=self.KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            digest.supabase(f"live_log?at=lt.{old}", method="DELETE")
        except Exception as err:  # noqa: BLE001
            print(f"  （ライブログの古い行を消せなかった：{err}）", file=sys.stderr)
