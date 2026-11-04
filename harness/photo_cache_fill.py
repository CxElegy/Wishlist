"""写しを埋める 1 日 1 回の決まった 1 つの仕事（photo_cache.yml）。点検・係は写しを読むだけで本番から落とさない（browser.FILL_MAX=0）。
docs/ の html にある Supabase の写真・小元素の網址のうち、写しに無いものだけを 1 回の上限バイト数まで落とす（残りは翌日）。
html に無くなった写しは消す（溜めない）。"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser  # noqa: E402
import sbread  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
URL = re.compile(r"https://[^/\"'\s)]+\.supabase\.co/storage/[^\"'\s)<>]+")
MAX_BYTES = int(float(os.environ.get("WL_FILL_MAX_MB") or 100) * 1024 * 1024)   # 1 回で落とす量（既定 100 MB。初回だけ workflow_dispatch の入力 max_mb で上げる）
MAX_SECONDS = int(os.environ.get("WL_FILL_MAX_MIN") or 12) * 60   # 時間の上限（workflow の timeout より前に止め、写しを保存させる）


EMB = re.compile(r"/storage/v1/object/public/emblems/([0-9A-Za-z_.-]+\.webp)")
PAGES = re.compile(r"https://cxelegy\.github\.io/Wishlist/p/([0-9a-f]{16}-\d+\.webp)")   # 旗 on のあとの網址（落とし先は Supabase の photos のまま）


def board_text(settings, table="boards", cols="config"):
    """DB の表を 1 回の GET で文字にして返す（読むだけ。鍵は SUPABASE_SERVICE_KEY、無ければ anon）。取れなければ空。"""
    try:
        base = settings["supabase_url"].rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_KEY") or settings["supabase_key"]   # 非公開の版面（boards_visible）は secret key でないと見えない
        return sbread.get("%s/rest/v1/%s?select=%s" % (base, table, cols), key, ttl=0)[0].decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print("DB を読めない", table, type(e).__name__, str(e)[:120])
        return ""


def board_emblems(settings):
    """お客さまの版面の小元素（boards.config の emblems 箱の網址。anon は非公開の版面が見えないので Actions では SUPABASE_SERVICE_KEY で読む）。docs/ の html に無いので DB から名前を数える（読むだけ・1 回の GET）。
    user_pages が /p/ に書き換える対象と同じ名前。取れなければ空（次の回で足す）。"""
    return set(EMB.findall(board_text(settings)))


def urls():
    seen = {}
    base = ""
    try:
        base = json.loads((ROOT / "state" / "photo_store.json").read_text(encoding="utf-8")).get("base", "").rstrip("/")
    except (OSError, ValueError):
        pass
    for f in (ROOT / "docs").rglob("*.html"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for u in URL.findall(text):
            seen.setdefault(browser._name(u), u)
        for n in PAGES.findall(text) if base else ():
            seen.setdefault(n, f"{base}/storage/v1/object/public/photos/{n}")
    # 置き場にある写真は全部（2026-11-03）：お客さまのページ（Supabase の pages 箱）は docs/ に無く、render と同じ photo_store.stored() が /p/ の網址を出すので、
    # docs/ だけ見ると 1,194 枚が /p/ で 404（ログイン中の画面で落ち先の Supabase に戻り egress になる）。stored() が出せる名前＝写しの対象。
    try:
        for k in json.loads((ROOT / "state" / "photo_store.json").read_text(encoding="utf-8")).get("p", {}) if base else ():
            for w in (400, 800):
                seen.setdefault(f"{k}-{w}.webp", f"{base}/storage/v1/object/public/photos/{k}-{w}.webp")
    except (OSError, ValueError):
        pass
    return seen


def board_urls():
    """DB から数える小元素の取得先（{名前: 網址}）。urls() とは別（試験はネットに出ない）。
    Actions の runner には PyYAML が無い（2026-11-03：import yaml が握りつぶされ 0 件だった）→ items.yaml は正規表現で読む。"""
    txt = (ROOT / "items.yaml").read_text(encoding="utf-8")
    st = {k: (re.search(rf"^\s*{k}:\s*[\"']?([^\s\"']+)", txt, re.M) or [None, ""])[1] for k in ("supabase_url", "supabase_key")}
    return {n: f"{st['supabase_url'].rstrip('/')}/storage/v1/object/public/emblems/{n}" for n in board_emblems(st)}


def main():
    want = urls()
    try:
        b = board_urls()
        print(f"お客さまの小元素 {len(b)} 種（鍵：{'secret' if os.environ.get('SUPABASE_SERVICE_KEY') else 'anon＝非公開の版面は見えない'}）")
        for n, u in b.items():
            want.setdefault(n, u)
    except Exception:  # noqa: BLE001
        pass
    browser.CACHE.mkdir(parents=True, exist_ok=True)
    gone = [f for f in browser.CACHE.iterdir() if f.is_file() and f.name not in want]
    for f in gone:
        f.unlink()
    got, t0 = 0, time.time()
    for name, u in want.items():
        if got >= MAX_BYTES or time.time() - t0 > MAX_SECONDS:
            break
        if (browser.CACHE / name).is_file():
            continue
        try:
            got += len(browser.storage_bytes(u, fill=True) or b"")
        except Exception as e:  # noqa: BLE001  1 枚の失敗で止めない
            print("落とせない", u, e)
    left = sum(1 for n in want if not (browser.CACHE / n).is_file())
    print(f"網址 {len(want)} · 消した {len(gone)} · 今回 {got / 1e6:.1f} MB · 残り {left}")
    if os.environ.get("GITHUB_OUTPUT"):   # 変わったときだけ写しを保存し、Pages を出し直す
        with open(os.environ["GITHUB_OUTPUT"], "a") as o:
            o.write(f"changed={'true' if got or gone else 'false'}\n")


if __name__ == "__main__":
    main()
