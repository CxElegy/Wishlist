"""エンブレム（版面の右上の小元素）の点検（HARNESS.md「エンブレムはサイトの売り」・EMBLEM_AUDIT.md）。ux_check.py から呼ぶ。

網页は開くたびに候補（.emb の data-alts）から 1 枚をランダムに出すので、画像そのものは候補を全部見る。
  E1 出ない      版面（section.sec、静かな版面「はじめに」は除く）に .emb が無い
  E2 読めない    候補の画像が開けない（2 回とも）・網页で naturalWidth ≤ 1
  E3 白い四角    logo・cutout の画像の外周の 9 割以上が不透明な白（地が抜けていない）
  E4 大きさ      表示の高さが同じ版面の中央値の 0.6 倍未満、または 1400：100〜215px・390：60〜140px の外（人物：cutout・badge、板ごとのロゴは除く。顔のアップは --k で縮めるので顔がそろう大きさに戻して測る）
  E5 はみ出し    画像の右端が画面の幅を越える
  E6 字に重なる  画像と題字の字そのもの（Range の行の矩形。.title は display:block で右に空きがある）が 1px² でも重なる
  E7 切れている  cutout が上の端で切れている：取るときと同じ規則（emblem.TOP_MAX：上の端の半分を超えて人物）、
                 上の端に当たっていて目が上から「目〜口」の EYE_TOP 倍より近い（額まで切れた。顔のモデル YuNet）、
                 上の 3px に絵が横幅の 20% 以上（頭のてっぺんが切れた：emblem.HEAD_EDGE）、
                 高さ 40px 未満の切れ端だけ（STRIP_MAX）
  E8 同じ画像    同じ版面に同じ src か、差分ハッシュの違い ≤ 4 ビット（emblem_fill.SAME_BITS）か、同じ動画（YouTube）の場面が 2 本以上
  E9 中身        元の画像のファイル名が別の作品の絵（大乱闘のフィギュア・amiibo など、BAD_SOURCE）
  E10 届かない   main の state/emblem_progress.json（後台が書く本番の状態）で state=failed（目標の本数に届かず止まっている。残り 1 枚だけは除く。残りの人が全員「画像のない人」＝候補が尽きた版面〔exhausted〕は ✗ にせず、下の「情報」に名前を出す）
  E11 何人も     cutout に顔が 2 つ以上、2 番目がいちばん大きい顔の face_id.CROWD_RATIO 以上（取るときの写真の規則と同じ）
  E15 主役がいない  キャラ・グループの版面で、名簿（emblem_who）の先頭 3 人（点数が高い・リンクの多い人）に小元素がいない人（emblem_fill.head_missing と同じ式。店長の items.yaml。BLEACH Mirrors High の黒崎一護：転送ページの別の人が一護の画像を先に取っていた）
  E19 公式があるのにアップのまま（情報：✗ にしない）  顔だけのアップ（fs > 0.5）が残る小元素の数と、そのうち公式サイトに同じ人の立ち絵（emblem.official_images）がある数を版面ごとに出す。公式が先の規則が gather・控え・入れ替えの全部の入口に効いているかの数え直し（0 に向かう）
  E18 短い辺が小さい  cutout（全身 body は除く）の画像の短い辺 < SMALL_SIDE（256px。emblem.BUST_MIN_SIDE と同じ数。ぼやけて見える）。数を出す。入れ替えで下限未満にはしない（emblem.better_cut）
  E17 人でない名前   キャラの版面で、名簿（emblem_who）の先頭 10 人に種族・役割・名無し（Wyverians・Hunter・Traveler・Wonderland Manekin。emblem.NOT_CHAR と同じ式）がいる、または小元素の主題にいる
  E16 顔だけのアップ  cutout（全身 body は除く）の顔の幅 > 画像の幅の CLOSE_W（45%）か、顔の下端から下が高さの SHOULDER_MIN（15%）未満（emblem_fill.closeup_of と同じしきい値。ここは YuNet で測れたものだけ：アニメ絵の検出は取るときの規則だけ）。小元素は胸像（BLEACH の黒崎一護）
  E13 顔を測っていない  cutout（全身の body は除く）に、顔の倍率 m も「顔なし」の印 nf もない（emblem_face.measure_item が回っていない。表示で顔の大きさがそろわない）
  E14 顔の大きさ  同じ版面の人物（全身 body は除く）の「顔の高さ × 倍率」の最大 ÷ 最小 > 1.25（emblem_face.fit が全版面に効いていない。店長もお客さまの版面も）
  E17 顔が測れない理由別の数（情報：✗ にしない）  顔なし（測ったが顔がない：網页の nf）の cutout を emblem_face.none_reason の札で数える。sheet＝向きを並べた図・small＝顔らしい箱はあるが小さい・noface＝箱がない（怪物・武器・物・覆面）。測り方の足りない（見つかる顔を見落とした）ものを増やさないための数え直しの材料
  E12 形の傷     cutout の左右の端（高さの 15% を超えてまっすぐ）か上の端（横幅の 25% を超えて）に直線の切り口、または形が凹みすぎ（面積 ÷ 凸包 < 0.45）
                 （scripts/cutshape.py：取るときの emblem.trim_flat・drop_broken と同じ式。まっすぐでよいのは下の端だけ）
顔のモデル（face_id、初回に約 39MB）が取れないときは E7 の顔・E11 を見ない（✗ の行に「顔のモデルなし」と出す）。
別人・遠景・ほぼ同じだが別の動画の場面は画素では決められないので、--emb full の写真の一覧を目で見る（EMBLEM_AUDIT.md）。
E4〜E6 は網页で測る：ふだんは出ている 1 枚、--emb full のときは候補を全部差し替えて測り、写真の一覧（OUT/emb/sheet-<だれ>-<幅>.png）を残す。
"""
import io
import json
import pathlib
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request

