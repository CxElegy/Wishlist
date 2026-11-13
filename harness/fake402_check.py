"""偽の Supabase（全部 402）を相手に、Actions の入口スクリプトを通しで走らせ、docs/・state/・items.yaml などが縮まないことを数える。
2026-11-04：11/5 以降は全部の回が 402 に当たる。sbstate の部品単体の試験（tests/test_sb_degrade.py）では、入口が
402 のときに生成物を空・縮んだ形でコミットしないかは見えない。ここは作業ツリーの写しを作り、items.yaml の supabase_url を
手元の偽サーバーに差して入口を 1 つずつ走らせ、入口ごとに git で「消えた行 − 足した行」を数える。
本番には一切出ない（網は 127.0.0.1 だけ）。入口の名簿は workflow の入口を全部数える点検（tests/test_fake402.py）で覆う。
使い方：python harness/fake402_check.py [--only 名前] [--keep]    # 縮み・失敗があれば終了コード 1
"""
import argparse
import http.server
import os
import pathlib
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sbconf  # noqa: E402
REAL = sbconf.url()   # 接続先は items.yaml から（偽サーバーに差し替える前の値）
PY = sys.executable
# (名前, 引数, 秒)  ※ workflow が走らせる順に近い
ENTRIES = [
    ("render", ["scripts/digest.py", "render"], 900),
    ("user_pages", ["scripts/user_pages.py"], 300),
    ("library --push", ["scripts/library.py", "--push"], 300),
    ("library --users", ["scripts/library.py", "--users"], 300),
    ("library_emblem --check", ["scripts/library_emblem.py", "--check"], 300),
    ("library_watch", ["scripts/library_watch.py"], 300),
    ("lib_queue sync", ["scripts/lib_queue.py", "sync"], 300),
    ("library_design --auto", ["scripts/library_design.py", "--auto"], 300),
    ("gate check", ["scripts/gate.py", "check"], 300),
    ("photo_store", ["scripts/photo_store.py", "--minutes", "1"], 300),
    ("photo_store --kick", ["scripts/photo_store.py", "--kick"], 300),
    ("userfeed", ["scripts/userfeed.py"], 300),
    ("collect_watch", ["scripts/collect_watch.py"], 300),
    ("new-items", ["scripts/digest.py", "new-items"], 300),
    ("unedited", ["scripts/digest.py", "unedited"], 300),
    ("library --refresh", ["scripts/library.py", "--refresh"], 300),
    ("library --compare", ["scripts/library.py", "--compare"], 300),
    ("library_emblem --minutes", ["scripts/library_emblem.py", "--minutes", "1"], 300),
    ("take-items", ["scripts/digest.py", "take-items"], 300),
    ("notify-changes", ["scripts/digest.py", "notify-changes"], 300),
    ("notify-wishlist", ["scripts/digest.py", "notify-wishlist"], 300),
    ("notify-new-items", ["scripts/digest.py", "notify-new-items"], 300),
    ("notify-urgent", ["scripts/digest.py", "notify-urgent"], 300),
    ("notify-weekly", ["scripts/digest.py", "notify-weekly"], 300),
    ("clear-waits", ["scripts/livestatus.py", "clear-waits"], 300),
    ("gate fire", ["scripts/gate.py", "fire"], 300),
    ("emblem_fill", ["scripts/emblem_fill.py", "--background", "--minutes", "1"], 300),
    # 収集の本体（digest.yml の bare `python scripts/digest.py`）と ingest。外の網は無い（= 外の網が落ちた回）。先頭 3 版面だけ（WL_COLLECT_LIMIT）
    ("digest all", ["scripts/digest.py"], 900),
    ("digest ingest", ["scripts/digest.py", "ingest"], 900),
    ("repair-images", ["scripts/digest.py", "repair-images"], 900),
]
# 入口ごとに足す環境変数（試験用の止める口）
ENTRY_ENV = {"digest all": {"WL_COLLECT_LIMIT": "3"}, "digest ingest": {"WL_COLLECT_LIMIT": "3"},
             "repair-images": {"WL_REPAIR_LIMIT": "40"}}
