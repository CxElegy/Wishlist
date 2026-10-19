"""配图的高清化・本站保存：用 OpenCV 的规则处理（不用 AI、不叫外部服务）。

原图看得清就不动（不花资源）。只有这四种情况把报道的配图存一份到 docs/pics/（网页优先用这份，打不开再用原图）：
  1. 看不清：网页上要放大 ENLARGE 倍以上才铺满（大位置 BIG_PX、卡片 CARD_PX，按 2 倍屏算），
     而且放到显示大小后量出来是糊的（blur > BLUR）→ 去噪・放大・锐化。
     两个条件都要：图小但锐利（文字横幅）放大一点也看得清；糊但够大的（背景虚化的照片）是拍法，不是看不清。
  2. Bing 的小缩略图：去掉 w 只给 100×100（看不清），带 w 又补一圈白边 → 取带 w 的，用 OpenCV 切掉白边
  3. 防盗链：浏览器打不开（新浪 sinaimg 这类，不带 Referer 就 403）→ 带原文网页作 Referer 下载，存一份
  4. 期限付きの網址（Yahoo ニュースの ?exp=10800 など，images.expiring）：数时间后变成 404 + 1×1 的空白 → 出刊时（还有效）存一份
已经打不开・变成空白的图记 dead：digest.retry_images 去原文重新找图（原文给的是新的有效地址，再由这里存一份）。

糊不糊（blur）：无参考的模糊度（Crété-Roffet 2007，re-blur 法）。把图缩放到显示大小（浏览器那样双线性），
  自己再用 1×9 的均值模糊一次，看相邻像素的差少了多少：本来就糊的图再模糊也几乎不变（接近 1），清楚的图会掉很多（接近 0）。
  横竖各算一次取大的。2026-10-17 用当时网页上 343 张配图校准：清楚的 0.12〜0.40，用户说看不清的 GTA6 那张 0.46。

放大的步骤（enhance）：
  ① 去 JPEG 噪点  cv2.fastNlMeansDenoisingColored（h=DENOISE，放大前做，不然 8×8 的块也一起放大）
  ② 放大          cv2.resize INTER_LANCZOS4（Lanczos 窗口 8×8，比双三次更清楚、不发虚）
  ③ 锐化          只在亮度（Lab 的 L）上做 USM：L + AMOUNT ×（L − 高斯模糊 L），
                  变化小于 THRESHOLD 的平坦处不加（不把噪点也放大），颜色通道不动（不出彩边）
存成 webp（质量 QUALITY）。哪张图存成了哪个文件记在 state/hdimg.json（render 读它换地址）；
不在最近 WINDOW_DAYS 天报道里的图连文件一起删掉（Pages 有 1GB 上限）。

    python scripts/hdimg.py            # 处理最近几期（出刊时 digest.publish 会自动调用）
"""

import concurrent.futures
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import images  # noqa: E402
import sitedir  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PICS_DIR = sitedir.SITE_DIR / "pics"   # 本站保存の写真。公開ページの場所は PICS_DIR.parent
STATE_FILE = ROOT / "state" / "hdimg.json"
REPORTS_DIR = ROOT / "reports"