import yaml
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cutshape  # noqa: E402  （numpy・OpenCV・PIL だけ。emblem は import しない）
SMALL_SIDE = 256   # emblem.BUST_MIN_SIDE と同じ（emblem は import しない）
CLOSEUP_FS = 0.5   # emblem.CLOSEUP と同じ（試験で一致を見る）
import emblem_face  # noqa: E402  （E17 の理由の札。import の時点では pathlib だけ）
FIRST_BOARD = "はじめに"   # user_pages.FIRST_BOARD
SAME_BITS = 4              # emblem_fill.SAME_BITS
TOP_MAX, TOP_TOUCH = 0.5, 0.03   # emblem.TOP_MAX・TOP_TOUCH（取るときの規則）。emblem を import すると sources の opener が入り Wikimedia が 403 を返す（E2 を見誤った）
BAD_SOURCE = re.compile(r"trophy|ssbb|ssb4|ssbu|amiibo|figurine|statue|sticker|(?:^|[/_ ])(?:item|weapon|artifact|material|furnishing)_", re.I)   # emblem.BAD_SOURCE と同じ：別の作品（大乱闘のフィギュア・amiibo）・持ち物の絵
HEAD_ROWS, HEAD_EDGE = 3, 0.2   # emblem.HEAD_ROWS・HEAD_EDGE：上の 3px に絵が横幅の 20% 以上 = 頭のてっぺんが切れた（BLEACH Mirrors High）
EYE_TOP = 1.4             # 目の高さ < 目〜口の距離 × これ = 額まで切れた（本番の cutout：哈利波特 1.23、髪だけ切れたものは 1.5 以上）
STRIP_MAX = 40            # cutout の高さがこれ未満 = 人物が消えて切れ端だけ残った（漫威 Black Panther 73×23）
YT = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|i\.ytimg\.com/vi/)([\w-]{11})")
FACE_TARGET, FACE_TOL = 0.32, 0.11   # emblem_face.TARGET・TOL
SIZE = {1400: (100, 215), 390: (60, 140)}
NOSTILL = ".emb img{opacity:1!important;transform:none!important}.emb-in{opacity:1!important;transform:none!important;transition:none!important}.emb{animation:none!important}"

READ = r"""() => [...document.querySelectorAll('section.sec')].map((s, i) => {
  const t = s.querySelector('.band .title, .band h2, h2'), el = s.querySelector('.emb');
  let alts = []; try { alts = el ? JSON.parse(el.dataset.alts || '[]') : []; } catch (_) {}
  return {i, k: s.dataset.k || (t ? t.innerText.trim() : s.id), title: t ? t.innerText.trim() : '', has: !!el, alts}; })"""
