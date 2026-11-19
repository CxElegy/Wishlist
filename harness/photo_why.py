"""写真の無い記事を 1 件ずつ「なぜ取れないか」に分けて数える（2026-11-19 店長「点検は、本物の写真が取れるかどうかを含めること」）。

店長の PC で回す。DB は読まない（記事の網址の一覧は PC の係が DB から引いて渡す）。記事のサイトへは本物の取り方（店長と同じ
sources.resolve_url・images.page・images.pick）で出る。

    python harness/photo_why.py < urls.txt                      # 1 行 1 網址
    python harness/photo_why.py --in stories.json --out D:/Claude/kpi/photo_why.jsonl
        # JSON：網址の list、または [{"url", "title"?, "og"?（_fp/all.json の _og のその網址の値）}]
    python harness/photo_why.py --in stories.json --browser     # 本物のブラウザ（scrapling の StealthyFetcher）なし／ありを比べる

画面に出すのは理由ごとの数と host だけ（お客さまの名前・版面の名前・題・網址の path は出さない）。1 件ずつの行（網址も）は --out の
ファイルにだけ（リポジトリの外でなければ断る。既定は書かない）。
分けるもの：包みか（news.google.com）・原文に戻せたか・HTTP の状態・最後の host・og:image の有無・images.pick の結果の大分類
（images.Result.category）・SAVED か・図の大きさ・og の覚え（user_pages の _og：無い／取れた／取れなかった理由／前の形の ""）。
"""
import argparse
import collections
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import browser  # noqa: E402,F401  urlopen の止め（公開の箱を落とさない）


def host(u):
    return (urllib.parse.urlparse(str(u or "")).hostname or "").lower()


def memo_kind(v):
    """og の覚えの値 → 大分類。"""
    if v is None:
        return "覚え無し"
    if v == "":
        return "前の形の空（試し直しの対象）"
    if isinstance(v, str) or isinstance(v, dict) and v.get("img"):
        return "取れた写真あり"
    if isinstance(v, dict):
        return f"取れなかった：{v.get('why') or '?'}（{v.get('n') or 1} 回）"
    return "読めない形"


class Tools:
    """網に出る道具（試験では差し替える）。"""

    def __init__(self):
        import images
        import sources
        self.images, self.sources = images, sources

    def resolve(self, u):
        return self.sources.resolve_url(u)

    def page(self, u):
        return self.images.page(u)

    def pick(self, title, u):
        e = self.sources.Entry(title=title or "", url=u, published=None, source="")
        return self.images.pick(None, [e], u)

    def size(self, img):
        ok, why = self.images._checks.get(img, (False, ""))
        w, h = self.images.size_of(why) if ok else (0, 0)
        return f"{w}×{h}" if w else ""

    def saved(self, res):
        return self.images.SAVED in (res.source or "")

    def clear(self):
        self.images.clear_cache()


def diagnose(item, tools):
    """1 件 → 行（網址は url の欄だけ。画面には出さない）。"""
    u = item["url"]
    row = {"url": u, "wrapped": "news.google.com" in u, "memo": memo_kind(item.get("og"))}
    real = u
    if row["wrapped"]:
        try:
            real = tools.resolve(u) or u
        except Exception:  # noqa: BLE001
            real = u
        row["resolved"] = "news.google.com" not in real
    p = tools.page(real)
    row["status"] = getattr(p, "status", None) or (200 if p.ok else None)
    row["host"] = host(getattr(p, "final", "") or real)
    row["og"] = bool(p.og or p.jsonld)
    row["page_reason"] = p.reason or ""
    res = tools.pick(item.get("title") or "", real)
    row["category"] = res.category
    row["saved"] = bool(res.image) and tools.saved(res)
    row["size"] = tools.size(res.image) if res.image else ""
    if row["saved"]:
        row["category"] = "无图：SAVED（本站保存が要る＝お客さまには使わない）"
    return row


