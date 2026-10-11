"""免费数据源抓取：全部走公开 RSS / API，不需要任何 Key，也不消耗 LLM token。

每个抓取函数返回 Entry 列表；出错时返回空列表并打印警告，不影响其它来源。
"""

import datetime as dt
import email.utils
import html
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

USER_AGENT = "Mozilla/5.0 (wishlist-digest; +https://github.com/CxElegy/Wishlist)"
TIMEOUT = 20
ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"


@dataclass
class Entry:
    title: str
    url: str
    published: dt.datetime | None
    source: str
    summary: str = ""
    image: str = ""


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _clean(text, limit=300):
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _parse_date(text):
    if not text:
        return None
    try:
        d = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _image(node, raw_html):
    """RSS 条目里的配图：media:thumbnail / media:content / enclosure / 正文第一张图。"""
    for tag in (f"{MEDIA}thumbnail", f"{MEDIA}content", "enclosure"):
        el = node.find(tag)
        if el is not None and el.get("url") and (tag != "enclosure" or el.get("type", "").startswith("image")):
            return html.unescape(el.get("url"))
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', html.unescape(raw_html or ""))
    return html.unescape(m.group(1)) if m else ""


def _warn(name, err):
    print(f"  [警告] {name} 抓取失败：{err}", file=sys.stderr)


def rss(url, source=None):
    """抓取并解析 RSS 2.0 / Atom。"""
    try:
        data = _get(url)
    except Exception as e:  # 网络错误跳过，不影响其它来源
        _warn(source or url, e)
        return []
    return rss_bytes(data, source or url)


def rss_bytes(data, source):
    data = data.strip()
    if not data or data[:15].lower().startswith(b"<!doctype html"):
        return []  # 没有结果时 Bing 会返回空内容或 HTML 页面
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        _warn(source, e)
        return []

    entries = []
    for it in root.iter("item"):  # RSS 2.0
        # Google 用 <source>，Bing 用带命名空间的 <News:Source>
        src = it.find("source")
        if src is None:
            src = next((c for c in it if c.tag.endswith("}Source")), None)
        entries.append(Entry(
            title=_clean(it.findtext("title"), 200),
            url=(it.findtext("link") or "").strip(),
            published=_parse_date(it.findtext("pubDate")),
            source=(src.text if src is not None and src.text else source),
            summary=_clean(it.findtext("description")),
            image=_image(it, it.findtext("description")),
        ))
    for it in root.iter(f"{ATOM}entry"):  # Atom
        link = it.find(f"{ATOM}link")
        entries.append(Entry(
            title=_clean(it.findtext(f"{ATOM}title"), 200),
            url=link.get("href", "") if link is not None else "",
            published=_parse_date(it.findtext(f"{ATOM}updated") or it.findtext(f"{ATOM}published")),
            source=source,
            summary=_clean(it.findtext(f"{ATOM}content") or it.findtext(f"{ATOM}summary")),
            image=_image(it, it.findtext(f"{ATOM}content") or it.findtext(f"{ATOM}summary")),
        ))
    return [e for e in entries if e.title and e.url]


def google_news(query, lookback_days, lang):
    hl, gl, ceid = lang
    q = urllib.parse.quote(f"{query} when:{lookback_days}d")
    entries = rss(f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}", "Google 新闻")
    for e in entries:
        # Google 新闻标题末尾带 " - 媒体名"，摘要只是重复标题，去掉
        if e.source != "Google 新闻" and e.title.endswith(f" - {e.source}"):
            e.title = e.title[: -len(e.source) - 3]
        e.summary = ""
    return entries


def bing_news(query):
    q = urllib.parse.quote(query)
    entries = rss(f"https://www.bing.com/news/search?q={q}&format=rss", "Bing 新闻")
    for e in entries:
        # Bing 链接是带随机跟踪参数的跳转地址，还原成原文地址
        real = urllib.parse.parse_qs(urllib.parse.urlparse(e.url).query).get("url")
        if real:
            e.url = real[0]
    return entries