# EMB_JS と同じ式で i 番目の版面の候補 j に差し替え、帯の右の空き（room）も同じ式で空け直す
SWAP = r"""async ([i, j]) => { const s = document.querySelectorAll('section.sec')[i], el = s.querySelector('.emb');
  const a = JSON.parse(el.dataset.alts || '[]')[j], inner = el.querySelector('.emb-in'), img = inner.querySelector('img');
  const n = img.cloneNode(); n.removeAttribute('loading'); n.src = a.src;
  const whole = a.shape === 'badge' && !a.crop && (a.plate || a.ar && (a.ar < 0.95 || a.ar > 1.6));
  n.className = a.shape + (a.body ? (a.body[1] > 1 ? ' body cut' : ' body') : a.m >= 1 ? ' fz' : '') + (whole ? ' whole' : '') + (a.shape === 'logo' && a.ar && a.ar < 0.5 ? ' wide' : '');
  n.style.cssText = a.body ? '--bl:' + (a.body[5] || (a.body[1] - a.body[0])) + ';--bf:' + a.body[1] + ';--bc:' + a.body[2] + ';--ba:' + a.body[3] : a.m ? (a.m < 1 ? '--k:' : '--m:') + a.m.toFixed(3) : a.fs ? '--k:' + Math.min(1, 0.32 / a.fs).toFixed(3) : '';
  if (a.shape === 'badge' && a.crop) { const c = document.createElement('span'); c.className = 'crop';
    c.style.cssText = '--cx:' + a.crop[0] + ';--cy:' + a.crop[1] + ';--cw:' + a.crop[2] + ';--ar:' + (a.ar || 1); c.appendChild(n); inner.replaceChildren(c); }
  else inner.replaceChildren(n);
  if (!n.complete) await new Promise(z => { n.onload = n.onerror = z; setTimeout(z, 15000); });
  const band = el.parentElement, b = band.getBoundingClientRect(), r = el.getBoundingClientRect();
  if (r.width) band.style.paddingRight = Math.ceil(b.right - r.left + 12) + 'px'; }"""
MEAS = r"""async (i) => { const q = () => { const s = document.querySelectorAll('section.sec')[i]; return [s, s && s.querySelector('.emb img')]; };
  let [s, img] = q();
  if (!img) { await new Promise(z => setTimeout(z, 1500)); [s, img] = q(); }   // 本人のページに替わる途中・描き直しの途中（null で点検ごと止まっていた）
  if (!img) return null;
  img.removeAttribute('loading'); img.scrollIntoView({block: 'center'});   // 画面の外の画像は loading=lazy で読まれていない（読めないと見誤った）
  const wait = () => img.complete ? 0 : new Promise(z => { img.onload = img.onerror = z; setTimeout(z, 15000); });
  await wait();
  if (!(img.naturalWidth > 1)) { const u = img.src; img.src = ''; img.src = u; await wait(); }   // 1 回だけ読み直す（時間切れのたまたま）
  const r = img.getBoundingClientRect(), t = s.querySelector('.band .title, .band h2, h2');
  let ov = 0;   // 字そのもの（行ごとの矩形）で測る。.title の箱は display:block で右に空きがあり、箱の端どうしの重なりを見誤った（2026-10-24 マンダロリアン 390）
  if (t) { const rg = document.createRange(); rg.selectNodeContents(t);
    for (const tr of rg.getClientRects()) ov += Math.max(0, Math.min(tr.right, r.right) - Math.max(tr.left, r.left)) * Math.max(0, Math.min(tr.bottom, r.bottom) - Math.max(tr.top, r.top)); }
  return {src: img.getAttribute('src'), ok: img.naturalWidth > 1, h: Math.round(r.height), off: Math.round(r.right - innerWidth), ov: Math.round(ov)}; }"""

_files, _why = {}, {}   # 開けなかった理由（E2 の行に出す）