# 入口を走らせない物（理由つき）。workflow の入口の数え漏れ点検（tests）はここも名簿として見る。キー = 「スクリプト 最初の引数」
NOT_COVERED = {
    "harness/run_tests.py": "CI の試験を流すだけ。本物の Supabase に触らない",
    "scripts/check_arch.py": "CI の点検。Supabase に触らない",
    "scripts/pc_watch.py": "PC のサーバーの死活を見て Discord へ知らせるだけ（鍵なし・docs/・state/ に書かない）。402 も「届かない」と数えて緑で終わる",
    "scripts/gate_fire.py": "git の fetch・reset・push と AI 編集の予約を起こす POST だけ（判断は gate.py check / fire の入口〔上の gate check・gate fire〕と同じ道で、Supabase は edit_control の読み取りのみ・sbstate で 402 を数える）。作業ツリーを origin/main に合わせ直すので、試走の写しの中では走らせない。tests/test_gate_fire.py が本物の git と偽の POST で通す",
    "scripts/pull_rebase.py": "git の取り込みだけ。Supabase に触らない",
    "scripts/push_main.py": "git の取り込みと push だけ（pull_rebase と同じ）。Supabase に触らない",
    "scripts/digest.py mark-items": "push のあと WL_ITEM_MARKS の印で item_requests に done を付けるだけ（docs/・state/ に書かない）。402 なら警告して終わり、依頼は pending のまま次の回が拾う",
    "harness/ask_remind.py": "Discord への通知だけ。Supabase に触らない",
    "harness/pages_photos.py": "Pages の写真の写しを公開物に並べるだけ（git に入れない）。Supabase に触らない",
    "harness/before_after.py": "Discord への Before/After だけ。Supabase に触らない",
    "harness/d5_sample.py": "テストグラウンドの見本を作るだけ。Supabase に触らない",
    "harness/photo_cache_fill.py": "走らせない（無料枠の決まり）。取り先は state/photo_store.json の base ＝本番の storage で、偽サーバーに差せない。走らせると本番の Supabase に出て、手元の写し（~/.cache/wl_photo_cache）も消す。取り先を差せる形にしてから入口に足す（別の段）",
    "harness/fake402_check.py": "この点検自身（fake402.yml が回す）",
    "harness/js_check.py docs/home": "CI の点検。生成した網页の埋め込み JS を node --check するだけ。Supabase に触らない",
    "harness/page_errors.py home/index.html": "CI の点検。手元の http で 2 ページを開き例外を数えるだけ（網は 127.0.0.1 だけ・browser.launch で Supabase も止める）",
    "harness/pages_health.py": "Pages の健康を数える読み取り（boards を読むだけで docs/・state/ に書かない）。402 なら測れずで終わる。別の段で入口に足す",
}
# 402 を 1 回も受けなくてよい入口（Supabase に届かずに終わるのが正しい物）。ここに無いのに 0 回なら赤。
NO_HITS = {
    "library_watch": "Supabase を使わない（scripts/library_watch.py に sbread・sbstate・supabase が無い）。ローカルの写しを数えるだけ",
    "collect_watch": "Supabase を使わない（scripts/collect_watch.py に sbread・sbstate・supabase が無い）",
    "gate check": "ローカルの state/ から作り直す値だけ。Supabase を読む edit_mode は gate fire の側（そちらは 402 を 1 回受ける）",
    "gate fire": "AI 編集の整理待ちがあるときだけ edit_mode（Supabase）を読む。待ちが無い回（CI の写しの state/ による）は 0 回で正しい＝手元と CI で回数が違う",
    "photo_store --kick": "ローカルで置いていない枚数を数え、あれば gh で photo_store.yml を起こすだけ（Supabase に触らない）",
    "new-items": "ローカルの inbox/ を読むだけ",
    "unedited": "ローカルの inbox/・edit.json を読むだけ",
    "library --refresh": "Wikidata（外の網）とローカルの items.yaml だけ。boards への書き込みは library --push 側",
    "library --compare": "ローカルの items.yaml を規則で比べて表示するだけ",
    "notify-changes": "ローカルの reports/ を読んで Discord へ送るだけ（webhook が無ければ何もしない）",
    "notify-wishlist": "ローカルの wishlist.yaml を読んで Discord へ送るだけ",
    "notify-new-items": "ローカルの items.yaml を読んで Discord へ送るだけ",
    "notify-urgent": "ローカルの inbox/ を読んで Discord へ送るだけ",
    "notify-weekly": "ローカルの reports/ を読んで Discord へ送るだけ",
}
# 終了コードが 0 でなくてよい入口（理由つき）
RC_OK = {
    "notify-weekly": (1, "Discord の webhook が無いと 1 で終わる。workflow は if ...; then で受けて「周报发送失败」と出すだけ（402 とは無関係）"),
}
# 縮んでよい物（名簿）。理由つき。ここに無い物が縮んだら赤。
ALLOW = {
    "state/gate.json": "ゲートは items.yaml の編集の状態から作り直す値（Supabase を読まない）。整理待ちが減れば縮む",
    "state/log/gate.json": "同上の履歴",
    "state/emblem_progress.json": "last_run（最後の 1 回の記録）を上書きするだけ。進捗の本体は変わらない（done が空の回は記録が短い）",
    "state/log/emblem.json": "同上の回の記録（最後の回が置き換わる）",
    "state/log/collect.json": "実行ログは件数の上限で古い順に落とす（回の記録が増えれば古い行が出ていく）",
    "state/recommend.json": "推薦は inbox の窓から毎回作り直す（候補が 1〜数件入れ替わる）。RATIO の割合を超えて縮めば赤",
    "state/photo_store.json": "stat（bad など集計の数字）は毎回数え直すので桁が減ると数バイト縮む。台帳 p が縮めば RATIO（2 %）を超えて赤",
    "state/hdimg.json": "高画質化の記録は今の報告・推薦の窓にある画像だけ残す（窓から出たものが落ちる）",
    "state/img_retry.json": "画像の再試行の記録は期限が来たものを落とす",
}
# 名簿の中でも、元のバイト数のこの割合を超えて縮んだら赤（窓の入れ替わりは数 % で、空にされたら 100 %）
RATIO = {"state/photo_store.json": 0.02, "state/recommend.json": 0.2, "state/hdimg.json": 0.2, "state/img_retry.json": 0.3, "state/log/collect.json": 0.5}
# 縮んでよいファイルの数の上限つきの名簿（前方一致）。
ALLOW_COUNT = {"docs/home/pics/": (10, "hdimg が使わなくなった写しを消す（窓から出た分）。10 枚を超える消え方は赤")}
# 土台を作り直す入口（2026-11-13）：docs/ を書く入口は、PR の「コミット済みの docs/home」ではなく、PR 自身のコードを
# 402 でない偽サーバー（200 で空の JSON を返す）で 1 回走らせた結果を土台にして、その上で 402 を当てて差を数える。
# こうすると render.py を正しく変えて出力が縮む PR でも docs/home をコミットし直さなくてよい（main では render.yml が合併のたびに
# docs/home を作り直すので、docs/home を含む PR は合併のたびに競合していた）。縮みとして赤になるのは 402 のせいの分だけ。
REBASE = {"render", "user_pages"}
WATCH = ("docs/", "state/", "inbox/", "reports/", "items.yaml", "wishlist.yaml")


