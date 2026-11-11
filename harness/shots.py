"""見た目の審査のための絵を、決まった大きさで撮る（ハーネス v2 の「目で確かめる」段。HARNESS_V2.md）。

店長の画面（1333×677）とスマホ（390×844）で、変えた所を撮る。撮るだけで、採点は審査の係が docs/rules/aesthetic.md の番号で付ける。

    python harness/shots.py --dir docs --page home/index.html --sel "#sec-bleach" --out OUT
    python harness/shots.py --url http://127.0.0.1:8123/testground/x.html --out OUT
→ OUT/<ページ>-<幅>x<高さ>[-<n>].png と OUT/shots.json（撮った絵の一覧・横のはみ出し）。--sel が無ければ画面の上から 1 枚。
作った網页（scripts/digest.py render のあと）を撮るときはコンテナの中で：bash harness/shots.sh OUT --page … --sel …
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

VIEWPORTS = ((1333, 677), (390, 844))
MAX_PER_SEL = 3   # 同じセレクタに当たる所は先頭の 3 つまで


def viewports(spec):
    return tuple(tuple(int(n) for n in v.lower().split("x")) for v in spec.split(",")) if spec else VIEWPORTS


def shoot(pg, url, w, h, sels, out, stem):
    import self_review
    pg.set_viewport_size({"width": w, "height": h})
    pg.goto(url, wait_until="load", timeout=60000)
    self_review.load_all(pg)
    pg.add_style_tag(content="*,*::before,*::after{animation:none!important;transition:none!important}")
    rows = []
    wide = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
    if not sels:
        f = out / f"{stem}-{w}x{h}.png"
        pg.screenshot(path=str(f))
        rows.append({"file": f.name, "url": url, "vp": f"{w}x{h}", "sel": "", "wide": wide})
    for sel in sels:
        loc = pg.locator(sel)
        n = min(loc.count(), MAX_PER_SEL)
        if not n:
            rows.append({"file": "", "url": url, "vp": f"{w}x{h}", "sel": sel, "missing": True, "wide": wide})
        for i in range(n):
            # 区切りを画面の上にそろえた位置（吸着した位置。aesthetic E4）で、画面 1 枚をそのまま撮る
            loc.nth(i).evaluate("e => e.scrollIntoView({block: 'start', behavior: 'instant'})")
            pg.wait_for_timeout(250)
            f = out / f"{stem}-{w}x{h}-{re.sub(r'[^A-Za-z0-9]+', '_', sel).strip('_')[:30]}-{i}.png"
            pg.screenshot(path=str(f))
            box = loc.nth(i).bounding_box() or {}
            rows.append({"file": f.name, "url": url, "vp": f"{w}x{h}", "sel": sel, "n": i, "wide": wide,
                         "box": [round(box.get(k, 0)) for k in ("x", "y", "width", "height")]})
    return rows


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--dir")
    a.add_argument("--page", action="append", default=[])
    a.add_argument("--url", action="append", default=[])
    a.add_argument("--sel", action="append", default=[])
    a.add_argument("--vp", default="", help="1333x677,390x844")
    a.add_argument("--out", default="shots")
    args = a.parse_args(argv)
    from playwright.sync_api import sync_playwright
    import browser
    import self_review
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    urls = list(args.url)
    if args.dir:
        port = self_review.serve(args.dir)
        urls += [f"http://127.0.0.1:{port}/{p}" for p in args.page or ["home/index.html"]]
    rows = []
    with sync_playwright() as p:
        b = browser.launch(p)
        ctx = b.new_context(locale="ja-JP")
        pg = ctx.new_page()
        for n, u in enumerate(urls):
            stem = re.sub(r"[^A-Za-z0-9]+", "_", u.split("://", 1)[-1].split("/", 1)[-1]).strip("_") or f"page{n}"
            for w, h in viewports(args.vp):
                rows += shoot(pg, u, w, h, args.sel, out, stem)
        b.close()
    (out / "shots.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(f"{r['vp']} {r['sel'] or '（上から）'} → {r['file'] or '✗ 見つからない'}{'・横にはみ出す ' + str(r['wide']) + 'px' if r['wide'] > 0 else ''}")
    return 1 if any(r.get("missing") or r["wide"] > 0 for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