def _get(url):
    """画像を開く（1 回だけ取り直す）。同じ網址は 1 回の点検で 1 回だけ。"""
    if url not in _files:
        img = None
        for _ in range(2):
            try:
                data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "wishlist-ux-check (https://cxelegy.github.io/Wishlist/)"}), timeout=20).read()
                if b"<svg" in data[:4096]:   # 記号（Twemoji）・SVG のロゴ：開けて <svg があればよい（画素の点検はしない）
                    img = "svg"
                else:
                    img = Image.open(io.BytesIO(data))
                    img.load()
                break
            except Exception as e:  # noqa: BLE001
                img, _why[url] = None, str(e)[:60]
                time.sleep(3)   # Commons の 429 など：少し置いてから
        _files[url] = img
    return _files[url]


def dhash(img):
    im = img.convert("RGBA")   # emblem_fill._hash と同じ：透明は灰の上に置いて測る（黒にすると細い立ち絵どうしが同じに見える）
    g = Image.alpha_composite(Image.new("RGBA", im.size, (128, 128, 128, 255)), im).convert("L").resize((9, 8))
    px = list(g.getdata())
    return int("".join("1" if px[r * 9 + c] > px[r * 9 + c + 1] else "0" for r in range(8) for c in range(8)), 2)


def white_box(img):
    """外周の 9 割以上が不透明な白（ロゴ・切り抜きの地が抜けていない）。"""
    im = img.convert("RGBA")
    w, h = im.size
    px = im.load()
    edge = [px[x, y] for x in range(w) for y in (0, h - 1)] + [px[x, y] for y in range(h) for x in (0, w - 1)]
    white = sum(1 for r, g, b, a in edge if a > 200 and min(r, g, b) > 240 and max(r, g, b) - min(r, g, b) < 15)
    return white / max(1, len(edge)) >= 0.9


def _faces(im):
    """白い地に置いた cutout の顔（YuNet の行：x, y, w, h, 右目, 左目, 鼻, 口の右, 口の左, 点数）。上に余白を足す（額が切れていても見つける）。
    顔のモデルがなければ None。"""
    import face_id
    eng = face_id.engine()
    if eng is None:
        return None
    import cv2
    import numpy as np
    s = max(1.0, 400 / max(im.size))
    w, h = int(im.width * s), int(im.height * s)
    pad = h // 2
    bg = Image.new("RGBA", (w, h + pad), "white")
    bg.alpha_composite(im.resize((w, h)), (0, pad))
    bgr = cv2.cvtColor(np.array(bg.convert("RGB")), cv2.COLOR_RGB2BGR)
    eng[0].setInputSize((bgr.shape[1], bgr.shape[0]))
    f = eng[0].detect(bgr)[1]
    return [(r, pad, s) for r in sorted(f, key=lambda r: -r[2] * r[3])] if f is not None else []


def cut_edge(img, faces=None, whole=False):
    """切り抜き（透明の地）が上の端で切れている → 理由、なければ ""。左右・下は見ない（胸像の切り口・腕）。
    上の端の 6 割で決めていたときは、額まで切れた哈利波特（上の端 9%）を拾えず、髪の上だけ切れた写真と分けられなかった。"""
    im = img.convert("RGBA")
    if im.getextrema()[3][0] > 200:   # 透明な所がない = 切り抜きではない
        return ""
    if im.height < STRIP_MAX:
        return f"切れ端 {im.width}×{im.height}"
    a = im.getchannel("A").load()
    if whole:   # 公式の全身の絵（body の足の裏が画像の中）：上の端は絵そのもの（ポチタの持ち手）。emblem_fill.broken_image と同じ
        return ""
    top = sum(1 for x in range(im.width) if a[x, 0] > 128) / im.width
    if top > TOP_MAX:
        return f"上の端 {top:.0%}"
    head = sum(1 for x in range(im.width) if any(a[x, y] > 128 for y in range(min(HEAD_ROWS, im.height)))) / im.width
    if head >= HEAD_EDGE:
        return f"頭のてっぺんが切れた（上 {HEAD_ROWS}px に {head:.0%}）"
    if top > TOP_TOUCH and faces:
        r, pad, s = faces[0]
        eye, mouth = (r[5] + r[7]) / 2 - pad, (r[11] + r[13]) / 2 - pad
        if mouth > eye and eye < (mouth - eye) * EYE_TOP:
            return f"額で切れた（目 {eye / s:.0f}px）"
    return ""