def _replay(method, path, root):
    """土台の回の偽サーバーの返事。空の `[]` だと、digest.py が state/ の写し（feedback・sizes・nav_schemes）を「空の本物」で
    上書きして、そのあとの 402 の回が読む写しまで空になり、402 で写しに戻れなくなっても気づけない。だから、写しのある表は
    コミット済みの state/ の写しを、Supabase が返す形にして返す（動いている Supabase の代わり）。写しの無い表は空。"""
    import json
    if method != "GET" or root is None:
        return b"[]"
    table = path.split("?")[0].rsplit("/", 1)[-1]
    try:
        if table == "feedback":
            rows = json.loads((root / "state" / "feedback.json").read_text(encoding="utf-8")).get("rows", [])
        elif table == "sizes":
            rows = [{"item": k, "size": v} for k, v in json.loads((root / "state" / "sizes.json").read_text(encoding="utf-8")).items()]
        elif table == "nav_schemes":
            rows = [{"section": k, "scheme": v} for k, v in json.loads((root / "state" / "nav_schemes.json").read_text(encoding="utf-8")).items()]
        else:
            rows = []
    except (OSError, ValueError, AttributeError):
        rows = []
    return json.dumps(rows, ensure_ascii=False).encode()


class _H(http.server.BaseHTTPRequestHandler):
    hits = []      # 作業枠（worker）ごとに make_handler が自分の hits を持たせる

    def _r(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        if getattr(self.server, "ok", False):      # 土台を作る回：動いている Supabase の代わり（空の結果）
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_replay(self.command, self.path, getattr(self.server, "root", None)))
            return
        self.server.hits.append(f"{self.command} {self.path[:80]}")
        self.send_response(402)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"message":"Fair Use Policy"}')

    do_GET = do_POST = do_PATCH = do_DELETE = do_PUT = _r

    def log_message(self, *a):
        pass


