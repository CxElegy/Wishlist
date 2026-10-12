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
    image_via: str = ""  # 配图是出刊时补到的：从哪来（og:image、转载 xxx ……）；收集时自带的为空


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
    """RSS 条目里的配图：media:thumbnail / media:content / enclosure / Bing 的 News:Image / 正文第一张图。"""
    for tag in (f"{MEDIA}thumbnail", f"{MEDIA}content", "enclosure"):
        el = node.find(tag)
        if el is not None and el.get("url") and (tag != "enclosure" or el.get("type", "").startswith("image")):
            return html.unescape(el.get("url"))
    # Bing 新闻：<News:Image>（Bing 自己的缩略图，原站挡机器人也能用）。不带尺寸参数时常只有 100×100，
    # 按 <News:ImageMaxWidth>（原图宽度）要原比例的图，最宽 1200
    bing = {el.tag.split("}")[-1]: (el.text or "").strip() for el in node if el.tag.startswith("{")}
    if bing.get("Image"):
        width = min(int(bing["ImageMaxWidth"]) if bing.get("ImageMaxWidth", "").isdigit() else 1200, 1200)
        return re.sub(r"^http://", "https://", html.unescape(bing["Image"])) + f"&w={width}"
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', html.unescape(raw_html or ""))
    return html.unescape(m.group(1)) if m else ""


# 中国大陆网站：海外服务器（GitHub Actions）常被拦（腾讯云 EdgeOne 567、超时），防盗链也多。
# 新闻优先用国外（含港台、日韩、欧美）来源，只有大陆网站报道的才用它们。
DOMESTIC_HOSTS = (
    ".cn", "sohu.com", "sina.com", "qq.com", "gtimg.com", "163.com", "126.net", "ifeng.com", "17173.com",
    "17173cdn.com", "3dmgame.com", "gamersky.com", "mydrivers.com", "ithome.com", "yidianzixun.com",
    "toutiao.com", "baidu.com", "bdstatic.com", "bilibili.com", "hdslb.com", "zhihu.com", "zhimg.com",
    "weibo.com", "douban.com", "doubanio.com", "36kr.com", "huxiu.com", "eastmoney.com", "cnbeta.com",
    "gcores.com", "donews.com", "ali213.net", "hupu.com", "china.com", "thepaper.com", "xinhuanet.com",
    "people.com.cn", "chinanews.com", "bjnews.com", "163yun.com", "youku.com", "iqiyi.com",
)
# Google 新闻的跳转链接看不出网站：按媒体名判断
DOMESTIC_SOURCES = (
    "新浪", "搜狐", "腾讯", "网易", "凤凰", "17173", "3DM", "驱动之家", "快科技", "游民星空", "游侠网", "机核",
    "一点资讯", "cnBeta", "DoNews", "虎扑", "财联社", "光明日报", "智源社区", "中华网", "东方财富", "IT之家",
    "36氪", "虎嗅", "澎湃", "新华", "人民网", "央视", "中国新闻网", "哔哩哔哩", "知乎", "微博", "今日头条",
    "红板报", "体坛", "QQ News", "Gamereactor China", "豆瓣", "百度", "新京报", "界面新闻", "第一财经",
)


def is_domestic(url, source=""):
    """是不是中国大陆网站。看得出网址的看网址，Google 新闻跳转链接看媒体名。"""
    host = urllib.parse.urlparse(url or "").hostname or ""
    if host and host != "news.google.com":
        return any(host == h.lstrip(".") or host.endswith(h if h.startswith(".") else "." + h) for h in DOMESTIC_HOSTS)
    return any(s in (source or "") for s in DOMESTIC_SOURCES)


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


BING_TRIES = 3  # Bing 新闻 RSS 常随机返回空结果（同一个词连搜 10 次约 3 次是空的）：空的就再搜，最多这么多次


def bing_news(query):
    q = urllib.parse.quote(query)
    for attempt in range(BING_TRIES):
        entries = rss(f"https://www.bing.com/news/search?q={q}&format=rss", "Bing 新闻")
        if entries:
            break
        if attempt + 1 < BING_TRIES:
            time.sleep(1)
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


def reddit_links(data):
    """Reddit RSS 里每个帖子的外链（正文末尾的 [link]）：{帖子链接: 外链}。"""
    links = {}
    try:
        for it in ET.fromstring(data.strip()).iter(f"{ATOM}entry"):
            link = it.find(f"{ATOM}link")
            m = re.search(r'href="([^"]+)">\[link\]', html.unescape(it.findtext(f"{ATOM}content") or ""))
            if link is not None and m:
                links[link.get("href", "")] = html.unescape(m.group(1))
    except ET.ParseError:
        pass
    return links


def _reddit_entries(path, params, name):
    import images  # images 也 import 了 sources，放到函数里避免循环导入
    try:
        is_json, data = _reddit_get(path, params)
    except Exception as e:
        _warn(name, e)
        return []
    if not is_json:
        entries = rss_bytes(data, name)
        # 标了剧透 / NSFW 的帖子 RSS 里没有缩略图（网页上是「View spoiler」遮罩），改用帖子外链的预览图
        links = reddit_links(data)
        for e in entries:
            if not e.image and links.get(e.url):
                e.image = images.link_image(links[e.url]) or ""
        return entries
    entries = []
    for p in (c["data"] for c in json.loads(data)["data"]["children"]):
        # 剧透帖的 preview 原图本身没有打码（打码的是 variants.obfuscated），直接用
        preview = ((p.get("preview") or {}).get("images") or [{}])[0].get("source", {}).get("url", "")
        if not preview and p.get("url_overridden_by_dest"):
            preview = images.link_image(p["url_overridden_by_dest"]) or ""
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