CLOSE_W, SHOULDER_MIN = 0.45, 0.15   # emblem_fill.CLOSE_W・SHOULDER_MIN


def closeup(img, faces):
    """E16：顔だけのアップ（顔の幅 > CLOSE_W か、顔の下 < SHOULDER_MIN）→ 理由、なければ ""。faces は _faces の行（r, pad, s）。"""
    if not faces:
        return ""
    r, pad, s = faces[0]
    w, h = img.size
    fw, below = r[2] / s / w, 1 - ((r[1] - pad) / s + r[3] / s) / h
    if fw > CLOSE_W:
        return f"顔の幅 {fw:.0%}"
    return f"肩・胸が写っていない（顔の下 {max(below, 0):.0%}）" if below < SHOULDER_MIN else ""


def crowd(faces):
    """顔が 2 つ以上で、2 番目がいちばん大きい顔の CROWD_RATIO 以上（face_id.photo_problem の「何人も写っている」）。"""
    import face_id
    return len(faces or []) > 1 and faces[1][0][2] * faces[1][0][3] >= face_id.CROWD_RATIO * faces[0][0][2] * faces[0][0][3]


def sources():
    """店長の版面の小元素の元の網址（items.yaml の emblem の image → (source, page)）。"""
    d = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))
    return {x["image"]: (str(x.get("source") or ""), str(x.get("page") or "")) for it in d.get("items", []) for x in (it.get("emblem") or [])
            if isinstance(x, dict) and x.get("image")}


def not_char():
    """emblem.NOT_CHAR と同じ式（emblem は import しない：scripts/emblem.py の代入をそのまま読む）。"""
    import ast
    src = (ROOT / "scripts" / "emblem.py").read_text(encoding="utf-8")
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.Assign) and n.targets[0].id == "NOT_CHAR")
    rx = eval(compile(ast.Expression(node.value), "NOT_CHAR", "eval"), {"re": re})
    return lambda s: bool(rx.search(str(s or "")))


def not_people(top=10):
    """E17：名簿の先頭 top 人か今の小元素に、人でない名前がいる版面 → {版面: [名前]}。"""
    bad, out = not_char(), {}
    for it in yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")).get("items", []):
        if it.get("emblem_kind") != "character":
            continue
        names = list((it.get("emblem_who") or [])[:top]) + [x.get("subject") for x in it.get("emblem") or [] if isinstance(x, dict)]
        hit = [n for n in dict.fromkeys(names) if bad(n)]
        if hit:
            out[it["name"]] = hit
    return out


def head_missing():
    """E15：名簿の先頭 3 人に小元素がいない → {版面: [名前]}（emblem_fill.head_missing と同じ式。emblem は import しない）。"""
    import unicodedata
    key = lambda s: re.sub(r"[^a-z0-9]", "", "".join(c for c in unicodedata.normalize("NFKD", str(s).lower()) if not unicodedata.combining(c)).replace("ou", "o").replace("uu", "u"))
    bare = lambda s: re.sub(r"\s*[(（].*?[)）]", "", re.sub(r" \d+$", "", str(s or "")))
    out = {}
    for it in yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")).get("items", []):
        if it.get("emblem_kind") not in ("character", "group"):
            continue
        have = set()
        for x in it.get("emblem") or []:
            if isinstance(x, dict):
                s = re.sub(r" \d+$", "", str(x.get("subject") or ""))
                m = re.fullmatch(r".+（(.+)）", s)
                have |= {key(s), key(bare(s))} | ({key(m.group(1))} if m else set())
        bad = not_char()
        miss = [w for w in [w for w in (it.get("emblem_who") or []) if not bad(w)][:3] if key(w) not in have and key(bare(w)) not in have]
        if miss:
            out[it["name"]] = miss
    return out


