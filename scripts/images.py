"""报道配图：候选获取 → 有效性检查 → 回退选择 → 失败原因记录。

只用公开的网页元数据（og:image / twitter:image / JSON-LD）、正文图片、条目自带图、
MSN 的公开文章接口、Reddit（官方 API 或公开 RSS）、YouTube oEmbed，以及 Bing / Google 新闻上
同一篇文章的公开转载和新闻稿原出处。
请求不带 Referer、不伪装来源；被防盗链、防机器人或登录挡住的图就判为不可用，换下一张
（Cloudflare 等的防机器人验证不去绕过：那是网站明确不让程序取）。
视频帖（虎扑之类）没有 og:image 时，用视频封面（<video poster>）。
例外是防盗链：原文网页自己的图（新浪 sinaimg 这类）不带 Referer 都是 403，网页上也显示不出来，
所以都不行时再带「这张图所在的原文网页」作 Referer 试一次（如实写出图是从哪一页来的，不冒充别的网站）；
这样拿到的图浏览器直接打不开，由 hdimg.py 存一份到本站（docs/pics/）再显示。
还是不行时交给网页上的作品封面 / 作品名封面块兜底。
验证不了的图（大陆网站把海外服务器整个拦掉的那种）一律不用：看网页的人不在大陆就是一张打不开的图。

    res = pick(chosen, refs, url)      # res.image / res.source / res.trace / res.reason
    print(log_line("关注项", "标题", res))
"""

import html
import io
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field

import sources

TIMEOUT = 12                  # 单次请求超时（秒）
RETRIES = 1                   # 网络错误 / 超时 / 5xx 再试几次（403、404 这类不重试）
PAGE_LIMIT = 1_500_000        # 网页最多读这么多字节
IMAGE_LIMIT = 8_000_000       # 图片超过这个大小就不要（太大，网页加载慢）
MIN_SHORT_SIDE = 200          # 图片短边至少这么多像素
MIN_LONG_SIDE = 300           # 长边至少这么多像素
MAX_CHECKS = 12               # 每条报道最多实际检查这么多张候选图
STORY_BUDGET = 60             # 每条报道找图最多花这么多秒（到点不再开始新的检查）
BODY_IMAGES = 6               # 每个网页最多取这么多张正文图
SYNDICATION_SIMILARITY = 0.8  # 转载：两个标题的二元组 Dice 系数至少这么高才算同一篇（见 same_article）
SYNDICATION_DAYS = 30         # Google 新闻找转载：搜最近多少天
SYNDICATION_PAGES = 3         # Google 新闻找转载：最多读几篇（每篇要还原跳转链接再读网页）
GONE = (404, 410)             # 原文返回这些状态码：页面已经删了，这条报道不出刊
SHARP_LONG = 1000             # 原文的预览图长边不到这么多：同一页还有更大的预览图（JSON-LD 的 1920×1080 之类）就换大的
REFERER_TRIES = 3             # 防盗链（403）的原文图，最多带 Referer 重试几张
SAVED = "（本站保存）"        # 带 Referer 才拿到的图：来源名后面加这个，hdimg.py 存到本站

IMG_SKIP = re.compile(r"logo|icon|avatar|banner|sprite|badge|button|noimage|emoji|qrcode|/ads?/|\.svg|\.gif|data:", re.I)
# 网站 logo、全站共用的默认分享图：放在哪条报道上都不对（theouterhaven Logo.jpg、rbbtoday img_ogp.png、fb_um_logo_m.jpg）
GENERIC = re.compile(r"logo|noimage|no_image|no-image|img_ogp\.|default_ogp|ogp_default|og_default|default-og|share_default|placeholder"
                     r"|^/default/[0-9a-f]{8}/", re.I)  # 新浪的默认分享图 n.sinaimg.cn/default/2fb77759/…/320X320.png
BOT_WALL = re.compile(r"cloudflare|cloudfront|datadome|akamai|captcha|attention required|request blocked|access denied", re.I)

ICON_MIN = 32                 # 来源图标至少这么多像素（Google 图标服务查不到时给 16px 的地球图标）
FAVICON_SERVICE = "https://www.google.com/s2/favicons?domain={host}&sz=128"  # Google 的公开网站图标服务

