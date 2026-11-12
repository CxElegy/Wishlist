"""写真の形ごとの「ほかの注目ニュース」の壁の空き（2026-11-03）。
ux_check の壁の空き ✓ は、写しが空だと写真が灰色の 8x8 で測るため、写真の形で決まる空きを見逃した（#725 で ✓ のあと 11/2 に test-a で空きを指摘された）。
ここは写真の形（横長・正方形・縦長・細長）を手元で作って返し、カードが 2〜4 枚の壁を 1400px で数える。本番にも写しにも触れない。
ブラウザが無い環境では飛ばす。

2026-11-12 速くした（全検査 634〜842 秒のうちこの 1 本が 506〜710 秒・負荷で Page.goto 30 秒切れ＝全員の push が詰まった）：
- 3.5MB の docs/home/index.html（img 4,300 枚）をそのまま開かず、試験のたびに cut() で壁のある節（.front）とページの外側だけを切り出す
  （カードの HTML・CSS は今の docs/home のもの＝render.py がカードの形を変えても試験に入る。壁の並べ方は今の render.FIT_JS）。
  docs/home が無い時だけ固定の予備 tests/fixtures/wall_shapes_page.html。
  内訳（直す前・1 通り）：goto 6〜14 秒（3.3MB の解析と写真 150〜280 枚の route）・HOLE_JS 1〜4 秒（大きい DOM）・固定待ち 1.2 秒・PIL 2 秒。× 43 通り。
- 写真の PNG は形ごとに 1 回だけ作る（前は 1 枚ごとに PIL・約 18 万回）。
- 1.2 秒の固定待ちの代わりに、壁の写真が読み終わり・形が 0.3 秒動かなくなるまで待つ（最長 3 秒）。
- 43 通りを 2 つのファイル（この試験と test_wall_shapes_b）に分けて、run_tests.py が並べて流す。
直す前の作りで測った通りごとの値は tests/fixtures/wall_shapes_baseline.json。CSS・FIT_JS・壁の節の HTML が測った時と同じ間は、合否が全部同じ・値の差 ±1 以内を確かめる。
直す前の作りでも値が揺れる通りがある（2026-11-13：1400px TW・右の列 +14 行の壁の中が 3・3・0、待ちを 4 秒にしても 3。今の作りは毎回 0）。
そういう通りは測った値を json の seen_<名前> に残し、その幅 ±1 で比べる（json の note）。
どれかが変わったら（docs/home を作り直すたびに変わる）、その比べ方だけ飛ばし、緑の時も「ℹ 」の 1 行で書く（閾値の点検はいつも流す）。
取り直し（直す前の作り＝大きいページ・写真ごとの PIL・1.2 秒待ちで測る。Linux のコンテナで。1 回 5 分以内に分ける）：
  python tests/test_wall_shapes.py --fixture            # docs/home から切り出し直す
  python tests/test_wall_shapes.py --baseline 0/8 … 7/8   # 8 つに分けて測り（4 つだと負荷で 5 分を超えた）、wall_shapes_baseline.json に足す"""
import hashlib
import io
import itertools
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
DOCS = ROOT / "docs"
FIX = ROOT / "tests" / "fixtures"
PAGE = FIX / "wall_shapes_page.html"
BASE = FIX / "wall_shapes_baseline.json"
SHAPES = {"W": (800, 450), "S": (600, 600), "T": (400, 600), "V": (300, 900)}   # 横長・正方形・縦長・細長
WIDTHS = (1400, 1100, 768)   # 壁が右の列の横に並ぶ幅と、1 列になる手前の幅
NARROW = 390   # 1 列になる幅（壁は右の列の下に回る）。空きでなく、並びの崩れ（横にはみ出す・カードの間が開く）を数える
MANY = 14      # 右の列の欲しい物・予定の行を増やす数（隠しても壁の 1.6 倍に収まらない場合の、壁を伸ばしきれない形を作る）
LEAD_ALONE = ["WWW", "WVV", "WTT", "WVVV"]   # 先頭を 2 列の大きい 1 枚に固定（生成ページの先頭が .tall になっても外れない）：その列に 1 枚だけで、隣が 3 枚以上
COMBOS = ["WW", "TW", "VV", "WWW", "TWW", "SSS", "VWT", "TTT", "WWWW", "TVWS"]
RUNS = [(s, w, 0, False) for s, w in itertools.product(COMBOS, WIDTHS)]
RUNS += [(s, w, MANY, False) for s, w in itertools.product(("WW", "TW", "WWW"), WIDTHS[:2])]   # 右の列が長い版面（欲しい物・予定が多い人）
RUNS += [(s, NARROW, 0, False) for s in ("WW", "WWWW", "TVWS")]
RUNS += [(s, w, 0, True) for s, w in itertools.product(LEAD_ALONE, WIDTHS[:1])]
N_RUNS = 43   # 通りの数（減ったら赤：test_runs_are_43）
SHARDS = 2    # 43 通りを分けるファイルの数（この試験＝0 番、test_wall_shapes_b＝1 番）
FIT_RE = re.compile(r"<script>(?:(?!</script>).)*const wall = \(\) =>.*?</script>", re.S)
STYLE_RE = re.compile(r"<style\b.*?</style>", re.S)