def closeup_left(official=None, items=None):
    """E19（情報）：顔だけのアップ（fs > emblem.CLOSEUP）のまま残っている小元素の数と、そのうち公式サイトに同じ人の立ち絵（emblem.official_images）がある数
    → {版面: (アップの数, 公式のある数, [公式のある人])}。「公式が先」の規則が全部の入口（gather・控え・入れ替え）に効いているかを数える。
    official(item, subject) → 網址のリスト（試験では差し替える。既定は emblem.official_images）。"""
    if official is None:
        import emblem
        official = lambda it, s: emblem.official_images(emblem.official_site(it), re.split(r"[\s(),]+", re.sub(r"\s*[(（].*?[)）]", "", s)))
    out = {}
    for it in items if items is not None else yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")).get("items", []):
        if it.get("emblem_kind") not in ("character", "group"):
            continue
        cl = [x["subject"] for x in it.get("emblem") or [] if isinstance(x, dict) and (x.get("fs") or 0) > CLOSEUP_FS and not x.get("body")]
        if cl:
            ok = [s for s in cl if official(it, s)]
            out[it["name"]] = (len(cl), len(ok), ok)
    return out


PROGRESS = "https://raw.githubusercontent.com/CxElegy/Wishlist/main/state/emblem_progress.json"


def stuck():
    """目標に届かず止まっている版面（emblem_progress.json の state=failed）。後台が main に書く本番の状態を読む
    （手元のチェックアウトは古いことがある）。取れなければ手元のもの。"""
    try:
        d = json.loads(urllib.request.urlopen(PROGRESS, timeout=20).read())
    except Exception:  # noqa: BLE001
        p = ROOT / "state" / "emblem_progress.json"
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    d = d.get("items", {})
    # 残り 1 枚だけ届かない（Astrae Oratio 29/30・绝区零 60/61）は名簿の最後の 1 人に使える画像がないだけなので ✗ にしない
    return {k: f"{v.get('have')}/{v.get('target')}" for k, v in d.items() if v.get("state") == "failed" and not v.get("exhausted") and (v.get("target") or 0) - (v.get("have") or 0) > 1}


CLOSE_STATE = "https://raw.githubusercontent.com/CxElegy/Wishlist/main/state/emblem_closeup.json"


def closeup_stage():
    """E16 の情報：顔だけのアップを段階的に入れ替え中（胸像待ち）の人数と、胸像が取れないまま 3 回を超えた人（名簿の上位 12 人は外さず探し続ける）
    → {版面: (待ちの人数, [3 回以上の人])}。後台が main に書く state/emblem_closeup.json（取れなければ手元）。"""
    try:
        d = json.loads(urllib.request.urlopen(CLOSE_STATE, timeout=20).read())
    except Exception:  # noqa: BLE001
        p = ROOT / "state" / "emblem_closeup.json"
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {k: (len(v), [s for s, x in v.items() if int((x or {}).get("n") or 0) >= 3]) for k, v in d.items() if v}


def exhausted():
    """候補が尽きた版面（残りの人が全員「画像のない人」：emblem_fill の exhausted）→ {名前: have/target}。"""
    try:
        d = json.loads(urllib.request.urlopen(PROGRESS, timeout=20).read()).get("items", {})
    except Exception:  # noqa: BLE001
        return {}
    return {k: f"{v.get('have')}/{v.get('target')}" for k, v in d.items() if v.get("state") == "failed" and v.get("exhausted")}