def _git(d, *a):
    return subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=x", *a], cwd=d, capture_output=True, text=True,
                          errors="replace").stdout   # 画像など utf-8 でない中身で作業枠ごと落ちていた（2026-11-05 repair-images）


def prepare(dst, port):
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True).stdout.split("\0")
    for f in filter(None, files):
        s = ROOT / f
        if s.is_file() and not s.is_symlink():
            (dst / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, dst / f)
    y = dst / "items.yaml"
    t = y.read_text(encoding="utf-8")
    base = re.search(r'supabase_url:\s*"([^"]+)"', t).group(1)   # 接続先は items.yaml から（2026-11-07 自前版に替えた）
    assert t.count(base) == 1
    y.write_text(t.replace(base, f"http://127.0.0.1:{port}"), encoding="utf-8")
    _git(dst, "init", "-q")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-qm", "base")


def _leaves(x):
    if isinstance(x, dict):
        return sum(_leaves(v) for v in x.values()) or 1
    if isinstance(x, list):
        return sum(_leaves(v) for v in x) or 1
    return 1


def _json_shrink(d, f, fake=""):
    """JSON は行数では見えない（1 行に詰めた中身が空になっても 1 行消えて 1 行足すだけ）。
    バイト数が減る、または要素（葉）の数が減ったら縮み。返すのは減ったバイト数（要素だけ減ったときは 1）。"""
    import json
    old = _git(d, "show", f"HEAD:{f}")
    try:
        new = (d / f).read_text(encoding="utf-8")
    except OSError:
        return len(old.encode()) or 1      # 消えた
    new = new.replace(fake, REAL) if fake else new
    if new == old:
        return 0
    try:
        jo, jn = json.loads(old), json.loads(new)
        lo, ln = _leaves(jo), _leaves(jn)
    except ValueError:
        return 0
    if f.startswith("reports/") and isinstance(jo, dict) and isinstance(jn, dict) and jo.get("edit_sig") != jn.get("edit_sig"):
        return 0   # 報告が古い edit.json で出ていた（収集の回と AI 編集が重なった）：新しい編集で出し直した（digest.py の edit_sig の規則。402 とは無関係）
    nb = len(old.encode()) - len(new.encode())
    return max(nb, 1) if (nb > 0 or ln < lo) else 0


def shrunk(d, fake=""):
    """{ファイル: 縮んだ量}。行ファイルは 消えた行 − 足した行 が正のもの、消えたファイルは全行。
    .json はバイト数・要素数でも比べる（1 行 JSON の穴、2026-11-04）。"""
    out = {}
    for line in _git(d, "diff", "--numstat", "HEAD").splitlines():
        a, r, f = line.split("\t", 2)
        if f.startswith(WATCH) and f.endswith(".json") and a != "-":
            n = _json_shrink(d, f, fake)
            if n:
                out[f] = n
        elif f.startswith(WATCH) and a.isdigit() and r.isdigit() and int(r) > int(a):
            out[f] = int(r) - int(a)
        elif f.startswith(WATCH) and a == "-":      # バイナリ：消えたかだけ
            if not (d / f).exists():
                out[f] = 1
    return out


def baseline(d, srv, args, env, sec, name):
    """402 でない偽サーバーで入口を 1 回走らせ、その出力を土台としてコミットする（落ちても続ける：土台が作れなければ今までの比べ方）。"""
    srv.ok, srv.root = True, d
    try:
        subprocess.run([PY, *args], cwd=d, env=env, capture_output=True, text=True, timeout=sec)
    except subprocess.TimeoutExpired:
        pass
    finally:
        srv.ok = False
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", f"baseline {name}", "--allow-empty")