NARROW_JS = """()=>{const w=document.querySelector('.mgrid>.wall');const cs=[...(w?w.querySelectorAll(':scope>.wc'):[])].filter(c=>c.offsetParent);
let gap=0;cs.forEach((c,i)=>{if(i)gap=Math.max(gap,c.offsetTop-(cs[i-1].offsetTop+cs[i-1].offsetHeight))});
return {over:Math.max(0,document.documentElement.scrollWidth-innerWidth),gap:Math.round(gap)}}"""
# 画面の中の壁の写真が読み終わり、壁と右の列の形が 0.3 秒動かなくなるまで待つ（前は 1.2 秒の固定待ち）。
# 画面の下の写真は loading=lazy で読まれない（前の作りでも同じ）ので待たない
SETTLE_JS = """async(cap)=>{const t0=performance.now(),sl=ms=>new Promise(r=>setTimeout(r,ms));
const sig=()=>{const m=document.querySelector('.mgrid');if(!m)return '';return [...m.querySelectorAll('.wc,.fside,.wall,.wc img')].map(e=>{const r=e.getBoundingClientRect();return r.x+','+r.y+','+r.width+','+r.height}).join(';')+'|'+document.documentElement.scrollWidth};
const imgs=()=>[...document.querySelectorAll('.mgrid img')].every(i=>i.complete||i.getBoundingClientRect().top>=innerHeight);
let last=sig(),since=performance.now();
while(performance.now()-t0<cap){await sl(50);const s=sig();if(s!==last||!imgs()){last=s;since=performance.now()}else if(performance.now()-since>=300)break}
return Math.round(performance.now()-t0)}"""


def tag(run):
    shapes, vw, many, fixed = run
    return f"{vw}px {shapes}" + (f"・右の列 +{many} 行" if many else "") + ("・先頭は 2 列の 1 枚" if fixed else "")


def shard(i):
    return RUNS[i::SHARDS]


def _png(w, h):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (120, 140, 170)).save(b, "PNG")
    return b.getvalue()


def _many(tail, k):
    """右の列（</div><aside…）の予定・欲しい物の行を k 行ずつに増やす（同じ行を写す）"""
    if not k:
        return tail
    def grow(m):
        li = re.findall(r"<li\b.*?</li>", m.group(2), re.S)
        return m.group(1) + m.group(2) + "".join(li[i % len(li)] for i in range(k)) + m.group(3) if li else m.group(0)
    return re.sub(r'(<div class="(?:agenda|sbox swish)">.*?<ol>)(.*?)(</ol>)', grow, tail, flags=re.S)


def cut(full):
    """大きいページから、壁のある節（.front）とページの外側（頭・目次・終わりのスクリプト）だけを残す"""
    w = full.index('<div class="wall">')
    e = full.index("</section>", w) + len("</section>")
    return full[:e] + full[full.index("</div></main>", e):]


def page(fit_js=None, full=False):
    """測るページ。試験のたびに今の docs/home から cut() で壁の節と外側を切り出す（render.py がカードの HTML を変えても試験に入る）。
    docs/home が無い時だけ固定の予備 tests/fixtures/wall_shapes_page.html。壁の並べ方は今の render.FIT_JS。
    full=True は直す前の作り：今の docs/home をそのまま（取り直し用）。
    返り値：(ページの文字, 壁のカードの前までの位置 a, 壁の終わり z, 比べ方の鍵＝CSS・FIT_JS・壁の節の HTML の hash)"""
    import render
    live = DOCS / "home" / "index.html"
    if live.is_file():
        lv = live.read_text(encoding="utf-8")
        src = lv if full else cut(lv)
    elif full:
        raise FileNotFoundError(live)
    else:
        src = PAGE.read_text(encoding="utf-8")
    js = render.FIT_JS if fit_js is None else fit_js
    m = FIT_RE.search(src)
    src = src[:m.start()] + "<script>" + js + "</script>" + src[m.end():]
    a = src.index('<div class="wall">') + len('<div class="wall">')
    z = src.index("</div><aside", a)
    sec = src[a:src.index("</section>", z)]   # 壁のカードと右の列の HTML
    key = hashlib.sha256(("".join(STYLE_RE.findall(src[:src.index("</head>")])) + "\0" + js + "\0" + sec).encode("utf-8")).hexdigest()[:16]
    return src, a, z, key