_reddit_token = None


def _reddit_oauth():
    """用 Reddit 官方 API（免费的 script 应用）换取只读令牌；没配置返回 None。"""
    global _reddit_token
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return None
    if _reddit_token is None:
        req = urllib.request.Request(
            "https://www.reddit.com/api/v1/access_token",
            data=b"grant_type=client_credentials",
            headers={
                "User-Agent": USER_AGENT,
                "Authorization": "Basic " + base64.b64encode(f"{cid}:{secret}".encode()).decode(),
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            _reddit_token = json.loads(resp.read())["access_token"]
    return _reddit_token


def _reddit_get(path, params):
    """先用官方 API；没配置就用 RSS。Reddit 限流很严：每次请求间隔 2 秒，遇到 429 等 10 秒重试一次。"""
    try:
        token = _reddit_oauth()
    except Exception as e:
        _warn("Reddit 授权", e)
        token = None
    query = urllib.parse.urlencode(params)
    if token:
        url = f"https://oauth.reddit.com{path}?{query}"
        headers = {"User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"}
    else:
        url = f"https://www.reddit.com{path}.rss?{query}"
        headers = {"User-Agent": USER_AGENT}
    for attempt in range(2):
        time.sleep(2)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as resp:
                return token is not None, resp.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt:
                raise
            time.sleep(10)


def _reddit_entries(path, params, name):
    try:
        is_json, data = _reddit_get(path, params)
    except Exception as e:
        _warn(name, e)
        return []
    if not is_json:
        return rss_bytes(data, name)
    entries = []
    for p in (c["data"] for c in json.loads(data)["data"]["children"]):
        preview = ((p.get("preview") or {}).get("images") or [{}])[0].get("source", {}).get("url", "")
        entries.append(Entry(
            title=_clean(p["title"], 200),
            url="https://www.reddit.com" + p["permalink"],
            published=dt.datetime.fromtimestamp(p["created_utc"], dt.timezone.utc),
            source=f"r/{p['subreddit']}",
            summary=f"赞 {p['score']} · 评论 {p['num_comments']} · " + _clean(p.get("selftext"), 250),
            image=html.unescape(preview),
        ))
    return entries


def reddit_search(query, lookback_days=7):
    """全站搜索。摘要里带赞数和评论数（官方 API 才有），方便 AI 判断热度。"""
    period = "week" if lookback_days <= 7 else "month"
    return _reddit_entries("/search", {"q": query, "sort": "relevance", "t": period, "limit": 25}, "Reddit")


def reddit_sub(subreddit):
    """专门版块的最新帖子（版块本身就是相关的，不再按关键词过滤）。"""
    return _reddit_entries(f"/r/{subreddit}/new", {"limit": 25}, f"r/{subreddit}")


def steam_news(appid, count=10):
    """只取官方公告（补丁、活动），不含第三方媒体转载。"""
    url = (
        "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
        f"?appid={appid}&count={count}&feeds=steam_community_announcements"
    )
    try:
        items = json.loads(_get(url))["appnews"]["newsitems"]
    except Exception as e:
        _warn(f"Steam 新闻 {appid}", e)
        return []
    return [
        Entry(
            title=_clean(n["title"], 200),
            url=n["url"],
            published=dt.datetime.fromtimestamp(n["date"], dt.timezone.utc),
            source="Steam 官方公告",
            summary=_clean(n.get("contents"), 500),
        )
        for n in items
    ]


def steam_price(appid, country):
    """返回如 '¥ 198.00（-30%，原价 ¥ 283.00）' 的价格字符串；免费或取不到时返回 None。"""
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc={country}&filters=price_overview"
    try:
        data = json.loads(_get(url))[str(appid)]
    except Exception as e:
        _warn(f"Steam 价格 {appid}", e)
        return None
    price = (data.get("data") or {}).get("price_overview") if data.get("success") else None
    if not price:
        return None
    if price["discount_percent"]:
        return f"{price['final_formatted']}（-{price['discount_percent']}%，原价 {price['initial_formatted'] or price['initial'] / 100}）"
    return price["final_formatted"]


# ---------- 图片 ----------

def resolve_url(url):
    """把 Google 新闻的跳转链接还原成原文地址（Google 页面里的签名参数换取真实地址）；失败就原样返回。"""
    if "news.google.com" not in (url or ""):
        return url
    try:
        aid = urllib.parse.urlparse(url).path.split("/")[-1]
        page = _get(f"https://news.google.com/rss/articles/{aid}").decode("utf-8", "ignore")
        sg = re.search(r'data-n-a-sg="([^"]+)"', page).group(1)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page).group(1)
        inner = ["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None,
                                 None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                 aid, int(ts), sg]
        body = urllib.parse.urlencode({"f.req": json.dumps([[["Fbv4je", json.dumps(inner), None, "generic"]]])})
        req = urllib.request.Request(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body.encode(),
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            arr = json.loads(resp.read().decode().split("\n\n", 1)[1])
        real = json.loads(arr[0][2])[1]
        return real if real.startswith("http") else url
    except Exception:
        return url


def og_image(url):
    """读取网页的预览图（og:image / twitter:image），只读前 300KB。"""
    if not url or "news.google.com" in url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            head = resp.read(300_000).decode("utf-8", "ignore")
    except Exception:
        return None
    for pattern in (
        r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)(?::src)?["\'][^>]*content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)',
    ):
        m = re.search(pattern, head, re.I)
        if m:
            return urllib.parse.urljoin(url, html.unescape(m.group(1)))
    return None


IMG_SKIP = re.compile(r"logo|icon|avatar|banner|sprite|badge|button|noimage|emoji|/ads?/|\.svg|\.gif|data:", re.I)


def article_images(url, limit=8):
    """原文里的候选配图：og:image 排第一，然后是正文 <img>（优先 <article> 内的），去掉图标 / logo。"""
    if not url or "news.google.com" in url:
        return []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            page = resp.read(1_500_000).decode("utf-8", "ignore")
    except Exception:
        return []
    m = re.search(r"<article\b.*?</article>", page, re.I | re.S)
    body = m.group(0) if m else page
    found = []
    og = og_image(url)
    if og:
        found.append(og)
    for tag in re.findall(r"<img\b[^>]*>", body, re.I):
        src = re.search(r'(?:data-src|data-original|src)=["\']([^"\']+)', tag, re.I)
        if not src or IMG_SKIP.search(src.group(1)):
            continue
        u = urllib.parse.urljoin(url, html.unescape(src.group(1)))
        if u.startswith("http") and u not in found:
            found.append(u)
        if len(found) >= limit:
            break
    return found


def steam_header(appid):
    try:
        data = json.loads(_get(f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic"))
        return data[str(appid)]["data"]["header_image"]
    except Exception:
        return None


# ---------- 状态类数据源：返回 (显示文字, 稳定值, 封面图)，稳定值变了才提示“有变化” ----------

def _fmt_time(ts, tz):
    return dt.datetime.fromtimestamp(ts, tz).strftime("%m-%d %H:%M")


ANILIST_QUERY = """
query ($id: Int, $search: String, $type: MediaType) {
  Media(id: $id, search: $search, type: $type) {
    id type status episodes chapters siteUrl
    title { native romaji }
    coverImage { extraLarge }
    bannerImage
    startDate { year month day }
    nextAiringEpisode { episode airingAt }
    relations { edges { relationType node { id type } } }
  }
}"""
ANILIST_STATUS = {
    "FINISHED": "已完结", "RELEASING": "连载中", "NOT_YET_RELEASED": "未开播",
    "CANCELLED": "已取消", "HIATUS": "停更中",
}


def _anilist(variables):
    req = urllib.request.Request(
        "https://graphql.anilist.co",
        # 传 null 会让 AniList 返回 404，空值直接不传
        data=json.dumps({"query": ANILIST_QUERY, "variables": {k: v for k, v in variables.items() if v}}).encode(),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())["data"]["Media"]


def anilist_status(anilist_id, search, media_type, tz):
    """番剧 / 漫画状态。番剧会顺着“续作”关系找到最新一季，所以填第一季也行。"""
    try:
        media = _anilist({"id": anilist_id, "search": None if anilist_id else search, "type": media_type})
        for _ in range(10):  # 最多追 10 季
            sequel = next(
                (e["node"]["id"] for e in media["relations"]["edges"]
                 if e["relationType"] == "SEQUEL" and e["node"]["type"] == media_type),
                None,
            )
            if not sequel:
                break
            media = _anilist({"id": sequel, "type": media_type})
    except Exception as e:
        _warn(f"AniList {anilist_id or search}", e)
        return None

    title = media["title"]["native"] or media["title"]["romaji"]
    status = ANILIST_STATUS.get(media["status"], media["status"])
    parts = [f"[《{title}》]({media['siteUrl']})", status]
    nxt = media.get("nextAiringEpisode")
    if nxt:
        parts.append(f"第 {nxt['episode']} 集 {_fmt_time(nxt['airingAt'], tz)} 播出")
    elif media["status"] == "NOT_YET_RELEASED":
        d = media["startDate"]
        when = "-".join(str(x) for x in (d["year"], d["month"], d["day"]) if x)
        parts.append(f"预计 {when} 开播" if when else "开播日期未定")
    total = media.get("episodes") or media.get("chapters")
    if total:
        parts.append(f"共 {total} {'集' if media_type == 'ANIME' else '话'}")
    cover = media.get("bannerImage") or (media.get("coverImage") or {}).get("extraLarge")
    return " · ".join(parts), f"{media['id']}|{media['status']}", cover


TMDB_STATUS = {
    "Returning Series": "连载中", "Ended": "已完结", "Canceled": "已取消",
    "In Production": "制作中", "Planned": "计划中", "Pilot": "试播",
    "Released": "已上映", "Post Production": "后期制作", "Rumored": "传闻",
}


def tmdb_status(ref, api_key, language="zh-CN"):
    """ref 形如 'tv/1399' 或 'movie/693134'（就是 themoviedb.org 网址里的那段）。"""
    kind, _, tmdb_id = ref.partition("/")
    url = f"https://api.themoviedb.org/3/{kind}/{tmdb_id}?language={language}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if api_key.startswith("eyJ"):  # v4 读访问令牌
        headers["Authorization"] = f"Bearer {api_key}"
    else:  # v3 API Key
        url += f"&api_key={api_key}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            d = json.loads(resp.read())
    except Exception as e:
        _warn(f"TMDB {ref}", e)
        return None

    status = TMDB_STATUS.get(d.get("status"), d.get("status"))
    link = f"https://www.themoviedb.org/{ref}"
    art = d.get("backdrop_path") or d.get("poster_path")
    cover = f"https://image.tmdb.org/t/p/w780{art}" if art else None
    if kind == "movie":
        date = d.get("release_date") or "待定"
        return f"[《{d.get('title')}》]({link}) · {status} · 上映日期 {date}", f"{d.get('status')}|{date}", cover

    parts = [f"[《{d.get('name')}》]({link})", status, f"共 {d.get('number_of_seasons')} 季"]
    nxt = d.get("next_episode_to_air")
    if nxt:
        parts.append(f"下一集 S{nxt['season_number']}E{nxt['episode_number']} {nxt.get('air_date') or '日期未定'}")
    elif d.get("last_episode_to_air"):
        last = d["last_episode_to_air"]
        parts.append(f"最近一集 S{last['season_number']}E{last['episode_number']} {last.get('air_date')}")
    nxt_season = nxt["season_number"] if nxt else None
    return " · ".join(parts), f"{d.get('status')}|{d.get('number_of_seasons')}|{nxt_season}", cover