BIG_PX = 1280       # 大位置的目标长边：头条约 600 CSS px 宽 × 2 倍屏（平板・手机）
CARD_PX = 720       # 普通卡片的目标长边：约 300 CSS px × 2 倍屏
ENLARGE = 1.6       # 1. 网页上要放大这么多倍以上才算「可能看不清」（浏览器放大 1.5 倍以内看不出来）
BLUR = 0.42         # 1. 放到显示大小后的模糊度超过这个才处理（0 = 很清楚，1 = 全糊）
MAX_SCALE = 3.0     # 最多放大几倍（再大也只是更糊）
BIG_PER_WORK = 2    # 每个关注项最新几条有图的报道算「大位置」（头条＋トップのポスター候选）
DENOISE = 3         # ① 去噪强度（OpenCV 的 h / hColor，3 = 轻轻去掉 JPEG 块，不抹掉细节）
AMOUNT = 0.7        # ③ 锐化强度
THRESHOLD = 2.0     # ③ 亮度变化小于这个（0〜255）的地方不锐化
QUALITY = 82        # webp 质量
WINDOW_DAYS = 8     # 网页显示最近 7 天（render.HOLD_DAYS），多留 1 天
WORKERS = 6         # 同时下载几张
RETRY_DAYS = 1      # 下载失败的图隔几天再试
VERSION = 3         # 判断规则的版本：改了规则就加 1，state 里旧版的记录重新判断一次
BING_WH = re.compile(r"&(amp;)?[wh]=\d+")
BING_WIDE = 1200    # 2. Bing 的小缩略图改取这个宽度（再切白边）
SINA_SIZE = re.compile(r"(sinaimg\.cn)/(?:thumbnail|thumb\d+|small|bmiddle|middle|orj\d+|mw\d+)/")


def enhance(bgr, long_side):
    """OpenCV 放大：去噪 → Lanczos 放大到长边 long_side → 只在亮度上 USM 锐化。返回 BGR 图。"""
    import cv2
    import numpy as np
    h, w = bgr.shape[:2]
    scale = long_side / max(h, w)
    if scale <= 1:
        return cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else bgr
    den = cv2.fastNlMeansDenoisingColored(bgr, None, DENOISE, DENOISE, 7, 21)
    up = cv2.resize(den, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_LANCZOS4)
    lab = cv2.cvtColor(up, cv2.COLOR_BGR2LAB)
    lum = lab[..., 0].astype(np.float32)
    detail = lum - cv2.GaussianBlur(lum, (0, 0), 0.5 + 0.5 * scale)
    detail[np.abs(detail) < THRESHOLD] = 0
    lab[..., 0] = np.clip(lum + AMOUNT * detail, 0, 255).astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def blur_score(bgr):
    """无参考模糊度 0〜1（Crété-Roffet 的 re-blur 法，见开头的说明）。"""
    import cv2
    import numpy as np
    f = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    k = np.ones((1, 9), np.float32) / 9
    out = 0.0
    for axis, kernel in ((0, k.T), (1, k)):
        d_f = np.abs(np.diff(f, axis=axis))
        d_b = np.abs(np.diff(cv2.filter2D(f, -1, kernel), axis=axis))
        s_f = float(d_f.sum())
        if s_f > 0:
            out = max(out, (s_f - float(np.maximum(0, d_f - d_b).sum())) / s_f)
    return out


def as_shown(bgr, target):
    """浏览器把图缩放到 target 长边时的样子（双线性）。"""
    import cv2
    h, w = bgr.shape[:2]
    s = target / max(h, w)
    return cv2.resize(bgr, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_LINEAR)


def unclear(bgr, target):
    """看不清吗：(要不要处理, 放大倍数, 模糊度)。两个条件都满足才处理（见开头的 1.）。"""
    scale = target / max(bgr.shape[:2])
    if scale < ENLARGE:
        return False, scale, None
    b = blur_score(as_shown(bgr, target))
    return b > BLUR, scale, b


def trim_white(bgr, tol=4):
    """切掉四周的白边（Bing 指定宽度时补的）。整行 / 整列都接近白色（≥ 255 − tol）的才切。"""
    import numpy as np
    content = (bgr < 255 - tol).any(axis=2)
    rows, cols = np.where(content.any(axis=1))[0], np.where(content.any(axis=0))[0]
    if not len(rows) or not len(cols):
        return bgr
    return bgr[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]


def plan_picks(picks):
    """「気になるかも？」の推薦カードの図 → (目標の長辺, 記事のページ)。愿望清单に合ったもの（各批の最初の大きいカード）は BIG_PX、
    ほかは CARD_PX。報道の図と同じ「看不清」の判定にかける（推薦カードだけ抜けていた：Bing の 100×100 が 7 倍に引き伸ばされて糊）。"""
    out = {}
    for x in picks or []:
        img = x.get("image")
        if not isinstance(img, str) or not img.startswith(("http://", "https://")):
            continue
        target = BIG_PX if x.get("kind") == "wish" else CARD_PX   # 愿望清单类（各批的第一张是大卡片）
        if out.get(img, (0,))[0] < target:
            out[img] = (target, x.get("url") or "")
    return out