_pages = {}   # 运行内缓存：网页地址 → Page
_checks = {}  # 运行内缓存：图片地址 → (ok, reason)
_reddit_blocked = []  # 本次运行里 Reddit 已经限流 / 拒绝过（没配 API 时），后面的帖子不再请求


def clear_cache():
    _pages.clear()
    _checks.clear()
    _icons.clear()
    _reddit_blocked.clear()
    sources._reddit_limited = None
    sources._hot_lists.clear()
    sources._search_cache.clear()
    _removed.clear()


# ---------- 下载 ----------

@dataclass
class Fetched:
    status: int | None = None
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    error: str = ""      # 网络错误 / 超时的说明；HTTP 错误码放在 status 里
    too_big: bool = False


def _ascii_url(url):
    """地址里有没编码的中日文（/画像/猫.jpg）时先编码，urllib 只收 ASCII（否则报 ordinal not in range(128)）。
    已经编码过的 %xx 不动；域名是中日文的用 IDNA。"""
    if url.isascii():
        return url
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    netloc = parts.netloc.replace(host, host.encode("idna").decode()) if host and not host.isascii() else parts.netloc
    q = lambda x, safe: urllib.parse.quote(x, safe=safe)
    return urllib.parse.urlunsplit((parts.scheme, netloc, q(parts.path, "/%:@!$&'()*+,;="),
                                    q(parts.query, "=&%:@!$'()*+,;/?"), q(parts.fragment, "%")))


def _fetch(url, limit, referer=None):
    """GET 一个地址，最多读 limit 字节。只带 User-Agent，不带 Cookie；referer 只在防盗链重试时给（图所在的原文网页）。"""
    last = Fetched(error="未请求")
    url = _ascii_url(url)
    for attempt in range(RETRIES + 1):
        try:
            hdr = {"User-Agent": sources.USER_AGENT, **({"Referer": referer} if referer else {})}
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                length = headers.get("content-length", "")
                if length.isdigit() and int(length) > limit:
                    return Fetched(resp.status, headers, b"", too_big=True)
                body = resp.read(limit + 1)
                return Fetched(resp.status, headers, body[:limit], too_big=len(body) > limit)
        except urllib.error.HTTPError as e:
            try:
                body = e.read(4000) if e.fp else b""
            except Exception:
                body = b""
            last = Fetched(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, body)
            if e.code < 500 and e.code != 429:
                return last
        except Exception as e:  # 超时、连接被重置、DNS ……
            reason = getattr(e, "reason", e)
            # reason 有时就是一句话（URLError("no host given")），这时写出那句话，不写类型名 str
            name = reason[:60] if isinstance(reason, str) else type(reason).__name__
            last = Fetched(error="超时" if "timed out" in str(reason).lower() or isinstance(reason, TimeoutError)
                           else f"网络错误 {name}")
        if attempt < RETRIES:
            time.sleep(1)
    return last


def _http_reason(f, what):
    """把一次失败的请求写成一句原因：'原文 403（Cloudflare）'、'图片 超时' ……"""
    if f.error:
        return f"{what} {f.error}"
    note = ""
    if f.status in (401, 403, 429, 503):
        text = f.body.decode("utf-8", "ignore") + " " + f.headers.get("server", "")
        m = BOT_WALL.search(text)
        if m:
            note = f"（防机器人：{m.group(0)}）"
        elif f.status == 429:
            note = "（限流）"
    return f"{what} HTTP {f.status}{note}"


# ---------- 图片检查 ----------

def check(url, referer=None):
    """图片能不能用：返回 (ok, 原因)。实际下载，按文件内容判断格式（不只看 Content-Type），
    检查大小和尺寸，OK 时原因是「宽×高」。结果在本次运行内缓存。referer 见 _fetch。"""
    if not url or not url.startswith(("http://", "https://")):
        return False, "地址无效"
    key = (url, referer) if referer else url
    if key in _checks:
        return _checks[key]
    f = _fetch(url, IMAGE_LIMIT, referer)
    if f.too_big:
        result = (False, f"图片超过 {IMAGE_LIMIT / 1_000_000:g}MB")
    elif f.status != 200:
        result = (False, _http_reason(f, "图片"))
    else:
        result = _inspect(f.body, f.headers.get("content-type", ""))
    _checks[key] = result
    return result