def measure(runs, fit_js=None, log=None, full=False):
    """runs を 1 つのブラウザで順に流し、({tag: 値}, 鍵) を返す。ブラウザ・ページが無ければ unittest.SkipTest。
    full=True は直す前の作り（大きいページ・写真ごとに PIL・1.2 秒の固定待ち）：wall_shapes_baseline.json の取り直し用"""
    try:
        from playwright.sync_api import sync_playwright
        import ux_check
        from browser import launch
        src, a, z, key = page(fit_js, full)
        key = page(fit_js)[3]   # 鍵はいつも切り出したページのもの（比べる側と同じ）
    except Exception as ex:   # noqa: BLE001
        raise unittest.SkipTest(f"ブラウザ・ページが無い：{ex}")
    cards = re.split(r'(?=<article class="wc)', src[a:z])[1:]
    pngs = {k: _png(*v) for k, v in SHAPES.items()}
    out = {}
    with sync_playwright() as pw:
        try:
            b = launch(pw)
        except Exception as ex:   # noqa: BLE001
            raise unittest.SkipTest(f"ブラウザが開けない：{ex}")
        try:
            for run in runs:
                shapes, vw, many, fixed = run
                n = len(shapes)
                pg = b.new_page(viewport={"width": vw, "height": 900})
                use = cards[:n]
                if fixed:   # 先頭だけ 2 列の大きい 1 枚（.lead・.tall なし）、あとは 1 列の普通のカード
                    use = [re.sub(r'class="wc[^"]*"', 'class="wc lead"' if i == 0 else 'class="wc"', c, count=1) for i, c in enumerate(use)]
                html = src[:a] + "".join(use) + _many(src[z:], many)
                smap = {}
                for c, s in zip(cards[:n], shapes):
                    for u in re.findall(r'<img[^>]*src="([^"]+)"', c):
                        smap[u.replace("&amp;", "&")] = s

                def rt(r):   # 引数は 1 つだけ（2 つ以上だと Playwright が (route, request) で呼ぶ）。html・smap はこの通りのもの
                    u = r.request.url
                    if u.startswith("http://wl.test/"):
                        p = DOCS / u[len("http://wl.test/"):].split("?")[0]
                        if p == DOCS / "home" / "index.html":
                            return r.fulfill(status=200, body=html, content_type="text/html")
                        return r.fulfill(path=str(p)) if p.is_file() else r.fulfill(status=404, body="")
                    # 外へは取りに行かない（字体・CDN も含めて手元の絵を返す：前の作りと同じ）
                    s = smap.get(u, "S")
                    return r.fulfill(status=200, body=_png(*SHAPES[s]) if full else pngs[s], content_type="image/png")
                pg.route(re.compile(r".*"), rt)
                pg.goto("http://wl.test/home/index.html", wait_until="load", timeout=30000)
                waited = pg.wait_for_timeout(1200) if full else pg.evaluate(SETTLE_JS, 3000)
                if vw == NARROW:
                    o = pg.evaluate(NARROW_JS)
                    out[tag(run)] = {"over": o["over"], "gap": o["gap"]}
                else:
                    h = pg.evaluate(ux_check.HOLE_JS)
                    v = {"wallPct": h["wallPct"], "sidePct": h["sidePct"]}
                    for k in ("cmpGap", "cmpEmb", "cmpEg"):
                        if k in h:
                            v[k] = h[k]
                    out[tag(run)] = v
                if log:
                    log(tag(run), out[tag(run)], waited)
                pg.close()
        finally:
            b.close()
    return out, key


def judge(run, v):
    """1 通りの値の合否：赤の理由の文、緑なら None"""
    t = tag(run)
    if run[1] == NARROW:
        if v["over"] or v["gap"] > 40:
            return f"{t}: 横にはみ出し {v['over']}px・カードの間 {v['gap']}px"
        return None
    # 先頭固定の形は、2 列の 1 枚が伸びれば 0%（伸びないと 8%・閾値ぎりぎりで通ってしまう）なので 2% で切る
    if v["wallPct"] > (2 if run[3] else 8) or v["sidePct"] > 8:
        return f"{t}: 壁の中 {v['wallPct']}%・右の列との差 {v['sidePct']}%"
    if v.get("cmpGap") or v.get("cmpEmb"):   # 2026-11-12：小さい形のカードの写真の下の空き・壁のカードの小元素の札は 0
        return f"{t}: 小さい形の写真の下の空き {v['cmpGap']}・小元素 {v['cmpEmb']} " + "・".join(v.get("cmpEg", []))
    return None