def _sheet(shots, path):
    if not shots:
        return
    ims = [Image.open(p).convert("RGB") for p in shots]
    cw, ch = max(i.width for i in ims), max(i.height for i in ims)
    cols = 10
    sheet = Image.new("RGB", (cw * cols, ch * ((len(ims) + cols - 1) // cols)), "white")
    for n, im in enumerate(ims):
        sheet.paste(im, ((n % cols) * cw, (n // cols) * ch))
    sheet.save(path)


def check(pg, who, width, out, full=False, guest=False):
    """1 枚の網页（読み込み済み）のエンブレムを点検して、✗ の言葉の一覧を返す。"""
    pg.add_style_tag(content=NOSTILL)
    secs = [s for s in pg.evaluate(READ) if s["title"] != FIRST_BOARD and s["k"] != FIRST_BOARD]
    found = {f"E{n}": [] for n in range(1, 19)}
    nomodel = False
    nf_why = {}   # E17：顔が測れない理由の札 → [版面 名前]
    src_of = sources()
    shots, embdir = [], out / "emb"
    if full:
        embdir.mkdir(parents=True, exist_ok=True)
    for s in secs:
        if not s["has"]:
            found["E1"].append(s["k"])
            continue
        hashes, videos = {}, {}
        for j, a in enumerate(s["alts"]):
            url = urllib.parse.urljoin(pg.url, a["src"])
            name = a["src"].rsplit("/", 1)[-1]
            img = _get(url)
            if img is None:
                found["E2"].append(f"{s['k']} {name}（{_why.get(url, '')}）")
                continue
            if img == "svg":
                continue
            if a["shape"] in ("logo", "cutout") and white_box(img):
                found["E3"].append(f"{s['k']} {name}")
            if a["shape"] == "cutout":
                if not (a.get("body") or a.get("m") or a.get("nf")):   # 網址の小元素（お客さまの版面）も。前は除いていて、135 枚の未測定を見逃した
                    found["E13"].append(f"{s['k']} {name}")   # 顔を測っていない（emblem_face.measure_item・library_emblem.measure_faces が回っていない）= 表示で顔の大きさがそろわない
                if a.get("nf") and not a.get("body"):
                    nf_why.setdefault(emblem_face.none_reason(img), []).append(f"{s['k']} {name}")
                faces = _faces(img.convert("RGBA"))
                nomodel |= faces is None
                b = a.get("body")
                why = cut_edge(img, faces, whole=bool(b) and len(b) > 1 and b[1] <= 1)
                if why:
                    found["E7"].append(f"{s['k']} {name} {why}")
                flaw = cutshape.flat_flaw(img)
                if flaw:
                    found["E12"].append(f"{s['k']} {name}")
                if not a.get("body") and min(img.size) < SMALL_SIDE:   # E18：短い辺が小さい（ぼやけて見える）
                    found["E18"].append(f"{s['k']} {name} {img.size[0]}×{img.size[1]}")
                if crowd(faces):
                    found["E11"].append(f"{s['k']} {name} 顔 {len(faces)}")
                if not a.get("body") and (why := closeup(img, faces)):
                    found["E16"].append(f"{s['k']} {name} {why}")
            h = dhash(img)
            same = next((n for n, x in hashes.items() if bin(h ^ x).count("1") <= SAME_BITS), None)
            src, page = src_of.get(a["src"], ("", ""))
            vid = YT.search(page) or YT.search(src)
            if not same and vid:
                same = videos.get(vid.group(1))
                videos.setdefault(vid.group(1), name)
            if same:
                found["E8"].append(f"{s['k']} {name}＝{same}")
            hashes[name] = h
            if BAD_SOURCE.search(urllib.parse.unquote(src.split("?")[0].split("//", 1)[-1].split("/", 1)[-1])):
                found["E9"].append(f"{s['k']} {name}（{src.rsplit('/', 1)[-1][:40]}）")
        shares = [a["fs"] * a["m"] for a in s["alts"] if a.get("m") and a.get("fs") and a["shape"] == "cutout" and not a.get("body")]   # 顔の高さ ÷ 枠の高さ（版面の中の全候補）
        shares = [v for v in shares if abs(v - FACE_TARGET) <= FACE_TARGET * FACE_TOL]   # そろえきれず札のついたもの（big/small）は別の段（BACKLOG：別の写真に替える）
        if shares and max(shares) / min(shares) > 1.25:
            found["E14"].append(f"{s['k']} 顔の大きさ {max(shares) / min(shares):.2f} 倍")
        hs = []
        for j in range(len(s["alts"]) if full else 1):
            if full:
                pg.evaluate(SWAP, [s["i"], j])
            m = pg.evaluate(MEAS, s["i"])
            if m is None:
                found["E2"].append(f"{s['k']}（画像の要素が消えた）")
                continue
            name = m["src"].rsplit("/", 1)[-1]
            if not m["ok"]:
                found["E2"].append(f"{s['k']} {name}（網页）")
                continue
            a = next((x for x in s["alts"] if x["src"] == m["src"]), {})
            fs = a.get("fs") or 0
            mm = a.get("m") if not a.get("body") else None   # 顔をそろえる倍率（emblem_face.fit）：表示の高さを倍率で割って、そろえる前の大きさ（枠の高さ）に戻して測る
            # 顔のアップは網页が顔の大きさをそろえて縮める（--k = 0.32/fs）ので、顔がそろう大きさに戻して測る
            hs.append((m["h"] / mm if mm else m["h"] * fs / 0.32 if fs > 0.32 and not a.get("body") else m["h"], name, "" if a.get("plate") else a.get("shape", "")))   # 板ごとのタイトルロゴは人物の物差しで測らない
            if m["off"] > 0:
                found["E5"].append(f"{s['k']} {name} +{m['off']}px")
            if m["ov"] > 0:
                found["E6"].append(f"{s['k']} {name}")
            if full:
                el = pg.query_selector_all("section.sec")[s["i"]].query_selector(".emb")
                try:
                    el.scroll_into_view_if_needed()
                    p = embdir / f"{who}-{width}-{s['i']:02d}-{j:02d}.png"
                    el.screenshot(path=str(p))
                    shots.append(p)
                except Exception:  # noqa: BLE001
                    pass
        lo, hi = SIZE.get(width, SIZE[1400])
        med = statistics.median(h for h, _, _ in hs) if hs else 0
        for h, name, shape in hs:
            if shape not in ("cutout", "badge"):
                continue
            if h < med * 0.6 or not lo <= h <= hi:
                found["E4"].append(f"{s['k']} {name} {h}px（中央値 {med:.0f}）")
    if guest:   # 店長の版面（ログインなし）だけ：止まっている版面は後台の状態から
        found["E10"] = [f"{k} {v}" for k, v in stuck().items()]
    if guest:
        found["E15"] = [f"{k} {'・'.join(v)}" for k, v in head_missing().items()]
    if guest and (cs := closeup_stage()):
        print("  情報：胸像待ち（顔だけのアップの入れ替え中）" + "・".join(f"{k} {n} 人（3 回を超えた {len(o)} 人：{'、'.join(o[:5])}）" for k, (n, o) in cs.items()))
    if guest:
        found["E17"] = [f"{k} {'・'.join(v)}" for k, v in not_people().items()]
    if guest:
        try:
            cl = closeup_left()
            print(f"  情報 E19 顔だけのアップが残る {sum(v[0] for v in cl.values())} 枚（{len(cl)} 版面）のうち、公式サイトに同じ人の立ち絵がある {sum(v[1] for v in cl.values())} 枚（{len([k for k, v in cl.items() if v[1]])} 版面）"
                  + "".join(f"\n    {k}：{v[0]} 枚・公式あり {v[1]}（{'・'.join(v[2][:4])}）" for k, v in cl.items()))
        except Exception as e:  # noqa: BLE001
            print(f"  情報 E19 数えられなかった：{e}")
    if guest and (ex := exhausted()):
        print(f"  情報：候補が尽きた版面（✗ にしない・1 日おきに見直す）{ex}")
    if nf_why:
        print(f"  情報 E17 顔が測れない {sum(map(len, nf_why.values()))} 枚の理由：" + "・".join(f"{k} {len(v)}（{emblem_face.NONE_REASONS[k]}）" for k, v in sorted(nf_why.items())))
    if full:
        _sheet(shots, embdir / f"sheet-{who}-{width}.png")
    label = {"E1": "エンブレムなし", "E2": "読めない", "E3": "白い四角", "E4": "大きさ", "E5": "はみ出し", "E6": "題字に重なる",
             "E7": "切れている", "E8": "同じ画像", "E9": "別の作品の絵", "E10": "目標に届かない", "E11": "何人も写っている", "E13": "顔を測っていない", "E14": "顔の大きさがばらつく", "E15": "主役がいない", "E16": "顔だけのアップ", "E17": "人でない名前", "E18": "短い辺が256px未満", "E12": "形の傷（直線の切り口・凹み）"}
    bad = [f"{e} {label[e]} {len(v)}（{'・'.join(v[:4])}{'…' if len(v) > 4 else ''}）" for e, v in found.items() if v]
    return bad + (["E7・E11 顔のモデルなし（額の切れ・何人もは見ていない）"] if nomodel else [])