def size_of(why):
    """check 的 OK 原因「宽×高」→ (宽, 高)；不是这种写法返回 (0, 0)。"""
    m = re.fullmatch(r"(\d+)×(\d+)", why or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _inspect(body, content_type):
    from PIL import Image
    try:
        with Image.open(io.BytesIO(body)) as im:
            w, h = im.size
    except Exception:
        kind = "网页" if "html" in content_type or body.lstrip()[:1] == b"<" else (content_type or "未知内容")
        return False, f"不是图片（{kind}）"
    if min(w, h) < MIN_SHORT_SIDE or max(w, h) < MIN_LONG_SIDE:
        return False, f"图片太小 {w}×{h}"
    return True, f"{w}×{h}"


# ---------- 网页里的候选图 ----------

@dataclass
class Page:
    url: str
    ok: bool
    reason: str = ""                                  # 没拿到候选图的原因（打不开 / 没有图）
    og: list = field(default_factory=list)            # og:image / twitter:image
    jsonld: list = field(default_factory=list)        # JSON-LD 里的 image / thumbnailUrl
    body: list = field(default_factory=list)          # 正文 <img>
    status: int | None = None                         # 打不开时的 HTTP 状态码
    og_label: str = "og:image"                        # og 那一栏的来源名（MSN 接口取到的图写「MSN 接口」）
    icons: list = field(default_factory=list)         # 网站声明的图标（apple-touch-icon / icon），大的在前
    poster: list = field(default_factory=list)        # 视频封面（<video poster>）

    @property
    def gone(self):
        """原文已经删了（404 / 410）。"""
        return self.status in GONE


_META = (
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)(?::src|:url)?["\'][^>]*content=["\']([^"\']*)',
    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)(?::src|:url)?["\']',
)


def page(url):
    """读取网页并解析出候选图。结果在本次运行内缓存。"""
    if url in _pages:
        return _pages[url]
    if not url or "news.google.com" in url:
        p = Page(url, False, "原文是未还原的 Google 新闻跳转链接")
    elif MSN_ARTICLE.match(url):
        p = msn_page(url)
    else:
        f = _fetch(url, PAGE_LIMIT)
        if f.status != 200:
            p = Page(url, False, _http_reason(f, "原文"), status=f.status)
        else:
            p = parse_page(url, f.body.decode("utf-8", "ignore"))
    _pages[url] = p
    return p


def parse_page(url, text):
    p = Page(url, True)
    for pattern in _META:
        for m in re.finditer(pattern, text, re.I):
            u = _abs(url, m.group(1))
            if u and u not in p.og:
                p.og.append(u)
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', text, re.I | re.S):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for u in _jsonld_images(data):
            u = _abs(url, u)
            if u and u not in p.jsonld:
                p.jsonld.append(u)
    for tag in re.findall(r"<video\b[^>]*>", text, re.I):
        src = re.search(r'poster=["\']([^"\']+)', tag, re.I)
        u = _abs(url, src.group(1)) if src else ""
        if u and u not in p.poster:
            p.poster.append(u)
    m = re.search(r"<article\b.*?</article>", text, re.I | re.S)
    for tag in re.findall(r"<img\b[^>]*>", m.group(0) if m else text, re.I):
        src = re.search(r'(?:data-src|data-original|src)=["\']([^"\']+)', tag, re.I)
        if not src or IMG_SKIP.search(src.group(1)):
            continue
        u = _abs(url, src.group(1))
        if u and u not in p.body:
            p.body.append(u)
        if len(p.body) >= BODY_IMAGES:
            break
    icons = []
    for tag in re.findall(r"<link\b[^>]*>", text, re.I):
        rel = re.search(r'rel=["\']([^"\']+)', tag, re.I)
        href = re.search(r'href=["\']([^"\']+)', tag, re.I)
        if not rel or not href or "icon" not in rel.group(1).lower() or "mask" in rel.group(1).lower():
            continue
        sizes = re.search(r'sizes=["\'](\d+)', tag, re.I)
        size = int(sizes.group(1)) if sizes else (180 if "apple" in rel.group(1).lower() else 0)
        u = _abs(url, href.group(1))
        if u and not u.lower().split("?")[0].endswith(".svg"):
            icons.append((size, u))
    p.icons = [u for _, u in sorted(icons, key=lambda x: -x[0])]
    if not (p.og or p.jsonld or p.body or p.poster):
        p.reason = "原文没有图片元数据，正文也没有图"
    return p


def _abs(base, u):
    u = html.unescape((u or "").strip())
    if not u:
        return ""
    u = urllib.parse.urljoin(base, u)
    return u if u.startswith(("http://", "https://")) else ""


def _jsonld_images(node):
    """JSON-LD（schema.org）里所有 image / thumbnailUrl 的地址。"""
    if isinstance(node, list):
        for x in node:
            yield from _jsonld_images(x)
    elif isinstance(node, dict):
        for key in ("image", "thumbnailUrl"):
            v = node.get(key)
            for x in v if isinstance(v, list) else [v]:
                if isinstance(x, str):
                    yield x
                elif isinstance(x, dict) and isinstance(x.get("url"), str):
                    yield x["url"]
        for k, v in node.items():
            if k not in ("image", "thumbnailUrl") and isinstance(v, (dict, list)):
                yield from _jsonld_images(v)


# 文章 ar- / 视频 vi- / 图集 ss- / 图集 gm-：都是同一个公开接口
MSN_ARTICLE = re.compile(r"https?://(?:www\.)?msn\.(?:com|cn)/([a-z]{2}-[a-z]{2})/.*?/(?:ar|vi|ss|gm)-([A-Za-z0-9]+)", re.I)


def msn_page(url):
    """MSN 的文章页是脚本渲染的空壳（HTML 里没有图）：改读 MSN 网页自己用的公开文章接口，取文章里的图。
    视频（vi-）没有 imageResources，图在 thumbnail（视频的封面）；图集在 slides。"""
    m = MSN_ARTICLE.match(url)
    f = _fetch(f"https://assets.msn.com/content/view/v2/Detail/{m.group(1).lower()}/{m.group(2)}", PAGE_LIMIT)
    if f.status != 200:
        return Page(url, False, _http_reason(f, "原文") + "（MSN 接口）", status=f.status)
    try:
        data = json.loads(f.body)
    except ValueError:
        return Page(url, False, "原文 MSN 接口返回格式无法解析")
    p = Page(url, True, og_label="MSN 接口")
    thumb = (data.get("thumbnail") or {}).get("image") if isinstance(data.get("thumbnail"), dict) else None
    slides = [(s or {}).get("image") for s in data.get("slides") or [] if isinstance(s, dict)]
    for im in [*(data.get("imageResources") or []), thumb, *slides]:
        u = _abs(url, (im or {}).get("url") if isinstance(im, dict) else None)
        if u and u not in p.og:
            p.og.append(u)
    if not p.og:
        p.reason = "原文没有图片元数据，正文也没有图"
    return p


_removed = {}  # 运行内缓存：Reddit 帖子 → 删了吗（True / False / None = 拿不到）


def gone(url):
    """原文是不是已经删了：网页 404 / 410；Reddit 帖子看正文是不是 [removed] / [deleted]（sources.reddit_removed，
    拿不到时不当成删了）。没还原的 Google 跳转不判断。"""
    if not url or "news.google.com" in url:
        return False
    if REDDIT_POST.match(url):
        if url not in _removed:
            _removed[url] = sources.reddit_removed(url)
        return _removed[url] is True
    return page(url).gone


def og_image(url):
    """网页的第一张预览图（作品官网取封面用）。"""
    p = page(url)
    return (p.og or p.jsonld or [None])[0]


# ---------- 来源图标（拿不到配图时，网页上显示来源网站的图标） ----------

_icons = {}  # 运行内缓存：图标地址 → 能不能用


def check_icon(url):
    """图标能不能用：实际下载，是图片，最短边至少 ICON_MIN 像素。"""
    if not url or not url.startswith(("http://", "https://")):
        return False
    if url not in _icons:
        f = _fetch(url, 1_000_000)
        ok = False
        if f.status == 200 and not f.too_big:
            from PIL import Image
            try:
                with Image.open(io.BytesIO(f.body)) as im:
                    ok = min(im.size) >= ICON_MIN
            except Exception:
                pass
        _icons[url] = ok
    return _icons[url]


def base_domain(host):
    """主域名：news.nicovideo.jp → nicovideo.jp，news.yahoo.co.jp → yahoo.co.jp。"""
    parts = (host or "").lower().split(".")
    n = 3 if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("co", "ne", "or", "ac", "go", "com", "net", "org") else 2
    return ".".join(parts[-n:])


def source_icon(url):
    """来源网站的图标：网站自己声明的（apple-touch-icon / icon，大的优先），没有或打不开就用
    Google 的公开网站图标服务，先查完整域名再查主域名。每个都实际下载检查；都不行返回 None。"""
    host = (urllib.parse.urlparse(url or "").hostname or "").lower()
    if not host or host == "news.google.com":
        return None
    p = _pages.get(url) or (page(url) if not REDDIT_POST.match(url) else None)
    candidates = (p.icons[:3] if p and p.ok else []) + [FAVICON_SERVICE.format(host=h) for h in dict.fromkeys([host, base_domain(host)])]
    return next((u for u in candidates if check_icon(u)), None)


# ---------- Reddit / YouTube ----------

REDDIT_POST = re.compile(r"https?://(?:www\.|old\.)?reddit\.com(/r/[^/]+/comments/[^/]+)")


def link_image(url):
    """帖子外链的预览图：YouTube 视频 / 播放列表用官方 oEmbed 取封面，其它网页取 og:image。
    链回 Reddit 本身的（纯文字帖）不算。"""
    host = urllib.parse.urlparse(url or "").netloc.lower()
    if not host or host.endswith("reddit.com") or host.endswith("redd.it"):
        return None
    if host.endswith("youtube.com") or host.endswith("youtu.be"):
        f = _fetch("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe=""), 100_000)
        try:
            return json.loads(f.body).get("thumbnail_url") if f.status == 200 else None
        except ValueError:
            return None
    return og_image(url)


def reddit_candidates(url):
    """Reddit 帖子的候选图和失败原因：先读帖子本身（配了 REDDIT_CLIENT_ID 走官方 API，否则读公开 RSS），
    帖子自带预览图就用；没有就用它的外链（YouTube 封面 / 网页预览图）。返回 ([(来源, 地址)], 原因)。"""
    m = REDDIT_POST.match(url or "")
    if not m:
        return [], ""
    if _reddit_blocked:
        return [], _reddit_blocked[0] + "（本次运行已跳过后续 Reddit 请求）"
    try:
        is_json, data = sources._reddit_get(m.group(1), {"limit": 1})
    except urllib.error.HTTPError as e:
        hint = "（未配置 REDDIT_CLIENT_ID，Reddit 拦截云服务器的匿名请求）" if e.code in (403, 429) and not sources._reddit_token else ""
        if hint:
            _reddit_blocked.append(f"Reddit HTTP {e.code}{hint}")
        return [], f"Reddit HTTP {e.code}{hint}"
    except Exception as e:
        return [], f"Reddit 网络错误 {type(e).__name__}"
    found, outbound = [], None
    if is_json:
        try:
            post = json.loads(data)[0]["data"]["children"][0]["data"]
        except (ValueError, LookupError, TypeError):
            return [], "Reddit 返回格式无法解析"
        preview = ((post.get("preview") or {}).get("images") or [{}])[0].get("source", {}).get("url")
        if preview:
            found.append(("Reddit 预览图", html.unescape(preview)))
        outbound = post.get("url_overridden_by_dest")
    else:
        outbound = next(iter(sources.reddit_links(data).values()), None)
    if outbound:
        img = link_image(outbound)
        host = urllib.parse.urlparse(outbound).netloc
        if img:
            found.append((f"帖子外链 {host}", img))
    return found, "" if found else "Reddit 帖子没有图，也没有带图的外链"


# ---------- Bing 新闻上的同一篇转载 ----------

def title_grams(text):
    t = re.sub(r"\W+", "", unicodedata.normalize("NFKC", text or "").lower())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similarity(a, b):
    ga, gb = title_grams(a), title_grams(b)
    return len(ga & gb) / max(1, min(len(ga), len(gb)))


def same_article(a, b):
    """转载用：两个标题整体相近才算同一篇（Dice 系数）。只看短标题落在长标题里的比例（similarity）不行：
    「From Season 5 ending…」会被当成「'The Boys' season 5 ending explained: …」的转载。"""
    ga, gb = title_grams(_strip_outlet(a)), title_grams(_strip_outlet(b))
    return 2 * len(ga & gb) / max(1, len(ga) + len(gb)) >= SYNDICATION_SIMILARITY


def _strip_outlet(title):
    """去掉标题末尾的媒体名（Google 新闻的「… - ライブドアニュース」、「… | RBB TODAY」）。"""
    return re.sub(r"\s+[-|｜–—]\s+[^-|｜–—]{1,30}$", "", (title or "").strip())


def search_phrase(title):
    """拿去搜转载的标题前半句：标题常被截断，各家后半句的措辞也常不一样（中日文取前 30 字，其它取前 10 个词）。"""
    t = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", title or "")).strip()
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]", t):
        return t[:30]
    return " ".join(t.split(" ")[:10])


def news_lang(title):
    """按标题文字选 Google 新闻的语言版本：(hl, gl, ceid)。"""
    if re.search(r"[\u3040-\u30ff]", title or ""):
        return "ja", "JP", "JP:ja"
    if re.search(r"[\uac00-\ud7af]", title or ""):
        return "ko", "KR", "KR:ko"
    if re.search(r"[\u4e00-\u9fff]", title or ""):
        return "zh-CN", "CN", "CN:zh-Hans"
    return "en-US", "US", "US:en"


def syndicated_candidates(title, skip_url=""):
    """原文打不开（防机器人）或没有图时，找同一篇的转载 / 新闻稿原出处：
    1. Bing 新闻搜同一标题：Bing 自己的缩略图（bing.com 提供，原站挡机器人也能用）和转载网页的预览图；
       搜回来的就是原文本身时，只用它的 Bing 缩略图。
    2. Google 新闻搜标题前半句：转载网页 / 新闻稿原出处（PR TIMES 等）的预览图。
    标题几乎相同（SYNDICATION_SIMILARITY）才算同一篇；国外网站排在中国大陆网站前面。
    返回 ([(来源, 地址)], 原因)；来源写明是哪个网站的转载。"""
    if len(title_grams(title)) < 8:
        return [], "标题太短，不找转载"
    found, read = [], {skip_url}  # found: (来源, 图片地址, 所在网页)

    def add_page(url, host):
        read.add(url)
        p = page(url)
        for u in (p.og + p.jsonld)[:2]:
            found.append((f"转载 {host}", u, url))

    for e in sources.bing_news(title)[:8]:
        if not same_article(title, e.title):
            continue
        host = urllib.parse.urlparse(e.url).netloc
        if e.image:
            label = "Bing 缩略图" if e.url == skip_url else f"转载 {host}（Bing 缩略图）"
            found.append((label, e.image, e.url))
        if e.url not in read:
            add_page(e.url, host)
    hits = [e for e in sources.google_news(search_phrase(title), SYNDICATION_DAYS, news_lang(title))
            if same_article(title, e.title)]
    hits.sort(key=lambda e: sources.is_domestic(e.url, e.source))
    for e in hits[:SYNDICATION_PAGES]:
        url = sources.resolve_url(e.url)
        if url not in read and "news.google.com" not in url:
            add_page(url, urllib.parse.urlparse(url).netloc)
    found.sort(key=lambda x: sources.is_domestic(x[2]))
    return [(label, u) for label, u, _ in found], "" if found else "Bing / Google 新闻都没有找到带图的同一篇转载"


# ---------- 选择 ----------

@dataclass
class Result:
    image: str | None = None
    source: str = ""                               # 选中的图从哪来：AI 挑选 / 条目自带 / og:image / 转载 xxx ……
    trace: list = field(default_factory=list)      # [(来源, 地址, 结果)]：每张检查过的候选图
    notes: list = field(default_factory=list)      # 拿候选图时的问题：原文 403（Cloudflare）……

    @property
    def reason(self):
        """没图时的原因（一句话，日志用）。"""
        if self.image:
            return ""
        parts = list(dict.fromkeys(self.notes))
        rejected = Counter(r for _, _, r in self.trace)
        parts += [f"{r}×{n}" if n > 1 else r for r, n in rejected.items()]
        return "；".join(parts) or "没有任何候选图"

    @property
    def category(self):
        """汇总用的大类。有图：按来源；没图：检查过候选图的，按最多的那种不合格原因；
        一张候选图都没有的，按拿候选图时遇到的问题（原文打不开 / 没有图 / Reddit 失败）。"""
        if self.image:
            return "有图：" + self.source.split(" ")[0]
        kinds = Counter(kind(r) for _, _, r in self.trace)
        if kinds:
            return "无图：" + kinds.most_common(1)[0][0]
        for note in self.notes:
            k = kind(note)
            if k != "其它":
                return "无图：" + k
        return "无图：没有候选图"


_KINDS = (  # (原因里的关键字, 大类)：从具体到笼统，第一个命中的算
    ("Reddit HTTP", "Reddit 请求失败"), ("Reddit 网络错误", "Reddit 请求失败"),
    ("原文 HTTP", "原文 HTTP 错误"), ("原文 超时", "原文超时"), ("原文 网络错误", "原文网络错误"),
    ("Google 新闻跳转", "原文链接未还原"), ("没有图片元数据", "原文没有图"), ("Reddit 帖子没有图", "原文没有图"),
    ("图片 HTTP", "候选图 HTTP 错误"), ("图片 超时", "候选图超时"), ("图片 网络错误", "候选图网络错误"),
    ("不是图片", "候选图格式错误"), ("太小", "候选图尺寸不合格"), ("图片超过", "候选图过大"),
    ("地址无效", "候选图地址无效"), ("logo / 默认图", "候选图是网站 logo / 默认图"), ("和别的报道重复", "候选图和别的报道重复"),
)


def kind(reason):
    """把一句原因归到大类：HTTP 错误 / 超时 / 网络错误 / 格式错误 / 尺寸不合格 ……；防机器人单独标出。"""
    for key, label in _KINDS:
        if key in reason:
            return label + ("（防机器人）" if "防机器人" in reason else "")
    return "其它"


BING_THUMB = re.compile(r"^https?://(www\.)?bing\.com/th\?")


def is_bing_thumb(u):
    """Bing ニュースの縮小画像（bing.com/th?id=…）。Bing が自分で切った一部分のことがある（横長のバナーが縦の一切れになる）。"""
    return bool(isinstance(u, str) and BING_THUMB.match(u))


def pick(chosen, refs, url, max_checks=MAX_CHECKS, budget=None, avoid=()):
    """一条报道的配图。按顺序检查候选图，第一张可用的就用：
    AI 挑的 > 条目自带图 > 原文（og:image > JSON-LD > 正文图；Reddit 帖子读帖子本身和外链）
    > 其它来源的原文 > 条目自带的 Bing 缩略图 > Bing / Google 新闻上的同一篇转载。
    Bing 缩略图是 Bing 裁过的一部分（横长的图会变成竖的一截），所以排在原文的图后面，原文拿不到图时才用。
    原文的预览图（og:image / JSON-LD）长边不到 SHARP_LONG 时，同一页后面更大的预览图优先（同一张图的大尺寸版）。
    都不行时，原文网页自己的图里被防盗链挡掉（403）的，带原文网页作 Referer 再试（来源名加 SAVED，hdimg.py 存到本站）。
    还不行返回 image=None（网页上这条进「其他消息」文字列表，或用这一版面唯一一次的作品封面）。
    网站 logo / 全站默认分享图不用；avoid 里的图（同一期别的报道已经用了）也不用，免得几张卡片同一张图。"""
    res = Result()
    seen = set()
    from_page = {}  # 原文网页（不是转载）里的候选图 → 那一页的地址：防盗链重试时作 Referer
    deadline = time.monotonic() + (STORY_BUDGET if budget is None else budget)

    def stages():
        yield [("AI 挑选", chosen)]
        # 以前给 Reddit 帖子找来的「转载图」不要：帖子没有转载，那是别的文章的图
        own = [("条目自带", e.image) for e in refs if not (sources.is_reddit(e) and (e.image_via or "").startswith("转载"))]
        yield [x for x in own if not is_bing_thumb(x[1])]
        pages = [url] + [sources.entry_link(e) for e in refs[1:3]]
        for i, link in enumerate(pages):
            if REDDIT_POST.match(link or ""):
                found, note = reddit_candidates(link)
            else:
                p = page(link)
                found = _candidates(p)
                for _, u in found:
                    from_page.setdefault(u, link)
                note = p.reason
            if i:
                found = [(f"{label}（其它来源）", u) for label, u in found]
            if note:
                res.notes.append(note)
            yield found
        yield [("条目自带（Bing 缩略图）", u) for _, u in own if is_bing_thumb(u)]
        if refs and not sources.is_reddit(refs[0]):  # Reddit 帖子是网友发的，没有「转载」
            found, note = syndicated_candidates(refs[0].title, url)
            if note:
                res.notes.append(note)
            yield found

    def preview(label):
        return label.split("（")[0] in ("og:image", "MSN 接口", "JSON-LD", "视频封面")

    def scan():
        for stage in stages():
            small = None  # 这一段里先找到的、偏小的原文预览图（后面有更大的就换）
            for label, img in stage:
                if not img or img in seen:
                    continue
                if small and not preview(label):
                    break
                if GENERIC.search(urllib.parse.urlparse(img).path) or img in avoid:
                    seen.add(img)
                    res.trace.append((label, img, "网站 logo / 默认图" if img not in avoid else "和别的报道重复"))
                    continue
                if time.monotonic() > deadline:
                    res.notes.append(f"找图超过 {STORY_BUDGET if budget is None else budget} 秒，停止")
                    break
                seen.add(img)
                ok, why = check(img)
                res.trace.append((label, img, why if not ok else "OK"))
                if ok:
                    if small is None and preview(label) and max(size_of(why)) < SHARP_LONG:
                        small = (label, img, max(size_of(why)))
                        continue
                    if small is None or max(size_of(why)) > small[2]:
                        res.image, res.source = img, label
                        return True
                if len(seen) >= max_checks:
                    res.notes.append(f"已检查 {max_checks} 张，停止")
                    break
            if small:
                res.image, res.source = small[1], small[0]
                return True
            if res.notes and res.notes[-1].startswith(("找图超过", "已检查")):
                return False
        return False

    if scan():
        return res
    # 防盗链：原文网页自己的图，带那一页作 Referer 再试（浏览器打不开，hdimg.py 存到本站）
    tries = 0
    for label, img, why in list(res.trace):
        if tries >= REFERER_TRIES:
            break
        if "HTTP 403" not in why or img not in from_page or img in avoid:
            continue
        tries += 1
        ok, why = check(img, referer=from_page[img])
        res.trace.append((label + SAVED, img, why if not ok else "OK"))
        if ok:
            res.image, res.source = img, label + SAVED
            return res
    return res


def _candidates(p):
    """网页的候选图，按可信的顺序：预览图（og）> JSON-LD > 视频封面 > 正文图。"""
    return [(p.og_label, u) for u in p.og] + [("JSON-LD", u) for u in p.jsonld] + \
        [("视频封面", u) for u in p.poster] + [("正文图", u) for u in p.body]


def log_line(name, headline, res):
    """每条报道一行，打印到 GitHub Actions 日志里。"""
    head = f"  [配图] {name} | {headline[:30]}"
    if res.image:
        return f"{head} | {res.source}" + (f"（前 {len(res.trace) - 1} 张不合格）" if len(res.trace) > 1 else "")
    return f"{head} | 无图：{res.reason}"


class Stats:
    """整期的配图汇总。"""

    def __init__(self):
        self.counts = Counter()
        self.dropped = 0  # 原文已删（404 / 410）、不出刊的报道

    def add(self, res, fallback_cover=False):
        self.counts["无图→作品封面" if fallback_cover else res.category] += 1

    def drop(self):
        self.dropped += 1

    def summary(self):
        total = sum(self.counts.values())
        ok = sum(n for k, n in self.counts.items() if k.startswith("有图"))
        parts = [f"{k} {n}" for k, n in self.counts.most_common()]
        gone = f"（另有 {self.dropped} 条原文已删，不出刊）" if self.dropped else ""
        return f"配图汇总：共 {total} 条{gone}，有图 {ok} 条 · " + " · ".join(parts)
