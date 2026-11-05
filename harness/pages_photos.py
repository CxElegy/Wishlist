"""pages.yml の build：写真の写し（actions/cache の .photo_cache）を docs/p/ に並べ、公開物に入れる（git には入れない）。
網址は https://cxelegy.github.io/Wishlist/p/<指紋>-<幅>.webp。docs/p/manifest.json に並べた名前を書く（pages_health.py --photos が読む）。
    python harness/pages_photos.py [写しの置き場] [docs]"""
import json
import re
import shutil
import sys
from pathlib import Path

NAME = re.compile(r"[0-9A-Za-z][0-9A-Za-z_-]*\.(webp|jpg|png|svg)")   # svg：外の小元素の Twemoji（photo_store.ext_name）   # photos・emblems の箱のファイル名（指紋-幅.webp ほか）


def stage(cache, docs):
    out = Path(docs) / "p"
    out.mkdir(parents=True, exist_ok=True)
    names = sorted(f.name for f in Path(cache).iterdir() if f.is_file() and NAME.fullmatch(f.name)) if Path(cache).is_dir() else []
    for n in names:
        shutil.copyfile(Path(cache) / n, out / n)
    m = out / "manifest.json"
    size = 0
    for _ in range(3):   # 公開物の合計（Pages は 1 GB まで）。manifest 自身の大きさも入れる（書く→数える→書き直す）。pages.yml は stage のあとに足さない
        m.write_text(json.dumps({"n": len(names), "names": names, "bytes": size}), encoding="utf-8")
        size = sum(f.stat().st_size for f in Path(docs).rglob("*") if f.is_file())
    return len(names)


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ".photo_cache"
    d = sys.argv[2] if len(sys.argv) > 2 else "docs"
    print("docs/p に", stage(c, d), "枚")