def same_as_baseline(runs, got, key):
    """直す前の作りの値と比べる。CSS・FIT_JS・OS が測った時と違えば (None, 理由)（比べない）、同じなら (食い違いの一覧, None)"""
    base = json.loads(BASE.read_text(encoding="utf-8"))
    if base.get("key") != key:
        return None, f"CSS・FIT_JS・壁の節の HTML のどれかが測った時と違う（鍵 {key}・測った時 {base.get('key')}）"
    if sys.platform != base.get("platform", "linux"):
        return None, f"OS が違う（{sys.platform}・測ったのは {base.get('platform')}）"
    diff = []
    for run in runs:
        t = tag(run)
        b, g = base["runs"][t], got[t]
        if b["ok"] != (judge(run, g) is None):
            diff.append(f"{t}: 合否が違う（前 {b['ok']}・今 {judge(run, g)}）")
        for k in ("wallPct", "sidePct", "over", "gap"):
            seen = [b[k]] + b.get("seen_" + k, []) if k in b else []   # 直す前の作りでも値が揺れる通りは、測った値の幅 ±1
            if seen and not min(seen) - 1 <= g[k] <= max(seen) + 1:
                diff.append(f"{t}: {k} 前 {sorted(set(seen))}・今 {g[k]}")
    return diff, None


class WallShapesCount(unittest.TestCase):
    def test_runs_are_43(self):
        """通りの数は 43 のまま、2 つのファイルで 1 回ずつ（重ならず漏れず）"""
        self.assertEqual(len(RUNS), N_RUNS)
        self.assertEqual(len({tag(r) for r in RUNS}), N_RUNS)
        got = [tag(r) for i in range(SHARDS) for r in shard(i)]
        self.assertEqual(sorted(got), sorted(tag(r) for r in RUNS))
        base = json.loads(BASE.read_text(encoding="utf-8"))
        self.assertEqual(sorted(base["runs"]), sorted(tag(r) for r in RUNS), "直す前の値の通りと今の通りが同じ")
        b = (ROOT / "tests" / "test_wall_shapes_b.py").read_text(encoding="utf-8")
        self.assertIn("shard(1)", b)


def check_shard(tc, i):
    runs = shard(i)
    waits = []
    got, key = measure(runs, log=lambda t, v, ms: waits.append(ms))
    bad = [m for m in (judge(r, got[tag(r)]) for r in runs) if m]
    diff, why = same_as_baseline(runs, got, key)
    # run_tests.py は「ℹ 」で始まる行を緑の時も出す（比べ方が止まったことを黙らせない）
    print(f"\nℹ 壁の形 shard {i}：{len(runs)} 通り・待ち 平均 {sum(waits) // max(1, len(waits))}ms 最長 {max(waits, default=0)}ms・"
          + (f"直す前の値と比べた {len(runs)} 通り" if why is None else f"直す前の値と比べず：{why}"), flush=True)
    tc.assertEqual(bad, [], "写真の形で壁に空きが出る組み合わせ（W 横長・S 正方形・T 縦長・V 細長）")
    if diff is not None:
        tc.assertEqual(diff, [], "直す前の作り（tests/fixtures/wall_shapes_baseline.json）と合否・値（±1）が同じ")


class WallShapes(unittest.TestCase):
    def test_wall_has_no_hole_for_any_photo_shape(self):
        check_shard(self, 0)


def _baseline(part):
    """直す前の作りで RUNS の part（"0/4" なら 0, 4, 8…番目）を測って wall_shapes_baseline.json に足す"""
    k, n = map(int, part.split("/"))
    runs = RUNS[k::n]
    got, key = measure(runs, full=True, log=lambda t, v, ms: print(t, v, flush=True))
    base = json.loads(BASE.read_text(encoding="utf-8")) if BASE.is_file() else {}
    if base.get("key") != key:
        base = {"key": key, "platform": sys.platform, "runs": {}}
    base["made"] = "直す前の作り（大きい docs/home・写真ごとに PIL・1.2 秒待ち）で測った値。tests/test_wall_shapes.py --baseline"
    for r in runs:
        base["runs"][tag(r)] = {"ok": judge(r, got[tag(r)]) is None, **{x: got[tag(r)][x] for x in ("wallPct", "sidePct", "over", "gap") if x in got[tag(r)]}}
    base["runs"] = dict(sorted(base["runs"].items()))
    BASE.write_text(json.dumps(base, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(base['runs'])} / {N_RUNS} 通り")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--fixture"]:
        PAGE.write_text(cut((DOCS / "home" / "index.html").read_text(encoding="utf-8")), encoding="utf-8", newline="")
    elif sys.argv[1:2] == ["--baseline"]:
        _baseline(sys.argv[2])
    else:
        unittest.main()
