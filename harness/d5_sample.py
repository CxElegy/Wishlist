"""D5「見せ場を 1 つ・2 色の配色」の見本を作る（テストグラウンドだけ、本番の render.py は変えない）。

    python scripts/digest.py render      # 今のページ docs/home/index.html を作る
    python harness/d5_sample.py          # docs/testground/d5-now.html（今）と d5-new.html（案）

d5-now.html = 今のページの写し（画像などは <base href="../home/"> で本番の場所から読む・自動更新は止める）。
d5-new.html = 同じものに上書きの CSS（令牌だけ）を足したもの：
  ・P5 の演出（硬い影・傾き・平行四辺形の札・倍の影）はトップの頭条（.poster）1 枚だけ
  ・ほか（照片墙・棚・気になるかも？・版面のカード・目次）は傾けず、影を消す
  ・版面の配色は「作品の色 --acc ＋その濃い色 --deep ＋紙色 --card」の 3 つだけ（AA を Python で計算して確かめる）
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "docs/home/index.html"
OUT = ROOT / "docs/testground"
PAPER = "#FBF8F1"   # render.py の --card
INK = "#1A1C22"     # render.py の --ink


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hexc(c):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v))) for v in c)


def lum(h):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, t):
    """a を b へ t（0〜1）だけ寄せる"""
    return hexc(tuple(x + (y - x) * t for x, y in zip(rgb(a), rgb(b))))


def toward(color, target, against, need):
    """color を target へ少しずつ寄せ、against との比が need 以上になった最初の色"""
    for i in range(0, 101):
        c = mix(color, target, i / 100)
        if contrast(c, against) >= need:
            return c
    return target


def two_tone(style):
    """版面の theme を「作品の色・その濃い色・紙色」の 3 つに置き換えた style"""
    v = dict(re.findall(r"--([a-z]+):(#[0-9A-Fa-f]{6})", style))
    acc, bg = v.get("acc"), v.get("bg")
    if not acc or not bg:
        return style, None
    deep = toward(acc, "#000000", PAPER, 15)          # 作品の色の濃い色（紙色の上の本文 15:1 以上、ほぼ黒に作品の色がにじむ程度）
    dark = lum(bg) < 0.2                               # もとが暗い版面は暗いまま（作品の気分を残す）
    if dark:
        b, f = deep, PAPER
    else:
        b, f = PAPER, deep
    a = toward(acc, PAPER if dark else "#000000", b, 4.5)   # 作品の色：地の上で文字にも使えるよう 4.5:1
    alt_b, alt_f = f, b                                    # 反転の箱（.fact など）は 2 色を入れ替えるだけ
    alt_a = toward(acc, PAPER if not dark else "#000000", alt_b, 4.5)
    new = (f"--bg:{b};--fg:{f};--acc:{a};--abg:{alt_b};--afg:{alt_f};--aacc:{alt_a};--aac:{alt_a};"
           f"--deep:{deep};--line:color-mix(in srgb,{f} 22%,{b})")
    checks = {"本文": contrast(f, b), "作品の色": contrast(a, b), "反転": contrast(alt_f, alt_b),
              "反転の作品の色": contrast(alt_a, alt_b)}
    return new, checks


# 上書きの CSS：使うのは :root の令牌と、版面の --bg --fg --acc だけ（16 進は書かない）
CSS = """
<style id="d5">
/* D5 見本：見せ場は頭条 1 枚。ほかは静かに */
:root{--tilt:0deg;--skew:0deg;--shadow:none;--shadow-l:none;--quiet:1px solid color-mix(in srgb,var(--ink) 22%,transparent)}
/* ── 見せ場：頭条のポスターにだけ P5 の演出を集める ── */
.poster{--tilt:-2.2deg;--skew:-10deg;--shadow:6px 6px 0 var(--ink);
  box-shadow:10px 10px 0 var(--rose),20px 20px 0 var(--ink);transform:rotate(-.6deg)}
.poster .phead .lab{transform:skewX(var(--skew));box-shadow:4px 4px 0 var(--rose)}
.poster .top h2{transform:rotate(var(--tilt))}
.poster .tag,.poster .tg{transform:skewX(var(--skew));box-shadow:3px 3px 0 var(--ink)}
/* ── 静かに：照片墙・棚・気になるかも？・右列・目次 ── */
.wc,.wc:hover,.pk .pkt,.pk:nth-child(even) .pkt,.pk.big .pkt,.pkgrid.row .pk .pic,.pkgrid.row .pk:nth-child(even) .pic,
.pkhead .flag,.card .pic,.card:nth-child(even) .pic{transform:none}
.wc,.wc:hover,.wc .tg,.pk .pic,.pkgrid.row .pk .pic,.pkhead .flag,.card .pic,.shelfbox>summary,.sbox,.agenda,
.shuffle:hover,.shuffle.back{box-shadow:none}
.wc,.sbox,.agenda,.shelfbox>summary,.pk .pic{border:var(--quiet)}
.wc:hover{outline:2px solid var(--ink);outline-offset:-2px}
.nav .pill.on::before{box-shadow:none}
.nav .nsec .tg,.nav .nslot.cur .nsec .tg{transform:none;box-shadow:none}
.wl-auth .shop,.wl-auth .rl{transform:none;box-shadow:none}
/* ── 版面：作品の 2 色＋紙色。硬い影をやめ、細い線で区切る ── */
.sec{box-shadow:none;border:1px solid var(--line)}
.sec .band{box-shadow:none}
.fact{box-shadow:none;border-left:6px solid var(--acc)}
.emb{transform:none}
/* 見出し・目次・右列の残りの演出も外す（html を前に付けて、後ろの <style> やスマホ用より強く） */
html .mast h1,html .mastwish,html .mastwish:hover,html .nav .mtabs a.on,html .nav .nsubs a.on,html .smore,html .tape,
html .xevent,html .shot .bar,html .picks,html .sec,html .fact,html .wc:hover,html .wc .tg{box-shadow:none}
html .picks{border:1px solid var(--line,var(--ink))}
html .fside .agenda,html .nav .wm,html .nav .nbody .pill .nm,html .nav .nbody .pill.on .nm,
html .nav .nbody .pill:nth-of-type(n) .nm,html .wcard:hover .wimg img{transform:none}
</style>
"""


def base(html, title):
    html = re.sub(r'<meta name="wl-ver"[^>]*>', "", html)            # 見本は自動更新しない
    html = html.replace("<head>", '<head><base href="../home/"><meta name="robots" content="noindex">', 1)
    html = re.sub(r"<title>[^<]*</title>", f"<title>{title}</title>", html, count=1)
    return html


def main():
    src = SRC.read_text(encoding="utf-8")
    assert src.count("<head>") == 1
    now = base(src, "D5 見本・今")
    (OUT / "d5-now.html").write_text(now, encoding="utf-8")

    worst = {}

    def repl(m):
        style, checks = two_tone(m.group(2))
        for k, val in (checks or {}).items():
            worst[k] = min(worst.get(k, 99), val)
        return m.group(1) + style + '"'

    new = re.sub(r'(<section [^>]*class="sec [^"]*" style=")([^"]*)"', repl, now)
    assert new.count("</head>") == 1
    new = new.replace("</head>", CSS + "</head>", 1).replace("<title>D5 見本・今</title>", "<title>D5 見本・案</title>")
    (OUT / "d5-new.html").write_text(new, encoding="utf-8")
    print("いちばん低いコントラスト：" + "、".join(f"{k} {v:.1f}" for k, v in worst.items()))
    assert all(v >= 4.5 for v in worst.values()), worst


if __name__ == "__main__":
    main()