def summary(rows):
    """理由ごとの数（host と理由だけ。網址の path・題は出さない）。"""
    c = collections.Counter
    lines = [f"記事 {len(rows)} 件"]
    w = [r for r in rows if r["wrapped"]]
    if w:
        lines.append(f"包みの網址 {len(w)} 件：原文に戻せた {sum(1 for r in w if r.get('resolved'))}・戻せない {sum(1 for r in w if not r.get('resolved'))}")
    for name, cnt in (("結果の大分類", c(r["category"] for r in rows)), ("HTTP の状態", c(str(r["status"]) for r in rows)),
                      ("og:image・JSON-LD", c("あり" if r["og"] else "なし" for r in rows)), ("SAVED", c("SAVED" if r["saved"] else "—" for r in rows)),
                      ("og の覚え", c(r["memo"] for r in rows))):
        lines.append(f"{name}：" + "・".join(f"{k} {v}" for k, v in cnt.most_common()))
    bad = c(r["host"] for r in rows if not r["category"].startswith("有图"))
    if bad:
        lines.append("取れない host（上位 10）：" + "・".join(f"{k or '?'} {v}" for k, v in bad.most_common(10)))
    return lines


def read_input(path, stdin):
    text = pathlib.Path(path).read_text(encoding="utf-8") if path else stdin.read()
    try:
        data = json.loads(text)
    except ValueError:
        data = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out = []
    for x in data if isinstance(data, list) else []:
        x = {"url": x} if isinstance(x, str) else x if isinstance(x, dict) else {}
        if str(x.get("url") or "").startswith(("http://", "https://")):
            out.append(x)
    return out


def outside_repo(p):
    p = pathlib.Path(p).resolve()
    return not (p == ROOT or ROOT in p.parents)


def run(items, tools, use_browser=False, quiet=True):
    """→ 行。use_browser：本物のブラウザ（SCRAPLING_BROWSER=1）で読む。ブラウザは開いた網址を stderr に書くので、quiet で黙らせる。"""
    old = os.environ.get("SCRAPLING_BROWSER")
    if use_browser:
        os.environ["SCRAPLING_BROWSER"] = "1"
    else:
        os.environ.pop("SCRAPLING_BROWSER", None)
    tools.clear()
    try:
        with contextlib.redirect_stderr(io.StringIO()) if quiet else contextlib.nullcontext():
            return [diagnose(x, tools) for x in items]
    finally:
        if old is None:
            os.environ.pop("SCRAPLING_BROWSER", None)
        else:
            os.environ["SCRAPLING_BROWSER"] = old


def main(argv=None, tools=None, stdin=None, out=print):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    a = ap.parse_args(argv)
    if a.out and not outside_repo(a.out):
        raise SystemExit("--out はリポジトリの外に（1 件ずつの行には記事の網址が入る）")
    items = read_input(a.inp, stdin or sys.stdin)[:a.limit]
    if tools is None:
        import images
        tools = Tools()
        tmp = pathlib.Path(tempfile.mkdtemp())   # ブラウザの開き直し・書いた人の顔写真の覚え（state/）に、お客さまの記事の網址を残さない
        images.BROWSER_SKIP_FILE = tmp / "browser_skip.json"
        images.AUTHOR_FILE = tmp / "author_imgs.json"
    rows = run(items, tools)
    for ln in summary(rows):
        out(ln)
    if a.browser:
        rows_b = run(items, tools, use_browser=True)
        got = lambda rs: sum(1 for r in rs if r["category"].startswith("有图"))   # noqa: E731
        out(f"本物のブラウザ：なし {got(rows)} 件 → あり {got(rows_b)} 件に写真")
        for ln in summary(rows_b)[1:]:
            out("  （ブラウザあり）" + ln)
        for r, rb in zip(rows, rows_b):
            r["browser_category"] = rb["category"]
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        out(f"1 件ずつの行：{len(rows)} 行を書いた（リポジトリの外）")
    return rows


if __name__ == "__main__":
    main()
