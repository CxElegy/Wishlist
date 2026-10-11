"""每个关注项的配色：优先用 items.yaml 里手写的 theme，否则从封面图自动提取。

一套配色有两面（主面 bg/fg/accent 和副面 alt_*），板块里的卡片在两面之间交替；
split=true 时标题条做成两面对角分割（例如黑白主视觉的作品）。
"""

import colorsys
import io
import sys
import urllib.request

from sources import USER_AGENT, TIMEOUT

DEFAULT = {
    "bg": "#1A1C22", "fg": "#F1EEE6", "accent": "#E0703F",
    "alt_bg": "#F1EEE6", "alt_fg": "#1A1C22", "alt_accent": "#B83A17",
    "split": False, "font": "sans",
}


def _rgb(hex_):
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(c))) for c in rgb)


def _lum(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _shift(rgb, lightness, max_sat=0.35):
    """保持色相，把亮度改到指定值；饱和度封顶，避免底色太艳。"""
    h, _, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return tuple(c * 255 for c in colorsys.hls_to_rgb(h, lightness, min(s, max_sat)))


def _chroma(rgb):
    """色度：最亮通道减最暗通道。比 HLS 饱和度可靠（后者在近黑/近白时会虚高）。"""
    return (max(rgb) - min(rgb)) / 255


def _readable(rgb, bg, target=4.5):
    """调整 rgb 的亮度直到在 bg 上达到对比度要求。"""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    step = 0.04 if _lum(bg) < 0.3 else -0.04
    while contrast(rgb, bg) < target and 0 < l < 1:
        l = min(1, max(0, l + step))
        rgb = tuple(c * 255 for c in colorsys.hls_to_rgb(h, l, s))
    return rgb


def from_image(url):
    """下载封面图，提取主色生成一套配色；失败返回 None。"""
    try:
        from PIL import Image

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            img = Image.open(io.BytesIO(resp.read())).convert("RGB")
    except Exception as e:
        print(f"  [警告] 封面取色失败：{e}", file=sys.stderr)
        return None

    img.thumbnail((200, 200))
    # FASTOCTREE 能保留面积小但显眼的颜色（比如角色发色），MEDIANCUT 会把它们并进暗部
    q = img.quantize(16, method=Image.Quantize.FASTOCTREE)
    pal = q.getpalette()
    colors = [(n, tuple(pal[i * 3:i * 3 + 3])) for n, i in sorted(q.getcolors(), reverse=True)]

    base = colors[0][1]
    dark = _lum(base) < 0.35
    # 主面：主色调，压暗或提亮到适合做底色
    bg = _shift(base, 0.11) if dark else _shift(base, 0.93)
    fg = (242, 238, 230) if dark else (26, 28, 34)
    # 强调色：除底色外最鲜艳的颜色。鲜艳程度为主，占比开方后稍作加权，避免挑到零星噪点
    def vivid(entry):
        n, c = entry
        return _chroma(c) ** 1.5 * (0.5 + 0.5 * (n / colors[0][0]) ** 0.5)
    accent = max(colors[1:] or colors, key=vivid)[1]
    accent = _readable(_shift(accent, 0.6 if dark else 0.4, max_sat=0.75), bg)
    # 副面：同色系反向明度
    alt_bg = _shift(base, 0.93) if dark else _shift(base, 0.16)
    alt_fg = (26, 28, 34) if dark else (242, 238, 230)
    alt_accent = _readable(accent, alt_bg)
    return {
        "bg": _hex(bg), "fg": _hex(fg), "accent": _hex(accent),
        "alt_bg": _hex(alt_bg), "alt_fg": _hex(alt_fg), "alt_accent": _hex(alt_accent),
        "split": False, "font": "serif",
    }


def resolve(item, cover, cache):
    """手写 theme > 缓存 > 从封面提取 > 默认。手写的可以只写部分字段。"""
    manual = item.get("theme") or {}
    key = f"{item['name']}|{cover}"
    if key not in cache:
        cache[key] = (from_image(cover) if cover else None) or dict(DEFAULT)
    return {**cache[key], **manual}
