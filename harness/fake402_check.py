"""偽の Supabase（全部 402）を相手に、Actions の入口スクリプトを通しで走らせ、docs/・state/・items.yaml などが縮まないことを数える。
2026-11-04：11/5 以降は全部の回が 402 に当たる。sbstate の部品単体の試験（tests/test_sb_degrade.py）では、入口が
402 のときに生成物を空・縮んだ形でコミットしないかは見えない。ここは作業ツリーの写しを作り、items.yaml の supabase_url を
手元の偽サーバーに差して入口を 1 つずつ走らせ、入口ごとに git で「消えた行 − 足した行」を数える。
本番には一切出ない（網は 127.0.0.1 だけ）。入れていない入口：網が要る収集・画像直し（digest.py 本体・repair-images・emblem_fill・library_emblem の本体）。
使い方：python harness/fake402_check.py [--only 名前] [--keep]    # 縮み・失敗があれば終了コード 1
"""
import argparse
import http.server
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable
# (名前, 引数, 秒)  ※ workflow が走らせる順に近い
ENTRIES = [
    ("render", ["scripts/digest.py", "render"], 900),
    ("user_pages", ["scripts/user_pages.py"], 300),
    ("library --push", ["scripts/library.py", "--push"], 300),
    ("library --users", ["scripts/library.py", "--users"], 300),
    ("library_emblem --check", ["scripts/library_emblem.py", "--check"], 300),
    ("library_watch", ["scripts/library_watch.py"], 300),
    ("gate check", ["scripts/gate.py", "check"], 300),
    ("photo_store", ["scripts/photo_store.py", "--minutes", "1"], 300),
    ("photo_store --kick", ["scripts/photo_store.py", "--kick"], 300),
    ("userfeed", ["scripts/userfeed.py"], 300),
    ("collect_watch", ["scripts/collect_watch.py"], 300),
    ("new-items", ["scripts/digest.py", "new-items"], 300),
    ("unedited", ["scripts/digest.py", "unedited"], 300),
]
# 縮んでよい物（名簿）。理由つき。ここに無い物が縮んだら赤。
ALLOW = {
    "state/gate.json": "ゲートは items.yaml の編集の状態から作り直す値（Supabase を読まない）。整理待ちが減れば縮む",
    "state/log/gate.json": "同上の履歴",
}
WATCH = ("docs/", "state/", "inbox/", "reports/", "items.yaml", "wishlist.yaml")


class _H(http.server.BaseHTTPRequestHandler):
    hits = []

    def _r(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        _H.hits.append(f"{self.command} {self.path[:80]}")
        self.send_response(402)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"message":"Fair Use Policy"}')

    do_GET = do_POST = do_PATCH = do_DELETE = do_PUT = _r

    def log_message(self, *a):
        pass


def _git(d, *a):
    return subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=x", *a], cwd=d, capture_output=True, text=True).stdout


def prepare(dst, port):
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True).stdout.split("\0")
    for f in filter(None, files):
        s = ROOT / f
        if s.is_file() and not s.is_symlink():
            (dst / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, dst / f)
    y = dst / "items.yaml"
    t = y.read_text(encoding="utf-8")
    base = "https://bzokpnbcjscbcehdxtjq.supabase.co"
    assert t.count(base) == 1
    y.write_text(t.replace(base, f"http://127.0.0.1:{port}"), encoding="utf-8")
    _git(dst, "init", "-q")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-qm", "base")


def shrunk(d):
    """{ファイル: 縮んだ行数}（消えた行 − 足した行 が正のもの）。消えたファイルは全行。"""
    out = {}
    for line in _git(d, "diff", "--numstat", "HEAD").splitlines():
        a, r, f = line.split("\t", 2)
        if f.startswith(WATCH) and a.isdigit() and r.isdigit() and int(r) > int(a):
            out[f] = int(r) - int(a)
        elif f.startswith(WATCH) and a == "-":      # バイナリ：消えたかだけ
            if not (d / f).exists():
                out[f] = 1
    return out


def run(only=None, keep=False):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    d = pathlib.Path(tempfile.mkdtemp(prefix="fake402_"))
    prepare(d, srv.server_address[1])
    env = {**os.environ, "SUPABASE_SERVICE_KEY": "fake", "HTTPS_PROXY": "", "https_proxy": "", "PYTHONIOENCODING": "utf-8"}
    for k in ("DISCORD_WEBHOOK_URL", "SBSTATE_PING"):
        env.pop(k, None)
    rows, bad = [], []
    for name, args, sec in ENTRIES:
        if only and name != only:
            continue
        h0, t0 = len(_H.hits), time.time()
        try:
            rc = subprocess.run([PY, *args], cwd=d, env=env, capture_output=True, text=True, timeout=sec).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        s = shrunk(d)
        bad_files = {f: n for f, n in s.items() if f not in ALLOW}
        rows.append((name, rc, len(_H.hits) - h0, sum(s.values()), bad_files, int(time.time() - t0)))
        if rc != 0:
            bad.append(f"{name}：終了コード {rc}（402 で落ちてはいけない）")
        for f, n in bad_files.items():
            bad.append(f"{name}：{f} が {n} 行縮んだ（名簿に無い）")
        _git(d, "add", "-A")
        _git(d, "commit", "-qm", name, "--allow-empty")   # 次の入口の差を、その入口だけの変化にする
    srv.shutdown()
    if not keep:
        shutil.rmtree(d, ignore_errors=True)
    print(f"{'入口':26}{'終了':>8}{'402を受けた':>12}{'縮んだ行(名簿内含む)':>20}{'秒':>6}")
    for name, rc, hits, n, bf, sec in rows:
        print(f"{name:26}{str(rc):>8}{hits:>12}{n:>20}{sec:>6}")
    for b in bad:
        print("✗", b)
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sys.exit(1 if run(a.only, a.keep) else 0)
