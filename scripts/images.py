"""报道配图：候选获取 → 有效性检查 → 回退选择 → 失败原因记录。

只用公开的网页元数据（og:image / twitter:image / JSON-LD）、正文图片、条目自带图、
Reddit（官方 API 或公开 RSS）、YouTube oEmbed 和 Bing 新闻上同一篇文章的公开转载。
请求不带 Referer、不伪装来源；被防盗链、防机器人或登录挡住的图就判为不可用，换下一张，
都不行时交给网页上的作品封面 / 作品名封面块兜底。

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
SYNDICATION_SIMILARITY = 0.8  # Bing 转载：标题二元组重合度至少这么高才算同一篇

IMG_SKIP = re.compile(r"logo|icon|avatar|banner|sprite|badge|button|noimage|emoji|qrcode|/ads?/|\.svg|\.gif|data:", re.I)
BOT_WALL = re.compile(r"cloudflare|cloudfront|datadome|akamai|captcha|attention required|request blocked|access denied", re.I)

_pages = {}   # 运行内缓存：网页地址 → Page
_checks = {}  # 运行内缓存：图片地址 → (ok, reason)
_reddit_blocked = []  # 本次运行里 Reddit 已经限流 / 拒绝过（没配 API 时），后面的帖子不再请求


def clear_cache():
    _pages.clear()
    _checks.clear()
    _reddit_blocked.clear()


# ---------- 下载 ----------

@dataclass
class Fetched:
    status: int | None = None
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    error: str = ""      # 网络错误 / 超时的说明；HTTP 错误码放在 status 里
    too_big: bool = False


def _fetch(url, limit):
    """GET 一个地址，最多读 limit 字节。只带 User-Agent，不带 Referer / Cookie。"""
    last = Fetched(error="未请求")
    for attempt in range(RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": sources.USER_AGENT})
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
            last = Fetched(error="超时" if "timed out" in str(reason).lower() or isinstance(reason, TimeoutError)
                           else f"网络错误 {type(reason).__name__}")
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

def check(url):
    """图片能不能用：返回 (ok, 原因)。实际下载，按文件内容判断格式（不只看 Content-Type），
    检查大小和尺寸。结果在本次运行内缓存。"""
    if not url or not url.startswith(("http://", "https://")):
        return False, "地址无效"
    if url in _checks:
        return _checks[url]
    f = _fetch(url, IMAGE_LIMIT)
    if f.too_big:
        result = (False, f"图片超过 {IMAGE_LIMIT / 1_000_000:g}MB")
    elif f.status != 200:
        result = (False, _http_reason(f, "图片"))
    else:
        result = _inspect(f.body, f.headers.get("content-type", ""))
    _checks[url] = result
    return result


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
    else:
        f = _fetch(url, PAGE_LIMIT)
        if f.status != 200:
            p = Page(url, False, _http_reason(f, "原文"))
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
    if not (p.og or p.jsonld or p.body):
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


def og_image(url):
    """网页的第一张预览图（作品官网取封面用）。"""
    p = page(url)
    return (p.og or p.jsonld or [None])[0]


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


def syndicated_candidates(title, skip_url=""):
    """新闻稿常被好几家网站转载：用 Bing 新闻搜同一标题，标题几乎相同的那几篇的预览图。
    返回 ([(来源, 地址)], 原因)；来源写明是哪个网站的转载。"""
    if len(title_grams(title)) < 8:
        return [], "标题太短，不找转载"
    found = []
    for e in sources.bing_news(title)[:8]:
        if e.url == skip_url or similarity(title, e.title) < SYNDICATION_SIMILARITY:
            continue
        host = urllib.parse.urlparse(e.url).netloc
        if e.image:
            found.append((f"转载 {host}（Bing 缩略图）", e.image))
        p = page(e.url)
        for u in (p.og + p.jsonld)[:2]:
            found.append((f"转载 {host}", u))
    return found, "" if found else "Bing 新闻没有找到带图的同一篇转载"


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
    ("地址无效", "候选图地址无效"),
)


def kind(reason):
    """把一句原因归到大类：HTTP 错误 / 超时 / 网络错误 / 格式错误 / 尺寸不合格 ……；防机器人单独标出。"""
    for key, label in _KINDS:
        if key in reason:
            return label + ("（防机器人）" if "防机器人" in reason else "")
    return "其它"


def pick(chosen, refs, url, max_checks=MAX_CHECKS, budget=None):
    """一条报道的配图。按顺序检查候选图，第一张可用的就用：
    AI 挑的 > 条目自带图 > 原文（og:image > JSON-LD > 正文图；Reddit 帖子读帖子本身和外链）
    > 其它来源的原文 > Bing 新闻上的同一篇转载。都不行返回 image=None（网页上用作品封面代替）。"""
    res = Result()
    seen = set()
    deadline = time.monotonic() + (STORY_BUDGET if budget is None else budget)

    def stages():
        yield [("AI 挑选", chosen)]
        yield [("条目自带", e.image) for e in refs]
        pages = [url] + [sources.resolve_url(e.url) for e in refs[1:3]]
        for i, link in enumerate(pages):
            if REDDIT_POST.match(link or ""):
                found, note = reddit_candidates(link)
            else:
                p = page(link)
                found = [("og:image", u) for u in p.og] + [("JSON-LD", u) for u in p.jsonld] + \
                        [("正文图", u) for u in p.body]
                note = p.reason
            if i:
                found = [(f"{label}（其它来源）", u) for label, u in found]
            if note:
                res.notes.append(note)
            yield found
        if refs and not refs[0].source.startswith("r/"):
            found, note = syndicated_candidates(refs[0].title, url)
            if note:
                res.notes.append(note)
            yield found

    for stage in stages():
        for label, img in stage:
            if not img or img in seen:
                continue
            if time.monotonic() > deadline:
                res.notes.append(f"找图超过 {STORY_BUDGET if budget is None else budget} 秒，停止")
                return res
            seen.add(img)
            ok, why = check(img)
            res.trace.append((label, img, why if not ok else "OK"))
            if ok:
                res.image, res.source = img, label
                return res
            if len(seen) >= max_checks:
                res.notes.append(f"已检查 {max_checks} 张，停止")
                return res
    return res


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

    def add(self, res, fallback_cover=False):
        self.counts["无图→作品封面" if fallback_cover else res.category] += 1

    def summary(self):
        total = sum(self.counts.values())
        ok = sum(n for k, n in self.counts.items() if k.startswith("有图"))
        parts = [f"{k} {n}" for k, n in self.counts.most_common()]
        return f"配图汇总：共 {total} 条，有图 {ok} 条 · " + " · ".join(parts)