def _worker(q, results, env, keep):
    """作業枠 1 つ = 偽サーバー 1 つ + 作業ツリーの写し 1 つ。入口は枠の中では 1 本ずつ（差を入口だけの変化にするため）、枠どうしは並べて走らせる。"""
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    srv.hits = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    d = pathlib.Path(tempfile.mkdtemp(prefix="fake402_"))
    fake = f"http://127.0.0.1:{srv.server_address[1]}"
    prepare(d, srv.server_address[1])
    while True:
        try:
            i, name, args, sec = q.get_nowait()
        except queue.Empty:
            break
        e = {**env, **ENTRY_ENV.get(name, {})}
        if name in REBASE:
            baseline(d, srv, args, e, sec, name)
        h0, t0 = len(srv.hits), time.time()
        try:
            rc = subprocess.run([PY, *args], cwd=d, env=e, capture_output=True, text=True, timeout=sec).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        s = shrunk(d, fake)
        bad_files = {f: n for f, n in s.items() if f not in ALLOW}
        for f, n in s.items():   # 名簿の割合を見るのは RATIO のものだけ（写真などの binary を文字として読まない：repair-images が webp を消すと UnicodeDecodeError で作業枠が落ちた）
            if f in RATIO and n > len(_git(d, "show", f"HEAD:{f}").encode()) * RATIO[f]:
                bad_files[f] = n
        for pre, (mx, _) in ALLOW_COUNT.items():
            hit = [f for f in bad_files if f.startswith(pre)]
            if len(hit) <= mx:
                for f in hit:
                    bad_files.pop(f)
        hits = len(srv.hits) - h0
        bad = []
        if rc != RC_OK.get(name, (0,))[0]:
            bad.append(f"{name}：終了コード {rc}（402 で落ちてはいけない）")
        if rc in (0, RC_OK.get(name, (0,))[0]) and hits == 0 and name not in NO_HITS:
            bad.append(f"{name}：402 を 1 回も受けていない（Supabase に届く前に静かに終わった。縮み 0 の根拠にならない）")
        for f, n in bad_files.items():
            bad.append(f"{name}：{f} が {n} 行縮んだ（名簿に無い）")
        sec_used = int(time.time() - t0)
        results[i] = ((name, rc, hits, sum(s.values()), bad_files, sec_used), bad)
        print(f"  {name}: {sec_used}s", flush=True)
        _git(d, "add", "-A")
        _git(d, "commit", "-qm", name, "--allow-empty")   # 次の入口の差を、その入口だけの変化にする
    srv.shutdown()
    if not keep:
        shutil.rmtree(d, ignore_errors=True)


def run(only=None, keep=False, workers=None):
    """入口を並べて走らせる。枠の数は WL_FAKE402_WORKERS（既定 4）。網は使わない（外へはつながない）ので並べても入口どうしは邪魔しない。"""
    # 外の網は「落ちている」状態にする：プロキシを閉じたポートに向ける（接続拒否＝網エラー）。この環境は直につなぐと遮断ページが 404/403 を返すので、
    # 空にするだけでは「網エラー」ではなく「404 の判定」になってしまう。偽サーバー（127.0.0.1）だけは除外する
    dead = "http://127.0.0.1:9"
    env = {**os.environ, "SUPABASE_SERVICE_KEY": "fake", "PYTHONIOENCODING": "utf-8", "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
           **{k: dead for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")}}
    # 偽の時計：再試行の待ち（time.sleep）を飛ばす。待ちが 50〜90 秒あった入口（library --refresh・repair-images）が数秒になる
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "harness" / "fake_clock"), env.get("PYTHONPATH")]))
    for k in ("DISCORD_WEBHOOK_URL", "SBSTATE_PING"):
        env.pop(k, None)
    todo = [(i, n, a, s) for i, (n, a, s) in enumerate(ENTRIES) if not only or n == only]
    q = queue.Queue()
    # 長い入口（収集・描画）を先に配って、最後に長いのが残らないようにする
    for e in sorted(todo, key=lambda e: -e[3]):
        q.put(e)
    n = max(1, min(workers or int(os.environ.get("WL_FAKE402_WORKERS", "4")), len(todo) or 1))
    results = {}
    ths = [threading.Thread(target=_worker, args=(q, results, env, keep)) for _ in range(n)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    rows, bad = [], []
    for i, _, _, _ in todo:
        if i not in results:
            bad.append(f"{ENTRIES[i][0]}：走らなかった（作業枠が落ちた）")
            continue
        r, b = results[i]
        rows.append(r)
        bad += b
    print(f"{'入口':26}{'終了':>8}{'402を受けた':>12}{'縮んだ量(名簿内含む)':>20}{'秒':>6}")
    for name, rc, hits, n, bf, sec in rows:
        print(f"{name:26}{str(rc):>8}{hits:>12}{n:>20}{sec:>6}")
    for b in bad:
        print("✗", b)
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workers", type=int)
    a = ap.parse_args()
    sys.exit(1 if run(a.only, a.keep, a.workers) else 0)
