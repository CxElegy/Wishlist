"""配图的高清化・本站保存：用 OpenCV 的规则处理（不用 AI、不叫外部服务）。

两种情况把报道的配图存一份到 docs/pics/（网页优先用这份，打不开再用原图）：
  1. 太小：要放在大位置（各版面的头条、トップのポスター）的图长边不到 BIG_PX 的 NEED，
     普通卡片的图不到 CARD_PX 的 NEED → 放大到目标尺寸（最多 MAX_SCALE 倍）
  2. 防盗链：浏览器打不开（新浪 sinaimg 这类，不带 Referer 就 403）→ 带原文网页作 Referer 下载，存一份

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

ROOT = pathlib.Path(__file__).resolve().parent.parent
PICS_DIR = ROOT / "docs" / "pics"
STATE_FILE = ROOT / "state" / "hdimg.json"
REPORTS_DIR = ROOT / "reports"

BIG_PX = 1280       # 大位置的目标长边：头条约 600 CSS px 宽 × 2 倍屏（平板・手机）
CARD_PX = 720       # 普通卡片的目标长边：约 300 CSS px × 2 倍屏
NEED = 0.75         # 原图长边不到目标的 75% 才放大（够用的不动，省仓库空间）
MAX_SCALE = 3.0     # 最多放大几倍（再大也只是更糊）
BIG_PER_WORK = 2    # 每个关注项最新几条有图的报道算「大位置」（头条＋トップのポスター候选）
DENOISE = 3         # ① 去噪强度（OpenCV 的 h / hColor，3 = 轻轻去掉 JPEG 块，不抹掉细节）
AMOUNT = 0.7        # ③ 锐化强度
THRESHOLD = 2.0     # ③ 亮度变化小于这个（0〜255）的地方不锐化
QUALITY = 82        # webp 质量
WINDOW_DAYS = 8     # 网页显示最近 7 天（render.HOLD_DAYS），多留 1 天
WORKERS = 6         # 同时下载几张
RETRY_DAYS = 1      # 下载失败的图隔几天再试
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
    Bing 缩略图去掉 w / h 取原尺寸（指定宽度时 Bing 补白边凑尺寸，和 render._img_url 一样）。"""
    if images.is_bing_thumb(url):
        url = re.sub(r"&(amp;)?[wh]=\d+", "", url)
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


def process(url, target, referer):
    """一张图：返回写进 state 的记录 {w, h, target, local?, ref?, fail?}。"""
    import cv2
    import numpy as np
    body, ref = _download(url, referer)
    bgr = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR) if body else None
    if bgr is None:
        try:  # OpenCV 读不了的格式（avif 等）用 Pillow 读
            from PIL import Image
            import io
            bgr = cv2.cvtColor(np.array(Image.open(io.BytesIO(body)).convert("RGB")), cv2.COLOR_RGB2BGR) if body else None
        except Exception:
            bgr = None
    if bgr is None:
        return {"target": target, "fail": "下载失败或不是图片"}
    h, w = bgr.shape[:2]
    rec = {"w": w, "h": h, "target": target}
    small = max(w, h) < target * NEED
    if not (small or ref):
        return rec
    long_side = min(target, round(max(w, h) * MAX_SCALE)) if small else min(max(w, h), BIG_PX)
    out = enhance(bgr, long_side)
    name = local_name(url)
    PICS_DIR.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".webp", out, [cv2.IMWRITE_WEBP_QUALITY, QUALITY])
    if not ok:
        return {**rec, "fail": "webp 保存失败"}
    (ROOT / "docs" / name).write_bytes(buf.tobytes())
    rec.update(local=name, out=list(out.shape[1::-1]))
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
            if isinstance(r, dict) and r.get("local") and (ROOT / "docs" / r["local"]).exists()}


def run(today=None, reports=None):
    """处理最近几期的配图，删掉不再用的文件。返回 (新处理几张, 存到本站几张)。"""
    if reports is None:
        reports = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(REPORTS_DIR.glob("????-??-??.json"))[-WINDOW_DAYS - 2:]]
    today = today or max((r.get("date", "") for r in reports), default=dt.date.today().isoformat())
    want = plan(reports, today)
    state = load_state()
    todo = []
    for url, (target, referer) in want.items():
        r = state.get(url)
        if isinstance(r, dict) and r.get("target", 0) >= target and not r.get("fail") \
                and (not r.get("local") or (ROOT / "docs" / r["local"]).exists()):
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
    print(f"配图高清化：检查 {len(todo)} 张，存到本站 {saved} 张（放大・防盗链），本站共 {len(keep)} 张", file=sys.stderr)
    return len(todo), saved


def _safe(url, target, referer):
    try:
        return process(url, target, referer)
    except Exception as e:  # 一张图出问题不影响别的
        return {"target": target, "fail": f"{type(e).__name__}: {str(e)[:80]}"}


if __name__ == "__main__":
    run()
