"""公開（Pages）の健康を数える（2026-11-01 BACKLOG「最優先：Pages 公開の失敗」の物差し）。

    python harness/pages_health.py [--hours 24] [--repo CxElegy/Wishlist]

出す：①標準の「pages build and deployment」の回数・失敗（Source が「GitHub Actions」に切り替わると 0 回になる）
②pages.yml（Pages 公開）の回数・失敗・取り消し ③main への提交の数（生成物 / 人 の別）。
終了コード 1：切り替え後に標準の回がまだある・失敗がある（pages.yml の deploy の continue-on-error を外す前の確認にも使う）。
Settings の Source は API の入口が止められているので、標準の回の有無から読む。
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser  # noqa: F401  urllib の止め（free-tier.md）を通す。ここで読むのは Pages だけ

LEGACY = "pages build and deployment"
OURS = "Pages 公開"


def summarize(runs, now, hours=24):
    """runs: Actions API の workflow_runs。{名前: {n, failure, cancelled}} と切り替わったか。"""
    since = now - dt.timedelta(hours=hours)
    out = {}
    for r in runs:
        at = dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        if at < since or r["name"] not in (LEGACY, OURS):
            continue
        s = out.setdefault(r["name"], {"n": 0, "failure": 0, "cancelled": 0, "last": ""})
        s["n"] += 1
        s["failure"] += r.get("conclusion") == "failure"
        s["cancelled"] += r.get("conclusion") == "cancelled"
        s["last"] = max(s["last"], r["created_at"])
    return out


def verdict(s):
    """(ok, 一行)。標準の回が残っている＝Source は未切り替え。"""
    legacy, ours = s.get(LEGACY), s.get(OURS)
    if legacy:
        return False, "Source は未切り替え（標準の回が %d 回・失敗 %d・最後 %s）。Settings → Pages → Source を GitHub Actions に" % (legacy["n"], legacy["failure"], legacy["last"])
    if not ours:
        return False, "公開の回が 0 回（pages.yml が走っていない）"
    if ours["failure"]:
        return False, "pages.yml の失敗 %d 回" % ours["failure"]
    return True, "切り替え済み・pages.yml %d 回（取り消し %d）・失敗 0" % (ours["n"], ours["cancelled"])


def gh_runs(repo, since):
    """標準の回（event=dynamic）と pages.yml の回だけ取る（全部の回は 1 日 2500 件あり paginate で落ちる）。"""
    runs = []
    for path in ("runs?event=dynamic", "workflows/pages.yml/runs?"):
        out = subprocess.run(["gh", "api", "repos/%s/actions/%s&per_page=100&created=>%s" % (repo, path, since), "--jq", ".workflow_runs[]|{name,created_at,conclusion}"],
                             capture_output=True, text=True, check=True).stdout
        runs += [json.loads(x) for x in out.splitlines() if x.strip()]
    return runs


ROOT = Path(__file__).resolve().parent.parent
PAGES_P = "https://cxelegy.github.io/Wishlist/p"
WIDTHS = (400, 800)   # scripts/photo_store.py の WIDTHS と同じ
READY = 0.99   # 載っている写真のうち Pages に並んでいる割合がこれ以上で旗を on にしてよい


def wanted(docs):
    """docs の html が使う写真の名前（<指紋>-<幅>.webp。Supabase の網址でも Pages の網址でも）。"""
    out = set()
    for f in Path(docs).rglob("*.html"):
        out |= set(re.findall(r"/(?:photos|p)/([0-9a-f]{16}-\d+\.webp)", f.read_text(encoding="utf-8", errors="ignore")))
    return out


def wanted_from_store(path=None):
    """state/photo_store.json の p（置き場にある写真の指紋）× 幅の名前。docs/*.html に載らない写真（お客さまの pages 箱だけにある写真）も数える。"""
    f = Path(path) if path else ROOT / "state" / "photo_store.json"
    try:
        p = json.loads(f.read_text(encoding="utf-8")).get("p", {})
    except (OSError, ValueError):
        return set()
    return {"%s-%d.webp" % (k, w) for k in p for w in WIDTHS}


def photos_verdict(manifest, want, sample_ok=True):
    """(ok, 一行)。manifest＝公開中の Pages の p/manifest.json（取れなければ None＝Source が未切り替え、または写真なしの公開）。"""
    if not manifest or not manifest.get("n"):
        return False, "Pages に写真がない（Source 未切り替え、または写しが空）"
    have = set(manifest.get("names", []))
    cov = len(want & have) / len(want) if want else 0
    if cov < READY:
        return False, "載っている写真 %d 枚のうち Pages に並んでいるのは %.1f%%（%.0f%% 以上で on）" % (len(want), cov * 100, READY * 100)
    if not sample_ok:
        return False, "並んでいるはずの写真の抜き取りが 200 でない"
    return True, "Pages に写真 %d 枚・載っている %d 枚の %.1f%% が並ぶ → 旗を on にしてよい" % (manifest["n"], len(want), cov * 100)


def live_manifest():
    try:
        return json.loads(urllib.request.urlopen(PAGES_P + "/manifest.json", timeout=30).read())
    except Exception:  # noqa: BLE001  404（未切り替え）・通信失敗
        return None


def sample_ok(manifest, k=5):
    names = (manifest or {}).get("names", [])[:: max(1, len((manifest or {}).get("names", [])) // k)][:k]
    try:
        return all(urllib.request.urlopen(urllib.request.Request("%s/%s" % (PAGES_P, n), method="HEAD"), timeout=30).status == 200 for n in names)
    except Exception:  # noqa: BLE001
        return False


def photos_main(set_flag):
    m = live_manifest()
    ok, line = photos_verdict(m, wanted(ROOT / "docs") | wanted_from_store(), sample_ok(m) if m else False)
    print("%s %s" % ("✓" if ok else "✗", line))
    if set_flag:
        (ROOT / "state" / "pages_photos.json").write_text(json.dumps({"on": ok}) + "\n", encoding="utf-8")
        print("旗 on =", ok)
    raise SystemExit(0 if ok else 1)


LIMIT = 1 << 30   # GitHub Pages の公開物の目安 1 GB
WARN = 0.7        # これを超えたら ✗（古い写真を外す規則は消すことなので [?] で聞く）


def size_verdict(manifest, prev=None):
    """(ok, 一行)。manifest["bytes"]＝pages_photos.stage が書いた公開物の合計。prev＝前の測定（バイト）。"""
    b = (manifest or {}).get("bytes")
    if not b:
        return None, "測れず：公開中の manifest に bytes が無い（次の公開から入る）"
    grow = "" if not prev else "・前回より %+.1f MB" % ((b - prev) / 1e6)
    return b <= LIMIT * WARN, "公開物 %.0f MB＝1 GB の %.0f%%（%d%% 超で ✗）%s" % (b / 1e6, b / LIMIT * 100, WARN * 100, grow)


def size_prev(stored, today):
    """前回（前の日）のバイト。きょうの記録が既にあれば、その前（prev）。"""
    s = stored or {}
    return s.get("prev") if s.get("date") == today else s.get("bytes")


def size_next(stored, b, today):
    """--set で書く記録。きょうの分が既にあれば None（1 日 1 回だけ書く＝コミットが増えない）。"""
    if (stored or {}).get("date") == today:
        return None
    return {"bytes": b, "date": today, "prev": (stored or {}).get("bytes")}


def size_main(set_flag):
    f = ROOT / "state" / "pages_size.json"
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    try:
        stored = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = None
    m = live_manifest()
    ok, line = size_verdict(m, size_prev(stored, today))
    print("%s %s" % ("-" if ok is None else "✓" if ok else "✗", line))
    new = size_next(stored, m["bytes"], today) if set_flag and ok is not None else None
    if new:
        f.write_text(json.dumps(new) + "\n", encoding="utf-8")
    raise SystemExit(2 if ok is None else 0 if ok else 1)   # 2＝測れず（失敗ではない。ゲートは - と出す）


def emblems_missing(names, manifest):
    """boards の小元素の名前のうち、Pages の p/manifest.json に無いもの（足りない名前）。manifest が None なら全部。"""
    have = set((manifest or {}).get("names", []))
    return sorted(set(names) - have)


LEAK = re.compile(r"supabase\.co/storage/(?!v1/object/public/emblems/)")


def storage_leaks(text):
    """boards.config・board_stories にある Supabase storage の網址のうち小元素（emblems 箱）以外の数。JS の記事カードは photos 箱を書き換えないので 0 でなければ egress の穴（story の画像が photos 箱になった）。"""
    return len(LEAK.findall(text or ""))


def emblems_main():
    """--emblems：ライブラリの boards.config の小元素の名前 ⊆ Pages の写し。足りない数を出す（DB は読むだけ・1 回の GET。鍵は SUPABASE_SERVICE_KEY、無ければ anon＝公開の版面だけ）。"""
    import photo_cache_fill as f
    txt = (ROOT / "items.yaml").read_text(encoding="utf-8")
    st = {k: (re.search(r"^\s*%s:\s*[\"']?([^\s\"']+)" % k, txt, re.M) or [None, ""])[1] for k in ("supabase_url", "supabase_key")}
    names = f.board_emblems(st)
    if not names:
        print("測れず：boards の小元素の名前を読めない（鍵なし・網なし。anon は非公開の版面が見えない）")
        raise SystemExit(2)
    leaks = storage_leaks(f.board_text(st) + f.board_text(st, "board_stories", "*"))
    print("%s boards・board_stories の小元素以外の storage 網址 %d 件" % ("✓" if not leaks else "✗", leaks))
    miss = emblems_missing(names, live_manifest())
    print("%s boards の小元素 %d 種のうち Pages に無い %d 種 %s" % ("✓" if names and not miss else "✗", len(names), len(miss), miss[:5]))
    raise SystemExit(0 if names and not miss and not leaks else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--repo", default="CxElegy/Wishlist")
    ap.add_argument("--photos", action="store_true", help="写真を Pages から配ってよいかを判定（旗 state/pages_photos.json）")
    ap.add_argument("--set", action="store_true", help="--photos の結果を旗に書く")
    ap.add_argument("--emblems", action="store_true", help="boards の小元素の名前 ⊆ Pages の写し")
    ap.add_argument("--size", action="store_true", help="公開物の大きさ（1 GB の何 %）。--set で今回の値を state/pages_size.json に残す")
    a = ap.parse_args()
    if a.size:
        size_main(a.set)
    if a.emblems:
        emblems_main()
    if a.photos:
        photos_main(a.set)
    now = dt.datetime.now(dt.timezone.utc)
    s = summarize(gh_runs(a.repo, (now - dt.timedelta(hours=a.hours)).strftime("%Y-%m-%d")), now, a.hours)
    n = subprocess.run(["git", "log", "origin/main", "--since=%d hours ago" % a.hours, "--format=%an"], capture_output=True, text=True).stdout.split()
    bot = sum(x == "github-actions[bot]" for x in n)
    ok, line = verdict(s)
    print("%s %s\nmain への提交 %d（生成物 %d・人と係 %d）／%d 時間" % ("✓" if ok else "✗", line, len(n), bot, len(n) - bot, a.hours))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
