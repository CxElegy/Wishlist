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
        data = _get(url).strip()
        if not data or data[:15].lower().startswith(b"<!doctype html"):
            return []  # 没有结果时 Bing 会返回空内容或 HTML 页面
        root = ET.fromstring(data)
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


# ---------- 状态类数据源：返回 (显示文字, 稳定值)，稳定值变了才提示“有变化” ----------

def _fmt_time(ts, tz):
    return dt.datetime.fromtimestamp(ts, tz).strftime("%m-%d %H:%M")


ANILIST_QUERY = """
query ($id: Int, $search: String, $type: MediaType) {
  Media(id: $id, search: $search, type: $type) {
    id type status episodes chapters siteUrl
    title { native romaji }
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
    return " · ".join(parts), f"{media['id']}|{media['status']}"


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
    if kind == "movie":
        date = d.get("release_date") or "待定"
        return f"[《{d.get('title')}》]({link}) · {status} · 上映日期 {date}", f"{d.get('status')}|{date}"

    parts = [f"[《{d.get('name')}》]({link})", status, f"共 {d.get('number_of_seasons')} 季"]
    nxt = d.get("next_episode_to_air")
    if nxt:
        parts.append(f"下一集 S{nxt['season_number']}E{nxt['episode_number']} {nxt.get('air_date') or '日期未定'}")
    elif d.get("last_episode_to_air"):
        last = d["last_episode_to_air"]
        parts.append(f"最近一集 S{last['season_number']}E{last['episode_number']} {last.get('air_date')}")
    nxt_season = nxt["season_number"] if nxt else None
    return " · ".join(parts), f"{d.get('status')}|{d.get('number_of_seasons')}|{nxt_season}"