def plan(reports, today):
    """最近 WINDOW_DAYS 天报道里的配图 → (目标长边, 原文网页)。每个关注项最新 BIG_PER_WORK 条、
    和头条（weight hero / lead）用 BIG_PX，其余 CARD_PX。借来的作品封面不算（那不是报道自己的图）。"""
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=WINDOW_DAYS - 1)).isoformat()
    by_work = {}
    for rep in reports:
        if rep.get("date", "") < cutoff:
            continue
        for b in rep.get("items") or []:
            for st in b.get("stories") or []:
                img = st.get("image")
                if not isinstance(img, str) or not img.startswith(("http://", "https://")) or st.get("image_via") == "作品封面":
                    continue
                by_work.setdefault(b["name"], []).append((st.get("date") or rep["date"], st))
    out = {}
    for xs in by_work.values():
        xs.sort(key=lambda x: x[0], reverse=True)
        for i, (_, st) in enumerate(xs):
            big = i < BIG_PER_WORK or st.get("weight") in ("hero", "lead")
            target = BIG_PX if big else CARD_PX
            if out.get(st["image"], (0,))[0] < target:
                out[st["image"]] = (target, st.get("url") or "")
    return out


def local_name(url):
    return f"pics/{hashlib.sha1(url.encode()).hexdigest()[:16]}.webp"


def _download(url, referer):
    """(图片字节, 是否要 Referer)。先照常下载；403 时带原文网页作 Referer 再试（防盗链，见 images.py）。
    Bing 缩略图去掉 w / h 取原尺寸（指定宽度时 Bing 补白边凑尺寸，和 render._img_url 一样；太小的在 process 里另取）。"""
    if images.is_bing_thumb(url):
        url = BING_WH.sub("", url)
    big = SINA_SIZE.sub(r"\1/mw2000/", url)
    if big != url:  # 新浪图床：/middle/ /orj360/ 这些是缩小版，/mw2000/ 是同一张的原尺寸（最长 2000）
        body, ref = _download(big, referer)
        if body:
            return body, ref
    f = images._fetch(url, images.IMAGE_LIMIT)
    if f.status == 403 and referer:
        g = images._fetch(url, images.IMAGE_LIMIT, referer)
        if g.status == 200 and not g.too_big:
            return g.body, True
    if f.status == 200 and not f.too_big:
        return f.body, False
    return None, False


def _decode(body):
    import cv2
    import numpy as np
    if not body:
        return None
    bgr = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        try:  # OpenCV 读不了的格式（avif 等）用 Pillow 读
            from PIL import Image
            import io
            bgr = cv2.cvtColor(np.array(Image.open(io.BytesIO(body)).convert("RGB")), cv2.COLOR_RGB2BGR)
        except Exception:
            bgr = None
    return bgr


