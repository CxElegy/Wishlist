"""免费数据源抓取：全部走公开 RSS / API，不需要任何 Key，也不消耗 LLM token。

每个抓取函数返回 Entry 列表；出错时返回空列表并打印警告，不影响其它来源。
"""

import datetime as dt
import email.utils
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

USER_AGENT = "Mozilla/5.0 (wishlist-digest; +https://github.com/CxElegy/Wishlist)"
TIMEOUT = 20
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass
class Entry:
    title: str
    url: str
    published: dt.datetime | None
    source: str
    summary: str = ""


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


def _warn(name, err):
    print(f"  [警告] {name} 抓取失败：{err}", file=sys.stderr)


def rss(url, source=None):
    """通用 RSS 2.0 / Atom 解析。"""
    try:
        data = _get(url)
        if not data.strip():
            return []  # 没有结果时 Bing 会返回空内容
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            # Bing 偶尔把未转义的查询词写进 xmlns 属性，去掉后重试
            root = ET.fromstring(re.sub(rb'\sxmlns:\w+="[^"]*"', b"", data, count=1))
    except Exception as e:  # 网络或格式错误都跳过，不影响其它来源
        _warn(source or url, e)
        return []

    entries = []
    for it in root.iter("item"):  # RSS 2.0
        src = it.find("source")
        entries.append(Entry(
            title=_clean(it.findtext("title"), 200),
            url=(it.findtext("link") or "").strip(),
            published=_parse_date(it.findtext("pubDate")),
            source=(src.text if src is not None and src.text else source or url),
            summary=_clean(it.findtext("description")),
        ))
    for it in root.iter(f"{ATOM}entry"):  # Atom
        link = it.find(f"{ATOM}link")
        entries.append(Entry(
            title=_clean(it.findtext(f"{ATOM}title"), 200),
            url=link.get("href", "") if link is not None else "",
            published=_parse_date(it.findtext(f"{ATOM}updated") or it.findtext(f"{ATOM}published")),
            source=source or url,
            summary=_clean(it.findtext(f"{ATOM}content") or it.findtext(f"{ATOM}summary")),
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


def reddit(subreddit, query):
    q = urllib.parse.quote(query)
    return rss(
        f"https://www.reddit.com/r/{subreddit}/search.rss?q={q}&restrict_sr=1&sort=new",
        f"r/{subreddit}",
    )


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
