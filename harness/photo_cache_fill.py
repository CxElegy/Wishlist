"""写しを埋める 1 日 1 回の決まった 1 つの仕事（photo_cache.yml）。点検・係は写しを読むだけで本番から落とさない（browser.FILL_MAX=0）。
docs/ の html にある Supabase の写真・小元素の網址のうち、写しに無いものだけを 1 回の上限バイト数まで落とす（残りは翌日）。
html に無くなった写しは消す（溜めない）。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
URL = re.compile(r"https://[^/\"'\s)]+\.supabase\.co/storage/[^\"'\s)<>]+")
MAX_BYTES = 100 * 1024 * 1024   # 1 回で落とす量（初回に全部落とすと日の枠を食うので数日に分ける）


def urls():
    seen = {}
    for f in (ROOT / "docs").rglob("*.html"):
        for u in URL.findall(f.read_text(encoding="utf-8", errors="ignore")):
            seen.setdefault(browser._name(u), u)
    return seen


def main():
    want = urls()
    browser.CACHE.mkdir(parents=True, exist_ok=True)
    gone = [f for f in browser.CACHE.iterdir() if f.is_file() and f.name not in want]
    for f in gone:
        f.unlink()
    got = 0
    for name, u in want.items():
        if got >= MAX_BYTES:
            break
        if (browser.CACHE / name).is_file():
            continue
        try:
            got += len(browser.storage_bytes(u))
        except Exception as e:  # noqa: BLE001  1 枚の失敗で止めない
            print("落とせない", u, e)
    left = sum(1 for n in want if not (browser.CACHE / n).is_file())
    print(f"網址 {len(want)} · 消した {len(gone)} · 今回 {got / 1e6:.1f} MB · 残り {left}")


if __name__ == "__main__":
    main()