def process(url, target, referer):
    """一张图：返回写进 state 的记录 {w, h, target, v, blur?, local?, why?, fail?}。看得清的只记尺寸，不存文件。"""
    import cv2
    body, ref = _download(url, referer)
    bgr = _decode(body)
    if bgr is None:   # 打不开了（期限切れの 404・削除）：dead → digest.retry_images が原文から図を探し直す
        return {"target": target, "v": VERSION, "fail": "下载失败或不是图片", "dead": True}
    h, w = bgr.shape[:2]
    rec = {"w": w, "h": h, "target": target, "v": VERSION}
    why = "防盗链" if ref else "期限付きの網址" if images.expiring(url) else ""
    if images.is_bing_thumb(url) and max(w, h) < images.MIN_LONG_SIDE:
        wide = _decode(images._fetch(BING_WH.sub("", url) + f"&w={BING_WIDE}", images.IMAGE_LIMIT).body)
        if wide is not None:
            bgr, why = trim_white(wide), "Bing の小さい縮小画像"
    if max(bgr.shape[:2]) < images.MIN_LONG_SIDE or float(bgr.std(axis=(0, 1)).max()) < images.BLANK_STD:
        return {**rec, "dead": True}   # 1×1 の空白・単色の代わりの図に変わっていた
    need, scale, b = unclear(bgr, target)
    if b is not None:
        rec["blur"] = round(b, 3)
    if need:
        why = why or "看不清"
    if not why:
        return rec
    # 看不清 → 放大到目标（最多 MAX_SCALE 倍）；只是换个地方放的（防盗链・Bing）→ 不放大，太大的缩到 BIG_PX
    long_side = min(target, round(max(bgr.shape[:2]) * MAX_SCALE)) if need else min(max(bgr.shape[:2]), BIG_PX)
    out = enhance(bgr, long_side)
    name = local_name(url)
    PICS_DIR.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".webp", out, [cv2.IMWRITE_WEBP_QUALITY, QUALITY])
    if not ok:
        return {**rec, "fail": "webp 保存失败"}
    (PICS_DIR.parent / name).write_bytes(buf.tobytes())
    rec.update(local=name, out=list(out.shape[1::-1]), why=why)
    if ref:
        rec["ref"] = True
    return rec


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def local_map():
    """render 用：原图地址 → 本站文件（docs/ 下的相对路径），只给文件真的在的。"""
    return {u: r["local"] for u, r in load_state().items()
            if isinstance(r, dict) and r.get("local") and (PICS_DIR.parent / r["local"]).exists()}


def run(today=None, reports=None):
    """处理最近几期的配图，删掉不再用的文件。返回 (新处理几张, 存到本站几张)。"""
    if reports is None:
        reports = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(REPORTS_DIR.glob("????-??-??.json"))[-WINDOW_DAYS - 2:]]
    today = today or max((r.get("date", "") for r in reports), default=dt.date.today().isoformat())
    want = plan(reports, today)
    try:
        picks = json.loads((ROOT / "state" / "recommend.json").read_text(encoding="utf-8")).get("picks")
    except (OSError, ValueError):
        picks = None
    for img, (target, referer) in plan_picks(picks).items():
        if want.get(img, (0,))[0] < target:
            want[img] = (target, referer)
    state = load_state()
    todo = []
    for url, (target, referer) in want.items():
        r = state.get(url)
        if isinstance(r, dict) and r.get("v") == VERSION and r.get("target", 0) >= target and not r.get("fail") \
                and (not r.get("local") or (PICS_DIR.parent / r["local"]).exists()):
            continue
        if isinstance(r, dict) and r.get("fail") and r.get("day", "") > (
                dt.date.fromisoformat(today) - dt.timedelta(days=RETRY_DAYS)).isoformat():
            continue
        todo.append((url, target, referer))
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for (url, _, _), rec in zip(todo, pool.map(lambda t: _safe(*t), todo)):
            if rec.get("fail"):
                rec["day"] = today
            state[url] = rec
    state = {u: r for u, r in state.items() if u in want}
    keep = {r["local"] for r in state.values() if r.get("local")}
    if PICS_DIR.exists():
        for f in PICS_DIR.glob("*.webp"):
            if f"pics/{f.name}" not in keep:
                f.unlink()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(dict(sorted(state.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    saved = sum(1 for url, *_ in todo if state.get(url, {}).get("local"))
    print(f"配图高清化：检查 {len(todo)} 张，存到本站 {saved} 张（看不清・Bing 小图・防盗链），本站共 {len(keep)} 张", file=sys.stderr)
    return len(todo), saved


def _safe(url, target, referer):
    try:
        return process(url, target, referer)
    except Exception as e:  # 一张图出问题不影响别的
        return {"target": target, "v": VERSION, "fail": f"{type(e).__name__}: {str(e)[:80]}"}


if __name__ == "__main__":
    run()
