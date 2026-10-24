"""关注清单定期整理，分两步（参考 agents-radar）：

ingest   收集：按 items.yaml 从免费 RSS / API 抓取，按时间窗口、关键词过滤，与往期去重，
         连同状态变化、封面图一起存成 inbox/YYYY-MM-DD.json。不做任何编排，不花钱。
publish  出刊：读 inbox，把条目编排成报道，配图、配色，输出 reports/YYYY-MM-DD.json
         和 docs/index.html（简报网页，新一期在最上面）。编排方式按优先级：
           1. inbox/YYYY-MM-DD.edit.json（人工或 Claude 写的编排，格式见 load_edits）
           2. Claude API（settings.summarize: true 且有凭据）
           3. 关键词规则（priority_keywords），完全免费

用法：
    python scripts/digest.py              # ingest + publish
    python scripts/digest.py ingest       # 只收集
    python scripts/digest.py publish      # 只出刊（用最新一份 inbox）
    python scripts/digest.py render       # 只用已有数据重新生成网页（改了版式时用）
    python scripts/digest.py --dry-run    # 只抓取并打印，不写文件
"""

import argparse
import datetime as dt
import functools
import hashlib
import json
import os
import pathlib
import random
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
import unicodedata
import zoneinfo

import yaml

import heat
import images
import intel
import lang
import render
import sitedir
import sources
import taxonomy
import theme

ROOT = pathlib.Path(__file__).resolve().parent.parent
ITEMS_FILE = ROOT / "items.yaml"
WISHLIST_FILE = ROOT / "wishlist.yaml"
RECOMMEND_FILE = ROOT / "state" / "recommend.json"
DISCOVER_FILE = ROOT / "state" / "discover.json"
FEEDBACK_FILE = ROOT / "state" / "feedback.json"
NEWS_SYNC_FILE = ROOT / "state" / "db_news.json"
STORIES_SYNC_FILE = ROOT / "state" / "db_stories.json"
PRICES_SYNC_FILE = ROOT / "state" / "db_prices.json"
REPORTS_DIR = ROOT / "reports"
STATE_DIR = ROOT / "state"
FACTS_FILE = STATE_DIR / "facts.json"
THEMES_FILE = STATE_DIR / "themes.json"
SIZES_FILE = STATE_DIR / "sizes.json"
NAV_SCHEMES_FILE = STATE_DIR / "nav_schemes.json"   # 板块ごとに選んだ小分類の分け方（Supabase の nav_schemes 表の写し）
HEAT_FILE = STATE_DIR / "heat_signals.json"  # 話題度用的外部数据（维基浏览量、Steam 在线、AniList / TMDB 人气），见 heat.py
SIZES_PUSHED_FILE = STATE_DIR / "sizes_pushed.json"   # items.yaml 里的 size 上次同步进数据库时是什么
EMBLEM_REJECTS_FILE = STATE_DIR / "emblem_rejects.json"   # 管理ページで「違う」と外した小元素と理由（今後の規則を直す手がかり、emblem_rules.REJECT_REASONS）
INBOX_DIR = ROOT / "inbox"
DOCS_DIR = sitedir.SITE_DIR   # 公開ページ（docs/home/ = 店長のページ，test2 は凍結）
ISSUES_ON_PAGE = 3650  # 网页汇总所有期：消息永远保留，一周前的收进折叠区

NEWS_LANGS = {
    "zh-CN": ("zh-CN", "CN", "CN:zh-Hans"),
    "zh-TW": ("zh-TW", "TW", "TW:zh-Hant"),
    "en-US": ("en-US", "US", "US:en"),
    "ja-JP": ("ja", "JP", "JP:ja"),
    "ko-KR": ("ko", "KR", "KR:ko"),
}

# 不同类型关注项交给 LLM 的整理要求
ITEM_TYPES = {
    "product": "这是一个具体商品。常见重点：价格与促销、库存、评测、新版本/固件。",
    "category": "这是一整类产品，不要只盯一个型号。盘点新品、热门型号和明显降价。",
    "game": "这是一款游戏。常见重点：测试/上线日期、预约、版本更新、活动、DLC、折扣、官方公告。",
    "anime": "这是一部动画或漫画。常见重点：新季/续作/剧场版官宣、定档与播出时间、PV、制作阵容。",
    "show": "这是一部电影或剧集。常见重点：定档、上映/播出时间、预告片、续集或新季、国内上线平台。",
    "event": "这是一位艺人的演出。常见重点：巡演/演唱会官宣、追加场次、日程与场馆、门票抽选与发售、粉丝见面会。",
}

SYSTEM_PROMPT = """你是报纸编辑，把抓取到的新闻条目编成一个关注项的简报板块。只依据提供的条目，不编造条目之外的信息。

编辑规则：
- 合并重复报道，丢掉无关条目、广告、水贴。最多 6 条报道，没有值得报的就返回空列表。
- 按“对读者最关心的问题有多重要”排序，第一条是头条。
- weight：直接回答读者最关心的问题、且是新的确切信息（例如公布了测试/上线日期、开放预约）用 "hero"；
  头条用 "lead"；其余 "normal"。hero 宁缺毋滥。
- headline：原文标题，不翻译：用依据条目里最权威那条的标题，去掉媒体名和宣传噪音，太长就在原来的语言里删减。
- highlight：headline 里最关键的几个字（日期、数字、结论），必须原样出现在 headline 中；没有就留空。
- blurb：一句话补充，用原文的语言（照摘要精简），只给头条和 hero 写，其余留空。
- refs：这条报道依据的条目编号。
- Reddit 帖子是玩家讨论（摘要里有赞数、评论数），热度高时可以归纳成一条“社区热议”报道。
- 来源优先用国外媒体（含港台、日韩、欧美）：同一件事国外媒体也报了，refs 第一个放国外媒体；
  标了（大陆网站）的条目只在这件事只有大陆网站报道时才用。
- 不翻译：标题和摘要都保持原文的语言。
- 语言：读者的主言語是 {primary}，副言語依次是 {secondary}。同一件事有几种语言的报道时只写一条：
  refs 第一个放主言語的条目，headline 用它的原标题；没有主言語的就按副言語的顺序挑。其他语言的条目不单独成条。"""

STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "highlight": {"type": "string"},
                    "blurb": {"type": "string"},
                    "weight": {"type": "string", "enum": ["hero", "lead", "normal"]},
                    "refs": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["headline", "highlight", "blurb", "weight", "refs"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["stories"],
    "additionalProperties": False,
}


# ---------- 状态 ----------

def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# ---------- 抓取 ----------

def collect(item, settings):
    lookback = settings.get("lookback_days", 7)
    langs = item.get("news_langs") or settings.get("news_langs") or ["zh-TW"]
    # 中文新闻默认只要港台媒体（zh-TW）：大陆网站常拦海外服务器、图片防盗链，链接和配图容易失效。
    # 写了 zh-CN 的关注项才收大陆网站（Google 简体版，以及 Bing 搜回来的大陆网站）
    domestic_ok = "zh-CN" in langs
    keywords = item.get("keywords") or [item["name"]]
    use = item.get("use") or ["google", "bing", "reddit"]

    entries = []
    for kw in keywords:
        news = []
        if "google" in use:
            for lang in langs:
                news += sources.google_news(kw, lookback, NEWS_LANGS[lang])
        if "bing" in use:
            news += sources.bing_news(kw)
        entries += [e for e in news if domestic_ok or not sources.is_domestic(e.url, e.source)]
    for sub in item.get("subreddits") or []:
        entries += sources.reddit_sub(sub)
    if "reddit" in use:
        # 全站搜一次就够，用第一个关键词（通常是英文正式名）
        entries += sources.reddit_search(f'"{keywords[0]}"', lookback)
    for url in item.get("feeds") or []:
        entries += sources.rss(url)
    if item.get("steam_appid"):
        entries += sources.steam_news(item["steam_appid"])
    # 情報源を広げる（2026-10-22）：ニュースは GDELT（各国の新聞・専門サイト）も、SNS は Bluesky・Mastodon も、公式は YouTube のチャンネルも。
    # use の考え方はそのまま：google を使う関注項は GDELT も（ニュースの検索）、reddit を使う関注項は Bluesky・Mastodon も（SNS の全体検索。
    # 名前が普通の言葉の作品は use: [google, bing] にしてあるので SNS は探さない）。YouTube は公式チャンネルなので use に関係なく
    if "google" in use and item.get("gdelt", True):   # お客さまの版面（userfeed.py）は gdelt: false：5 秒に 1 回の順番を店長の収集に残す
        for kw in keywords[:GDELT_KEYWORDS]:
            entries += [e for e in sources.gdelt(kw, lookback, langs) if domestic_ok or not sources.is_domestic(e.url, e.source)]
    if "reddit" in use:
        entries += sources.bluesky(keywords[0], lookback, langs)
        entries += sources.mastodon_tag(keywords[0], langs)
    for ch in youtube_channels(item):
        entries += sources.youtube_channel(ch)
    # 地域ごとの情報員（intel/*.yaml）：関注項の言語・板块で担当が決まり、その地域の専門サイトの RSS を読む（同じフィードはこの回 1 回だけ取る）
    entries += intel.entries_for(item, settings)
    return entries


GDELT_KEYWORDS = 2   # GDELT は 5 秒に 1 回まで：関注項ごとに最初の 2 語（25 関注項で約 5 分。AI なし・時間は使ってよい）
YOUTUBE_FILE = STATE_DIR / "youtube_channels.json"   # 関注項 → 公式 YouTube チャンネル（Wikidata P2397 から規則で）。30 日ごとに見直す
YOUTUBE_RECHECK_DAYS = 30
_yt_lock = __import__("threading").Lock()


def youtube_channels(item):
    """関注項の公式 YouTube チャンネル：items.yaml の youtube があればそれ、なければ wiki → Wikidata P2397（state/youtube_channels.json に覚える）。"""
    if item.get("youtube"):
        return [c for c in item["youtube"] if isinstance(c, str)]
    if not item.get("wiki"):
        return []
    now = dt.datetime.now(dt.timezone.utc)
    with _yt_lock:
        cache = load_json(YOUTUBE_FILE) or {}
        got = cache.get(item["name"])
        try:
            fresh = got and (now - dt.datetime.fromisoformat(got["at"])).days < YOUTUBE_RECHECK_DAYS and got.get("wiki") == item["wiki"]
        except (KeyError, ValueError):
            fresh = False
        if fresh:
            return got.get("ids") or []
        ids = sources.youtube_channels_from_wiki(item["wiki"])
        cache[item["name"]] = {"ids": ids, "at": now.isoformat(timespec="seconds"), "wiki": item["wiki"]}
        save_json(YOUTUBE_FILE, cache)
        return ids


TRUSTED_SOURCES = {"Steam 官方公告"}


def title_key(title):
    return "t:" + re.sub(r"\W+", "", title.lower())


def _norm(text):
    return re.sub(r"\s+", "", text.lower())


# 图片画廊、附图页这类“同一篇文章的分页”，标题只差编号，直接丢掉
JUNK_PATTERNS = [r"^画像ギャラリー", r"\d+枚目の写真", r"写真・画像$", r"^图集", r"^사진\s*\d"]
# 垃圾站（被黑的网站批量生成的色情 / 盗版「在线看」页面）：标题里塞热门作品名骗搜索，会命中 match。
# 例：「绝区零艾莲被爆❌…在线高清完整-…免费全集-爱看高清网」（2026-10-16〜17，来源挂着「胡润百富」）
SPAM_PATTERNS = [
    r"[一-鿿]\s*❌\s*[一-鿿]",           # 汉字中间夹 ❌ 打码（× 是联名，不算）
    r"在线看|在线观看|在线播放|在线高清|高清完整|超清版|超清在线|免费全集|全集版|无删减|未删减",
    r"(爱看|高清|影视|电影|安卓|下载)网$",                 # 「-爱看高清网」「-2265安卓网」这类站名结尾
    r"涩涩|黄漫",
    # 标题末尾拼着「热门关键词 + 10 位随机码」：被黑的网站（media.unisba.ac.id「Unisba Media」，2026-10-19 查到 47 条）批量生成的页面，
    # 前半是随便一条新闻的标题，后半塞作品名骗搜索，页面本身是 404。随机码 = 10 位字母数字、有小写、且大写＋数字至少 3 个
    r"\s\((?=[A-Za-z0-9]*[a-z])(?=(?:[a-z]*[A-Z0-9]){3})[A-Za-z0-9]{10}\)\s*$",
]


# 正规网站的网址里被塞进广告的（站内搜索・追踪参数被拿去刷 SEO）：标题是真的旧文章，网址的参数里是「伴游…添加微信」。
# 例：finance.sina.cn/…/detail-xxx.d.html?oid=苏州姑苏区伴游模特（金牌经纪）添加快乐微信(88②③6881)…（2026-10-16，6 月的旧文当新闻）
SPAM_URL = re.compile(r"微信|威信|薇信|加V|伴游|外围|上门|模特.{0,6}经纪|[①-⑳]{2}")


# 乗っ取られて垃圾页を量産しているサイト（この網域と下位網域の記事は丸ごと捨てる）。AI 編集は標題の末尾の随機コードを削って報道にしてしまうので、
# 標題の規則だけでは抜ける：リンクの網域でも見る
SPAM_HOSTS = ("unisba.ac.id",)   # Unisba Media（2026-10 被黑、標題 = 別の記事 + 作品名 + 10 位随機コード、ページは 404）


def host_in(url, hosts):
    """url の網域が hosts のどれか、またはその下位網域か（www.gamewith.jp も gamewith.jp に当たる。notgamewith.jp は当たらない）。"""
    host = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    return bool(host) and any(host == h or host.endswith("." + h) for h in (x.lower() for x in hosts))


def host_rule_hit(rules, title, urls):
    """exclude_hosts のどれかに当たるか。文字列 = その網域（と下位網域）まるごと。
    {host, title} = その網域で、標題が title（正規表現）に当たるものだけ：攻略 wiki の網域（GameWith）は編集部のニュースも出すので、攻略頁の標題の形だけ落とす。
    収集の時点のリンクは Google の跳转で網址の道（path）がわからないので、道ではなく標題で分ける。"""
    for r in rules or []:
        host, pat = (r.get("host"), r.get("title")) if isinstance(r, dict) else (r, None)
        if host and any(host_in(u, (host,)) for u in urls if u) and (not pat or re.search(pat, title or "")):
            return True
    return False


def is_spam(title, url=""):
    if url:
        if host_in(url, SPAM_HOSTS):
            return True
        if SPAM_URL.search(urllib.parse.unquote(urllib.parse.urlsplit(url).query)):
            return True
    return any(re.search(p, title) for p in SPAM_PATTERNS)
# 标题去掉作品名后，字符二元组重合度超过这个值视为同一篇（转载、截断标题、改了后缀的）。
# 用实际标题校准过：真重复 ≥ 0.8，不同文章 ≤ 0.63
SIMILAR = 0.75


def _similar(a, b):
    return len(a & b) / max(1, min(len(a), len(b))) > SIMILAR


def _title_grams(title, names):
    """去掉作品名再取二元组，避免“都含游戏名”被误判为同一篇。"""
    t = re.sub(r"\W+", "", title.rstrip(". …").lower())
    for n in names:
        t = t.replace(re.sub(r"\W+", "", n.lower()), "")
    return {t[i:i + 2] for i in range(len(t) - 1)}


HISTORY_DAYS = 14  # 去重看最近几天的 inbox（收集窗口是 7 天，留一倍余量）


def seen_from_inbox(days=HISTORY_DAYS):
    """报道过的链接和标题，直接从最近几天的 inbox 里取。
    不再单独存 seen.json：那个文件每次运行都整份重写，git 历史会越积越大。"""
    seen = set()
    for path in sorted(INBOX_DIR.glob("????-??-??.json"))[-days:]:
        for item in load_json(path).get("items", []):
            for e in item["entries"]:
                seen.add(e["url"])
                seen.add(title_key(e["title"]))
    return seen


def recent_titles(days=HISTORY_DAYS):
    """最近几天 inbox 里已经收过的标题，按关注项分组，用来做跨批次的相似去重。"""
    titles = {}
    for path in sorted(INBOX_DIR.glob("????-??-??.json"))[-days:]:
        for item in load_json(path).get("items", []):
            titles.setdefault(item["name"], []).extend(e["title"] for e in item["entries"])
    return titles


def has_history(name):
    """这个关注项以前收到过条目吗（翻全部 inbox）。没有就是第一次收集，要多往前看一些。"""
    for path in INBOX_DIR.glob("????-??-??.json"):
        for item in load_json(path).get("items", []):
            if item["name"] == name and item["entries"]:
                return True
    return False


def match_hit(item, e):
    """这条消息靠哪个匹配词算进这个关注项（返回那个词）；不算就返回 None。
    新闻搜索会混入不相关结果：标题或摘要里必须出现某个匹配词（忽略大小写和空格）。
    「re:」开头的是正则，区分大小写、照原文匹配：名字是常用词（FROM、MCU）或泛词要和主题词同时出现时用它。
    写法规则见 docs/rules/match.md「匹配词（match）的写法」；python scripts/digest.py audit-match 可以检查。"""
    if e.source in TRUSTED_SOURCES or e.source in {f"r/{s}" for s in item.get("subreddits") or []}:
        return "(可信来源)"
    # Reddit 全站搜索来的帖子：正文是闲聊，「from Season 5」这种说法到处都是，匹配词必须出现在标题里
    text = e.title if e.source in ("Reddit", "Bluesky", "Mastodon") else e.title + e.summary   # SNS は本文が雑談：標題（投稿の文）にあること
    for w in item.get("match") or item.get("keywords") or [item["name"]]:
        if w.startswith("re:") and re.search(w[3:], text) or not w.startswith("re:") and _norm(w) in _norm(text):
            return w
    return None


def source_in(source, names):
    """出典名の除外（exclude_sources）は前方一致：「YouTube」で「YouTube on MSN」も外れる。
    続く 1 字が ASCII の英数字のときは別の名前（「note」で「Notebookcheck」「notes」は外さない）。
    漢字・かな・記号が続くのは同じ媒体（「YouTubeチャンネル」「note株式会社」「胡润百富网」も外す）。公式チャンネル（sources.YT_OFFICIAL）は drop_reason で別扱い。"""
    def other(c):
        return c.isascii() and c.isalnum()
    return any(source == s or source.startswith(s) and not other(source[len(s)]) for s in names if s)


def drop_reason(e, item, settings):
    """この記事を収めない理由（出典名・網域・垃圾・除外語・匹配词）。収めるなら None。
    収集（filter_entries）と audit-match が同じ規則を使う。網域は e.link（還元した原文）・e.url・e.site（Google ニュースの媒体の網站）で見る。"""
    if not e.source.startswith(sources.YT_OFFICIAL) and \
            source_in(e.source, [*settings.get("exclude_sources", ["YouTube"]), *(item.get("exclude_sources") or [])]):
        return "exclude_sources"   # 公式チャンネル（YouTube · ILLIT）は関注項が自分で選んだ情報源なので「YouTube」の除外に入れない
    hosts = [*(settings.get("exclude_hosts") or []), *(item.get("exclude_hosts") or [])]
    if host_rule_hit(hosts, e.title, (e.link, e.url, getattr(e, "site", ""))):
        return "exclude_hosts"
    if any(re.search(p, e.title) for p in JUNK_PATTERNS) or is_spam(e.title, e.link or e.url):
        return "垃圾"
    if any(w.lower() in e.title.lower() for w in item.get("exclude") or []):
        return "exclude"
    if match_hit(item, e) is None:
        return "match"
    return None


def _google_jump(url):
    return host_in(url, ("news.google.com",))


def audit_match(days=4, only=None):
    """检查误收：最近几天 inbox 里每个关注项的条目按「靠哪个匹配词进来的」分组列出来，
    并标出按现在的规则已经不会再收的（✗，后面写理由：match / exclude / 垃圾 / exclude_sources / exclude_hosts，和收集的 drop_reason 同一个）。
    加关注项、改匹配词之后跑一次，看有没有不相关的混进来。"""
    settings, items = load_config()
    paths = sorted(p for p in INBOX_DIR.glob("????-??-??.json"))[-days:]
    # Google の跳转で link・site がない記事（site を inbox に書く前に集めたもの）は網域を判定できない。
    # 同じ出典名の記事で網域がわかったものから「除外の網域の媒体」を推して、見えない分の件数を最後に出す
    hosts = [*(settings.get("exclude_hosts") or []), *(h for i in items for h in i.get("exclude_hosts") or [])]
    rule_hosts = [r.get("host") if isinstance(r, dict) else r for r in hosts]
    host_src = {}   # 出典名 → 網域がわかった記事の網域（除外の網域のもの）
    for path in paths:
        for raw in load_json(path).get("items", []):
            for d in raw["entries"]:
                h = next((h for u in (d.get("link"), d.get("site"), d.get("url")) for h in rule_hosts if h and host_in(u, (h,))), None)
                if h:
                    host_src.setdefault(d["source"], h)
    blind, blind_ex = 0, {}
    for item in items:
        if only and item["name"] not in only:
            continue
        groups, gone_n = {}, 0
        for path in paths:
            for raw in load_json(path).get("items", []):
                if raw["name"] != item["name"]:
                    continue
                for d in raw["entries"]:
                    e = entry_from_dict(d)
                    hit = match_hit(item, e)
                    why = drop_reason(e, item, settings)
                    gone_n += bool(why)
                    if not why and not e.link and not e.site and _google_jump(e.url):
                        blind += 1
                        if e.source in host_src and host_rule_hit(hosts, e.title, (f"https://{host_src[e.source]}/",)):
                            blind_ex[e.source] = blind_ex.get(e.source, 0) + 1   # 標題の形の規則（攻略頁だけ）も当てる
                    groups.setdefault(hit or "(不再匹配)", []).append(
                        (f"✗ [{why}] " if why else "  ") + e.title[:90])
        print(f"===== {item['name']}（{sum(len(v) for v in groups.values())} 条、✗ {gone_n}）")
        for w, titles in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(f"  [{w}] {len(titles)}")
            for t in titles[:8]:
                print(f"     {t}")
    if blind:
        ex = "、".join(f"{s} {n}" for s, n in sorted(blind_ex.items(), key=lambda kv: -kv[1]))
        print(f"\n網域を判定できない（Google の跳转で link・site がない）：{blind} 件"
              + (f"。うち出典名が除外の網域の媒体と同じもの {sum(blind_ex.values())} 件（{ex}）は、収集の時点なら exclude_hosts で外れる"
                 if blind_ex else ""))


def filter_entries(entries, item, settings, seen, now, known=()):
    names = [item["name"], *(item.get("keywords") or []), *(item.get("match") or [])]
    since = now - dt.timedelta(days=settings.get("lookback_days", 7))
    # 同一篇文章常同时出现在 Google 和 Bing：每个标题只留一条，优先国外网站（大陆网站常拦海外服务器、
    # 图片防盗链），其次能直接打开原文的（Google 是跳转页，拿不到配图）
    def rank(e):
        return (not sources.is_domestic(e.url, e.source), "news.google.com" not in e.url)

    best = {}
    for e in entries:
        key = title_key(e.title)
        if key not in best or rank(e) > rank(best[key]):
            best[key] = e
    out, grams = [], [_title_grams(t, names) for t in known]
    # 标题相近的转载只留先看到的那条：国外网站先看，同一件事有国外报道就不收大陆网站的；最后再按时间排回来
    for e in sorted(best.values(), key=lambda e: (sources.is_domestic(e.url, e.source),
                                                  -(e.published or now).timestamp())):
        key = title_key(e.title)
        if e.url in seen or key in seen or drop_reason(e, item, settings):
            continue   # 出典名（前方一致）・網域・垃圾・除外語・匹配词（audit-match と同じ drop_reason）
        g = _title_grams(e.title, names)
        if any(_similar(g, h) for h in grams):
            continue
        if e.published and e.published < since:
            continue
        grams.append(g)
        out.append(e)
    # Reddit 帖子多且杂（同人图、闲聊），单独限额，不和媒体报道抢名额
    out.sort(key=lambda e: e.published or now, reverse=True)
    news = [e for e in out if not e.source.startswith("r/") and e.source != "Reddit"]
    posts = [e for e in out if e not in news]
    cap = item.get("max_entries") or settings.get("max_entries_per_item", 30)
    return news[:cap] + posts[: settings.get("max_reddit_per_item", 10)]


def display_tz(settings):
    """网页上显示时间用的时区（display_timezone）。没写就用出刊的 timezone。"""
    return zoneinfo.ZoneInfo(settings.get("display_timezone") or settings.get("timezone", "Asia/Shanghai"))


def status_facts(item, settings, facts):
    """Steam 价格、番剧/剧集播出状态等“当前状态”。返回 (状态列表, 封面图)。"""
    tz = display_tz(settings)
    checks = []
    if item.get("steam_appid"):
        appid = item["steam_appid"]
        def steam():
            price = sources.steam_price(appid, settings.get("steam_country", "cn"))
            return (price, price, None) if price else None
        checks.append(("Steam 价格", f"steam:{appid}", steam))
    if item["type"] == "anime" and (item.get("anilist_id") or item.get("keywords")):
        media_type = item.get("anilist_type", "ANIME")
        checks.append(("播出状态" if media_type == "ANIME" else "连载状态",
                       f"anilist:{item.get('anilist_id') or item['keywords'][0]}",
                       lambda: sources.anilist_status(item.get("anilist_id"), item["keywords"][0], media_type, tz)))
    if item.get("tmdb"):
        key = os.environ.get("TMDB_API_KEY")
        if key:
            checks.append(("播出状态", f"tmdb:{item['tmdb']}", lambda: sources.tmdb_status(item["tmdb"], key)))
        else:
            print("  [提示] 未设置 TMDB_API_KEY，跳过剧集/电影状态", file=sys.stderr)

    out, cover = [], None
    for label, key, fetch in checks:
        result = fetch()
        if not result:
            continue
        text, stable, img = result
        cover = cover or img
        old = facts.get(key)
        facts[key] = {"text": text, "stable": stable, "item": item["name"], "label": label}
        out.append({"label": label, "text": text, "changed": bool(old and old["stable"] != stable)})
    return out, cover


def find_cover(item, status_cover):
    if item.get("cover"):
        return item["cover"]
    if status_cover:
        return status_cover
    if item.get("steam_appid"):
        img = sources.steam_header(item["steam_appid"])
        if img:
            return img
    if item.get("site"):
        return images.og_image(item["site"])
    return None


# ---------- LLM 编辑 ----------

def _github_oidc_token():
    """向 GitHub Actions 现场要一个身份令牌。令牌约 5 分钟过期且只能换一次，所以每次换取都重新要。"""
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&audience=https://api.anthropic.com"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["value"]


def make_client():
    """凭据优先级：API Key > GitHub Actions 的 Workload Identity Federation > SDK 自己能找到的（环境变量 / 本机登录）。
    都没有就返回 None，简报直接用原标题。"""
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        # 空的 ANTHROPIC_API_KEY 也会抢占凭据（会用空 Key 去认证），必须删掉
        os.environ.pop("ANTHROPIC_API_KEY", None)
    else:
        return anthropic.Anthropic()

    rule = os.environ.get("ANTHROPIC_FEDERATION_RULE_ID")
    if rule and os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"):
        print("使用 Workload Identity Federation（GitHub Actions）", file=sys.stderr)
        return anthropic.Anthropic(credentials=anthropic.WorkloadIdentityCredentials(
            identity_token_provider=_github_oidc_token,
            federation_rule_id=rule,
            organization_id=os.environ["ANTHROPIC_ORGANIZATION_ID"],
            service_account_id=os.environ.get("ANTHROPIC_SERVICE_ACCOUNT_ID") or None,
            workspace_id=os.environ.get("ANTHROPIC_WORKSPACE_ID") or None,
        ))
    if any(os.environ.get(k) for k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "ANTHROPIC_FEDERATION_RULE_ID")):
        return anthropic.Anthropic()  # 其它环境：SDK 按自己的规则读取这些环境变量
    return None

def format_entries(entries):
    lines = []
    for i, e in enumerate(entries, 1):
        date = e.published.strftime("%m-%d") if e.published else "日期未知"
        line = (f"[{i}] {date} | {lang.detect(e.title) or '?'} | {e.source}{'（大陆网站）' if sources.is_domestic(e.url, e.source) else ''}"
                f" | {e.title}")
        if e.summary:
            line += f" | {e.summary}"
        lines.append(line)
    return "\n".join(lines)


TOKENS = {"calls": 0, "in": 0, "out": 0}   # この実行で Claude API に使ったトークン（実行ログ・管理ページ「リソース」）


def edit_stories(client, model, item, entries, langs=None):
    """让 LLM 把条目编成报道；失败返回 None。langs：读者的言語（lang.order）。"""
    langs = langs or lang.order()
    prompt = (
        f"关注项：{item['name']}\n"
        f"类型说明：{ITEM_TYPES[item['type']]}\n"
        f"读者最关心的问题：{item.get('priority') or '所有重要动态'}\n"
        + (f"背景：{item['notes']}\n" if item.get("notes") else "")
        + (f"篇幅：最多 {item['max_stories']} 条，只挑最近最受关注的事；值得报的不多就少写，不要凑数\n"
           if item.get("max_stories") else "")
        + f"\n条目：\n{format_entries(entries)}"
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4000,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": STORY_SCHEMA}},
            system=SYSTEM_PROMPT.format(primary=langs[0], secondary="、".join(langs[1:]) or "なし"),
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:  # API 错误或凭据错误：这一项退回原标题，不影响整期
        print(f"  [警告] LLM 调用失败：{type(e).__name__}: {e}", file=sys.stderr)
        return None
    usage = getattr(response, "usage", None)
    if usage is not None:
        TOKENS["calls"] += 1
        TOKENS["in"] += int(getattr(usage, "input_tokens", 0) or 0)
        TOKENS["out"] += int(getattr(usage, "output_tokens", 0) or 0)
    if response.stop_reason in ("refusal", "max_tokens"):
        print(f"  [警告] LLM 未完成（{response.stop_reason}）", file=sys.stderr)
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        stories = json.loads(text)["stories"]
    except (json.JSONDecodeError, KeyError):
        return None
    for s in stories:
        s["refs"] = [r for r in s["refs"] if 0 < r <= len(entries)]
    return [s for s in stories if s["refs"]]


QUOTED = r"[『「《〈]([^』」》〉]+)[』」》〉]"
EVENT_NAMES = r"(TGS|東京ゲームショウ|Tokyo Game Show|gamescom|BitSummit|Anime ?Expo|Jump ?Festa|ジャンプフェスタ|\[)"


def side_mention(title, item):
    """标题里列了好几部作品、打头的是别的作品，本作只是顺带一提
    （例：『ガンダム…』がブースで試遊出展。『BLEACH Mirrors High』『ワンピース…』などとともに）。
    打头的是本作的系列名（如『BLEACH』）不算。只看单部作品（游戏、动画），一类东西 / 系列本来就会列好几个。"""
    if item.get("type") not in ("game", "anime"):
        return False
    works = [q for q in re.findall(QUOTED, title) if not re.match(EVENT_NAMES, q, re.I)]
    if len(works) < 2:
        return False
    first = _norm(works[0])
    names = [_norm(w) for w in [item["name"], *(item.get("keywords") or []), *(item.get("match") or [])]]
    return not any(n in first or first in n for n in names if n)


def _bigrams(text):
    t = re.sub(r"\W+", "", text.lower())
    return {t[i:i + 2] for i in range(len(t) - 1)}


_TOPIC_STOP = {"with", "that", "this", "from", "have", "will", "just", "more", "after", "into", "about",
               "what", "your", "over", "gets", "reveals", "reveal", "official", "officially", "latest", "news",
               "game", "games", "here", "every", "first", "still", "could", "would", "they", "their"}


def _topic_tokens(title, names):
    """判断“是不是同一件事”用的词：英文 4 字母以上的词 + 中日文的两字组，去掉作品名本身"""
    t = title.lower()
    for n in names:
        t = t.replace(n.lower(), " ")
    words = {w[:4] for w in re.findall(r"[a-z]{4,}", t) if w not in _TOPIC_STOP}  # 取前 4 个字母，leak / leaker 算同一个词
    cjk = re.sub(r"[^\u3040-\u30ff\u4e00-\u9fff]", "", t)
    return words | {cjk[i:i + 2] for i in range(len(cjk) - 1)}


def _same_topic(a, b):
    return len(a & b) >= 2 and len(a & b) / max(1, min(len(a), len(b))) >= 0.25


# 跨语言判断「同一件事」：同一批里至少 EVENT_MIN 篇标题都出现的专有词（全大写缩写 3 个字母以上，或字母和数字混在一起，
# 如 AGF、KINTEX、TGS2026）。日文、韩文、中文报道同一件事时，这类词往往原样出现。常见缩写不算
EVENT_MIN = 3
_EVENT_STOP = {"CBT", "OBT", "RPG", "MMO", "MMORPG", "ARPG", "SRPG", "NPC", "PVP", "PVE", "DLC", "CEO", "USD", "JPY", "KRW",
               "PS4", "PS5", "XBOX", "NEW", "THE", "AND", "FOR", "GAME", "PC", "MV", "PV", "OST", "TV", "AI", "IP",
               "LIVE", "TOP", "NOW", "SNS", "PR", "AMA", "BETA", "TEST", "OPEN", "INFO", "NEWS", "MAX", "PRO", "ULTRA",
               "PLUS", "MINI", "LTD", "INC", "CO", "VS", "UPDATE", "PICK", "WTA", "ATP"}


def _event_tokens(title, names):
    t = title
    for n in names:
        t = re.sub(re.escape(n), " ", t, flags=re.I)
    found = set()
    for w in re.findall(r"[A-Za-z0-9]+", t):
        if w.isdigit() or w.upper() in _EVENT_STOP:
            continue
        if (w.isupper() and len(w) >= 3) or (re.search(r"[A-Za-z]", w) and re.search(r"\d", w) and len(w) >= 4):
            found.add(w.upper())
    return found


def _event_keys(entries, names):
    """每篇的专有词里，这一批至少 EVENT_MIN 篇都有的那些。返回 {编号: 词集合}"""
    toks = {i: _event_tokens(e.title, names) for i, e in enumerate(entries, 1)}
    count = {}
    for ts in toks.values():
        for w in ts:
            count[w] = count.get(w, 0) + 1
    return {i: {w for w in ts if count[w] >= EVENT_MIN} for i, ts in toks.items()}


HEAT_MIN_OUTLETS = 4  # 设了 hot_only 时，头条以外的报道至少要有几家媒体在报


def fallback_stories(entries, item, limit=None):
    """不用 AI 时的编排：
    - 标题含 priority_keywords（你最关心的事）的排前面，第一条做头条
    - 设了 hot_only 的关注项只要“最火的事”：改按有多少家媒体在报同一件事排序，同一件事合成一条；
      头条以外只留至少 HEAT_MIN_OUTLETS 家在报的，没那么多事就少写
    - 同一新闻被多家转载时只留一条（标题字符重合度高的视为同一条）
    - 媒体报道优先于 Reddit；Reddit 帖子没命中关键词的不收（多半是同人图、闲聊）
    - 本作只是被顺带提到的（打头的是别的作品）不收
    - 同等条件下国外来源优先于中国大陆网站（大陆网站常拦海外服务器、防盗链，图片和链接容易失效），
      再其次有图的、较新的优先"""
    limit = limit or max(7, item.get("max_stories") or 0)  # 篇幅 L 每期可以多于 7 条
    words = [w.lower() for w in item.get("priority_keywords") or []]
    urgent = {i for i, e in enumerate(entries, 1) if is_urgent(e, item)}
    by_heat = bool(item.get("hot_only"))
    names = sorted({item["name"], *(item.get("keywords") or []), *(item.get("match") or [])}, key=len, reverse=True)
    topics = {i: _topic_tokens(e.title, names) for i, e in enumerate(entries, 1)} if by_heat else {}
    media = [i for i, e in enumerate(entries, 1) if not sources.is_sns(e)]

    def hits(e):
        return sum(w in e.title.lower() for w in words)

    def domestic(e):
        return sources.is_domestic(e.url, e.source)

    def heat(i):
        return sum(1 for j in media if j != i and _same_topic(topics[i], topics[j]))

    def score(pair):
        i, e = pair
        if by_heat:
            return (i in urgent, heat(i), not sources.is_sns(e), hits(e), not domestic(e),
                    bool(e.image) or "news.google.com" not in e.url, -i)
        return (i in urgent, hits(e) > 0, not sources.is_sns(e), hits(e), not domestic(e),
                bool(e.image) or "news.google.com" not in e.url, -i)

    candidates = [(i, e) for i, e in enumerate(entries, 1)
                  if (hits(e) or not sources.is_sns(e)) and not side_mention(e.title, item)]
    events = _event_keys(entries, names)
    picked, grams = [], []
    for i, e in sorted(candidates, key=score, reverse=True):
        g = _bigrams(e.title)
        if any(len(g & h) / max(1, min(len(g), len(h))) > 0.5 for h in grams):
            continue
        same = next((p for p in picked if events.get(i) and events[i] & p["_events"]), None)
        if same:  # 不同语言写的同一件事（共同的专有词），并进那条报道，当作多一个来源
            same["refs"].append(i)
            continue
        if by_heat and any(i in p["refs"] or any(_same_topic(topics[i], topics[r]) for r in p["refs"]) for p in picked):
            continue  # 已经归进前面某条报道的同一件事
        grams.append(g)
        weight = "hero" if i in urgent else ("lead" if not picked or all(p["weight"] == "hero" for p in picked) else "normal")
        refs = [i] + ([j for j in media if j != i and _same_topic(topics[i], topics[j])] if by_heat else [])
        if by_heat and picked and i not in urgent and len(refs) < HEAT_MIN_OUTLETS:
            continue  # 只有一两家在报的不算“火”，事情少就少写
        picked.append({"headline": e.title, "highlight": "", "blurb": "", "weight": weight, "refs": refs,
                       "_events": set(events.get(i) or ())})
        if len(picked) == limit:
            break
    for p in picked:
        p.pop("_events")
    return picked


def find_image(chosen, refs, url):
    """只要图片地址的地方（「我会喜欢？」推荐）用：和报道配图同一套候选、检查和回退，没有可用的返回 None。"""
    return images.pick(chosen, refs, url).image


SIBLINGS = 4   # 找图时最多看几篇「同一件事的别家报道」


def same_event(item, refs, entries, headline=""):
    """同一个关注项里报道同一件事的别家记事（原文被挡・没图时，从别的网站找图用）。
    判断和 StoryDeduper 一样：标题去掉作品自己的名字后，共有的「说明是哪件事的词」合计 ≥ 2。有图的排前面，最多 SIBLINGS 篇。"""
    generic = set()
    for w in [item.get("name", ""), *(item.get("keywords") or []), *(item.get("match") or [])]:
        generic |= story_tokens(str(w))
    mine = set().union(*(story_tokens(t) for t in [headline] + [e.title for e in refs])) - generic
    taken = {e.url for e in refs}
    out = [e for e in entries if e.url not in taken and not sources.is_sns(e)
           and StoryDeduper._close(mine, story_tokens(e.title) - generic)]
    out.sort(key=lambda e: not e.image)
    return out[:SIBLINGS]


def attach_media(stories, entries, cover, name="", stats=None, used=None, langs=None, item=None):
    """给每条报道配链接和图（候选、检查和回退见 images.pick），没图的头条用作品封面。
    一条报道有好几个来源时，读者的好みの言語（langs：主言語 → 副言語，lang.order）の来源排前面，同じ言語なら国外来源排前面
    （链接和配图都先用它），中国大陆网站垫后。
    原文已经删了（404 / 410）的来源不用；来源全删了的报道不出刊。
    出刊时补到的图写回条目（entry.image / image_via），还原出的原文地址写回 entry.link，publish 会存回 inbox，下次直接用。
    used：这一期已经用掉的图，别的报道不再用（几张卡片同一张图很难看）。
    每条报道的配图结果打一行日志，stats 记整期汇总。返回要出刊的报道。"""
    used = set() if used is None else used
    out = []
    for s in stories:
        refs = sorted((entries[r - 1] for r in s.pop("refs")),
                      key=lambda e: (lang.rank(lang.detect(e.title), langs) if langs else 0, sources.is_domestic(e.url, e.source)))
        url = s.get("url")
        if url and images.gone(url):
            url = None
        for i, e in enumerate(refs if not url else []):
            link = sources.entry_link(e)
            if not images.gone(link):
                url, refs = link, refs[i:]
                break
        if not url:
            print(f"  [配图] {name} | {s.get('headline', '')[:30]} | 不出刊：原文已删（HTTP 404 / 410）", file=sys.stderr)
            if stats is not None:
                stats.drop()
            continue
        s["url"] = url
        if refs[0].published:  # 消息本身的日期，卡片上显示、按它排序
            s["date"] = refs[0].published.date().isoformat()
        res = images.pick(s.get("image"), refs, s["url"], avoid=used,
                          siblings=same_event(item or {"name": name}, refs, entries, s.get("headline", "")))
        s["image"] = res.image
        if res.image:
            used.add(res.image)
        if res.image:
            s["image_via"] = next((e.image_via for e in refs if e.image == res.image and e.image_via), res.source)
            if res.source not in ("AI 挑选", "条目自带") and not refs[0].image:
                refs[0].image, refs[0].image_via = res.image, res.source
        icon = None
        if not s["image"]:  # 拿不到配图：记下来源网站和它的图标，网页上配图位置显示来源图标
            s["source"] = refs[0].source
            icon = s["source_icon"] = images.source_icon(s["url"])
        fallback = not s["image"] and not out and bool(cover)
        if fallback:
            s["image"], s["image_via"] = cover, "作品封面"
        note = "（用作品封面）" if fallback else "（显示来源图标）" if icon else ""
        print(images.log_line(name, s.get("headline", ""), res) + note, file=sys.stderr)
        if stats is not None:
            stats.add(res, fallback)
        out.append(s)
    return out


# ---------- 输出 ----------

def pages_url(settings):
    if settings.get("pages_url"):
        return settings["pages_url"]
    repo = os.environ.get("GITHUB_REPOSITORY", "CxElegy/Wishlist")
    owner, name = repo.split("/")
    return f"https://{owner.lower()}.github.io/{name}/"


def load_wishlist():
    """愿望清单（test1・test2 で共通の自分のもの）。watch（どの版面のニュースから来たか）は今の関注清单にある版面だけ残す：
    test1 の版面（星巴克马克杯…）を指したまま「版面 →」の行き止まりリンクや「○○のほかのニュース」の推薦を出さない（読むだけ、書き戻さない）。"""
    if not WISHLIST_FILE.exists():
        return []
    wishes = (yaml.safe_load(WISHLIST_FILE.read_text(encoding="utf-8")) or {}).get("wishlist") or []
    names = {i["name"] for i in (yaml.safe_load(ITEMS_FILE.read_text(encoding="utf-8")) or {}).get("items") or []}
    return [w if not w.get("watch") or w["watch"] in names else {k: v for k, v in w.items() if k != "watch"} for w in wishes]


PICK_COUNT = 5       # 「我会喜欢？」一批几条（1 大 + 4 小正好排满）
PICK_BATCHES = 6     # 候选池有几批那么多：网页每次打开随机抽一批（看过的少抽），「换一批」再抽
EXPLORE_AFTER = 2    # 差一点的（少命中一个标签）不放进前几批（没有脚本时显示的第一批），网页上标「换换口味」
PICK_DAYS = 14       # 从最近几天收集到的消息里挑
PICK_THRESHOLD = 5   # 每命中一个喜好标签 2 分，和愿望清单同一个关注项再加 1 分；至少 5 分才推荐
BOARD_SCORE = 4      # 关注的版面里没上版面的其他消息：基础分（再按投票学到的口味加减），和「换换口味」同一档
BOARD_PER_ITEM = 2   # 每个关注项最多准备几条这样的消息（找配图要花时间）
BOARD_DAYS = 3       # 只从最近几天收集到的里挑（新鲜的）


DISCOVER_HOURS = 12    # 「同类新消息」每隔多久搜一次
DISCOVER_SIMILAR = 2   # 每次每个关注项随机搜几条 similar（不是每次都搜同样的词）
DISCOVER_PROBES = 6    # 每次再随机搜几个喜好关键词 / 赞过的关键词（找按愿望清单推荐的新消息）
DISCOVER_KEEP = 400    # 搜到的消息跨次累积（一周内的），最多留几条
DISCOVER_PICKS = 4     # 「我会喜欢？」每批放几条同类新消息
FOLLOW_PER_ITEM = 4    # 同类新消息每个关注项最多准备几条（找配图要花时间，不跟着批数无限加）


HESITATE = "纠结"   # 愿望清单里还在犹豫买不买的状态：它的 similar 也会每天搜，找类似的好产品


def _need_text(title, summary=""):
    """检查 need 用的文字：去掉标题结尾的「 - 媒体名」（「- 遊戲新聞」里的「遊戲」不说明这条消息和游戏有关）。"""
    # 只认「横线 + 空格 + 媒体名」结尾（「週邊- 遊戲新聞」「… - 4Gamer」）；open-world、Team-Up 这种词里的横线不算
    return (re.sub(r"\s*[-–—]\s+[^-–—]{1,30}$", "", title) + " " + (summary or "")).lower()


def _need_checker(items, hesitating):
    """按现在 items.yaml / 愿望清单里的 similar 重新检查一条「同类新发现」：标题和摘要要满足它那条搜索词的 need。
    累积下来的旧条目也要过一遍——need 改严以后，以前放进来的不合格条目（如 IVE 新专辑被当成超级英雄电影）要去掉；
    别的搜索词的条件对得上时换成那个标签；搜索词已经删掉的也去掉。按喜好关键词搜的（probe）由 recommend() 重新打分，这里不管。"""
    needs = {}
    for it in list(items) + list(hesitating):
        for q in it.get("similar") or []:
            needs.setdefault((it["name"], q["label"]), []).append(q.get("need") or [])

    def fits(x, key):
        text = _need_text(x.get("title", ""), x.get("summary"))
        return any(all(_like_hit(n, text) for n in need) for need in needs.get(key) or [])

    def ok(x):
        """合格ならそのまま、元のラベルに合わなければ条件の合う別のラベルに付け替えて返す（先に同じ関注項、次に別の項）。
        どれにも合わなければ None（「動畫版確定」は手遊ではなく新作动画・动画化に）。"""
        if x.get("probe") or fits(x, (x.get("item"), x.get("label"))):
            return x
        if (x.get("item"), x.get("label")) not in needs:   # 搜索词ごと消したもの：付け替えずに捨てる
            return None
        keys = sorted((k for k in needs if k != (x.get("item"), x.get("label"))), key=lambda k: k[0] != x.get("item"))
        other = next((k for k in keys if fits(x, k)), None)
        return {**x, "item": other[0], "label": other[1]} if other else None
    return ok


def discover(force=False, taste=None):
    """「我会喜欢？」要的新消息，抓 Google 新闻，去掉已经在关注清单里的作品。每次用一个新的随机种子挑搜索词，
    这样每次搜到的不一样（种子记在 state/discover.json 里，出了问题可以复现）：
    - 每个关注项的 similar（同类搜索词）随机搜 DISCOVER_SIMILAR 条 → 「同类新发现」；
      愿望清单里 status 是「纠结」的东西也一样：按它的 similar 搜类似的好产品（条目带 "wish": true）；
    - 再随机搜 DISCOVER_PROBES 个愿望清单的喜好关键词（赞过的关键词更容易抽到）→ 条目带 "probe"，
      交给 recommend() 按标题重新打分，够分的才当「因为你想要」推荐。
    搜到的跨次累积（一周内的，最多 DISCOVER_KEEP 条）；每 DISCOVER_HOURS 小时最多搜一次。"""
    settings, items = load_config()
    old = load_json(DISCOVER_FILE) or {}
    now = dt.datetime.now(dt.timezone.utc)
    ok = _need_checker(items, [dict(w, _wish=True) for w in load_wishlist() if w.get("status") == HESITATE])
    if not force and old.get("at") and now - dt.datetime.fromisoformat(old["at"]) < dt.timedelta(hours=DISCOVER_HOURS):
        return [y for y in map(ok, old.get("entries", [])) if y]
    seed = random.SystemRandom().randrange(2 ** 32)
    rng = random.Random(seed)
    tracked = {_norm(w) for i in items for w in (i.get("match") or i.get("keywords") or [i["name"]])}
    days = settings.get("lookback_days", 7)
    since = now - dt.timedelta(days=days)
    hesitating = [dict(w, _wish=True) for w in load_wishlist() if w.get("status") == HESITATE]
    searches = []  # (搜索词 dict, 来源)
    for item in items + hesitating:
        qs = list(item.get("similar") or [])
        searches += [(q, item) for q in rng.sample(qs, min(DISCOVER_SIMILAR, len(qs)))]
    searches += [(q, None) for q in probe_queries(rng, taste or {})]
    out, grams = [], []
    for q, item in searches:
        try:
            found = sources.google_news(q["query"], days, NEWS_LANGS[q.get("lang", "zh-CN")])
        except Exception as err:
            print(f"  [同类] {q['query']} 失败：{err}", file=sys.stderr)
            continue
        for e in found[:20]:
            if source_in(e.source, settings.get("exclude_sources", ["YouTube"])) or \
                    host_rule_hit(settings.get("exclude_hosts"), e.title, (e.url, e.site)) or \
                    any(re.search(p, e.title) for p in JUNK_PATTERNS) or is_spam(e.title):   # 出典名（前方一致）・網域は収集と同じ
                continue
            if e.published and e.published < since:
                continue
            if any(w and w in _norm(e.title + e.summary) for w in tracked):  # 已经在关注的不算“新发现”
                continue
            if not all(_like_hit(n, _need_text(e.title, e.summary)) for n in q.get("need") or []):
                continue
            g = _title_grams(e.title, [])
            if any(_similar(g, x) for x in grams):
                continue
            grams.append(g)
            meta = ({"item": item["name"], "label": q["label"], **({"wish": True} if item.get("_wish") else {})}
                    if item else {"item": q["wish"], "label": q["label"], "probe": q["wish"]})
            out.append({"title": e.title, "url": e.url, "source": e.source, "summary": e.summary, "image": e.image,
                        "date": e.published.isoformat() if e.published else "", **meta})
    fresh = len(out)
    urls = {x["url"] for x in out}
    for x in old.get("entries", []):  # 以前搜到的、一周内的继续留着：池子越积越大，每次换一批都有新的
        if x["url"] in urls or (x.get("date") and x["date"] < since.isoformat()):
            continue
        x = ok(x)
        if not x:
            continue
        if any(_similar(_title_grams(x["title"], []), g) for g in grams):
            continue
        urls.add(x["url"])
        out.append(x)
    out = out[:DISCOVER_KEEP]
    save_json(DISCOVER_FILE, {"at": now.isoformat(), "seed": seed, "queries": [q["query"] for q, _ in searches],
                              "entries": out})
    print(f"同类新消息：新搜到 {fresh} 条，累计 {len(out)} 条（随机种子 {seed}，搜了 {len(searches)} 个词）", file=sys.stderr)
    return out


def _lang_of(text):
    """搜索词用哪个语言区的 Google 新闻：有假名的日文，有谚文的韩文，汉字分简繁，其余英文。"""
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja-JP"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko-KR"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh-TW" if _to_simplified(text) != text else "zh-CN"
    return "en-US"


def probe_queries(rng, taste):
    """随机挑几个愿望清单的喜好关键词去搜（基本属性不单独搜）。每个搜索词是「具体喜好的一种写法」
    加上同一件东西另一个喜好里同语言的一种写法（猫 + マグ），这样搜到的更像那件东西。
    赞过的关键词（taste 里分数 > 0 的）权重更高，踩过的不搜。"""
    bank = []
    for w in load_wishlist():
        basics = set(w.get("basics") or [])
        likes = w.get("likes") or {}
        for label, kws in likes.items():
            if label in basics:
                continue
            for k in kws:
                score = max(taste.get(_like_key(k), 0), taste.get(label, 0))
                if score < 0:
                    continue
                for alt in (a.strip() for a in str(k).split("|")):
                    if alt and not alt.startswith("-"):
                        bank.append((1 + 2 * score, alt, label, w, likes))
    picked, seen = [], set()
    while bank and len(picked) < DISCOVER_PROBES:
        weight, alt, label, w, likes = bank.pop(rng.choices(range(len(bank)), [b[0] for b in bank])[0])
        if (w["name"], label) in seen:
            continue  # 同一件东西的同一个喜好只搜一次
        seen.add((w["name"], label))
        lang = _lang_of(alt)
        extra = [a.strip() for lb, kws in likes.items() if lb != label for k in kws for a in str(k).split("|")
                 if a.strip() and not a.strip().startswith("-") and _lang_of(a.strip()) == lang]
        query = alt + (" " + rng.choice(extra) if extra else "")
        picked.append({"query": query, "lang": lang, "label": label, "wish": w["name"]})
    return picked


def _like_hit(keyword, text):
    """喜好关键词可以用 | 写同一个东西的几种写法（Snoopy|スヌーピー|史努比），命中任意一种就算。
    写成 -词 的是排除：リス|-リスト 里「やることリスト」的リス不算（先把排除的词从文字里去掉再找）。
    英文词要是完整的词（前面不能接着字母数字；5 个字母以内的后面也不能接着，复数 s 除外）：
    Bad Bunny 不该算 bunny 以外的东西，tour 不该命中 tourism。"""
    alts = [a.strip().lower() for a in str(keyword).split("|") if a.strip()]
    for bad in (a[1:] for a in alts if a.startswith("-")):
        text = text.replace(bad, " ")
    return any(_alt_hit(a, text) for a in alts if not a.startswith("-"))


def _alt_hit(alt, text):
    if re.fullmatch(r"[a-z0-9][a-z0-9 .+'’-]*", alt):
        tail = r"(?:e?s)?(?![a-z0-9])" if len(alt) <= 5 else ""
        return re.search(rf"(?<![a-z0-9]){re.escape(alt)}{tail}", text) is not None
    return alt in text


def _like_key(keyword):
    return str(keyword).split("|")[0].strip().lower()


# アカウントごとの表（db/accounts.sql）：読む・消す・直すときは自分のアカウントの行だけ、書くときは account を付ける
ACCOUNT_TABLES = {"feedback", "sizes", "nav_schemes", "item_requests", "photo_inbox", "live_status", "live_log", "news", "stories", "price_history"}


def scope_account(path, body=None, method=None, account=None):
    """supabase() の path・body に自分のアカウント（sitedir.NAME）を入れる。表がアカウントごとでなければそのまま。"""
    account = account or sitedir.NAME
    table, _, query = path.partition("?")
    if table not in ACCOUNT_TABLES:
        return path, body
    if body is not None and (method or "POST") == "POST":   # 書く：行に account、on_conflict に account
        body = [{**r, "account": account} for r in body] if isinstance(body, list) else {**body, "account": account}
        query = re.sub(r"on_conflict=", "on_conflict=account,", query)
    else:                                                 # 読む・消す・直す：自分の行だけ
        query = f"account=eq.{account}" + (f"&{query}" if query else "")
    return f"{table}?{query}" if query else table, body


def supabase(path, body=None, prefer=None, method=None):
    """用 secret key（SUPABASE_SERVICE_KEY）调 Supabase 的数据接口。没配置时返回 None。
    アカウントごとの表は自分のアカウントの行だけを読み書きする（scope_account）。"""
    path, body = scope_account(path, body, method)
    settings, _ = load_config()
    base, key = (settings.get("supabase_url") or "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not (base and key):
        return None
    headers = {"apikey": key, "Accept": "application/json"}
    if key.startswith("eyJ"):  # 旧版 JWT 格式的 key 还要放进 Authorization；新版 sb_secret_ 只放 apikey
        headers["Authorization"] = f"Bearer {key}"
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(f"{base}/rest/v1/{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {err.code}：{detail}") from None
    return json.loads(text) if text.strip() else []


def news_rows(path):
    """一份 inbox 里的全部条目，转成数据库 news 表的行。"""
    data = load_json(path)
    rows = {}
    for item in data.get("items", []):
        for d in item.get("entries", []):
            rows[(item["name"], d["url"])] = {
                "item": item["name"], "url": d["url"], "title": d["title"], "source": d.get("source"),
                "summary": d.get("summary") or None, "image": d.get("image") or None,
                "published_at": d.get("date"), "collected_on": data.get("date") or path.stem,
                "urgent": bool(d.get("urgent")), "backfill": bool(item.get("backfill"))}
    return rows


def sync_news():
    """把收集到的消息写进数据库（Supabase 的 news 表，建表语句在 db/news.sql）。
    只同步内容变过的 inbox 文件，记在 state/db_news.json；第一次运行会把已有的全部补进去。
    数据库连不上不影响出刊，下次运行再补。"""
    synced = (load_json(NEWS_SYNC_FILE) or {}).get("files", {})
    todo, rows = {}, {}
    for path in sorted(INBOX_DIR.glob("????-??-??.json")):
        file_rows = news_rows(path)
        digest_ = hashlib.sha1(json.dumps(sorted(file_rows.items(), key=lambda kv: kv[0]),
                                          ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        if synced.get(path.stem) != digest_:
            todo[path.stem] = digest_
            rows.update(file_rows)  # 同一条在几期里都有时，以最新一期为准（一次写入里不能有重复的行）
    if not todo:
        return
    batch = list(rows.values())
    try:
        for i in range(0, len(batch), 500):
            if supabase("news?on_conflict=item,url", batch[i:i + 500],
                        "resolution=merge-duplicates,return=minimal") is None:
                return  # 没配置数据库
    except Exception as err:
        hint = "（还没建表？在 Supabase 的 SQL Editor 里运行 db/news.sql）" if "PGRST205" in str(err) else ""
        print(f"  [数据库] 写入消息失败，下次再试{hint}：{err}", file=sys.stderr)
        return
    save_json(NEWS_SYNC_FILE, {"files": {**synced, **todo}})
    print(f"数据库：写入 {len(batch)} 条消息（{'、'.join(sorted(todo))}）", file=sys.stderr)


def _file_digest(rows):
    return hashlib.sha1(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def story_rows(path):
    """一期 reports 里的报道，转成数据库 stories 表的行。"""
    data = load_json(path)
    date = data.get("date") or path.stem
    rows = []
    for item in data.get("items", []):
        for pos, st in enumerate(item.get("stories") or []):
            day = st.get("date") or ""
            rows.append({"issue_date": date, "item": item["name"], "pos": pos, "headline": st["headline"],
                         "highlight": st.get("highlight") or None, "blurb": st.get("blurb") or None,
                         "weight": st.get("weight"), "url": st.get("url"), "image": st.get("image") or None,
                         "story_date": day[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", day) else None})
    return rows


def sync_stories():
    """把编排后的报道（reports/，网页上显示的那些）写进数据库 stories 表（建表语句在 db/history.sql）。
    某一期内容变了（AI 编辑重新编排过）就整期替换；已同步到哪记在 state/db_stories.json。"""
    synced = (load_json(STORIES_SYNC_FILE) or {}).get("files", {})
    done = {}
    for path in sorted(REPORTS_DIR.glob("????-??-??.json")):
        rows = story_rows(path)
        digest_ = _file_digest(rows)
        if synced.get(path.stem) == digest_:
            continue
        try:
            if supabase(f"stories?issue_date=eq.{path.stem}", method="DELETE", prefer="return=minimal") is None:
                return  # 没配置数据库
            if rows:
                supabase("stories", rows, "return=minimal")
        except Exception as err:
            hint = "（还没建表？在 Supabase 的 SQL Editor 里运行 db/history.sql）" if "PGRST205" in str(err) else ""
            print(f"  [数据库] 写入报道失败，下次再试{hint}：{err}", file=sys.stderr)
            break
        done[path.stem] = digest_
        print(f"数据库：{path.stem} 的报道 {len(rows)} 条", file=sys.stderr)
    if done:
        save_json(STORIES_SYNC_FILE, {"files": {**synced, **done}})


def _amount(price):
    """价格里能看出的数字（850、4,378、1.5 万 → 15000）；看不出就 None。"""
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(price))
    if not m:
        return None
    n = float(m.group().replace(",", ""))
    if re.search(r"\d\s*万", str(price)) and "多" not in str(price):
        n *= 10000
    elif "万" in str(price):
        return None  # 「6 万多」这种说不准的不算
    return int(n) if n == int(n) else n


def sync_prices():
    """价格 / 状态的历史写进数据库 price_history 表：Steam 价格、播出状态（state/facts.json）和
    愿望清单里写的价格。值变了才新增一行；上次写进去的值记在 state/db_prices.json。"""
    last = (load_json(PRICES_SYNC_FILE) or {}).get("last", {})
    now = {}
    for key, f in (load_json(FACTS_FILE) or {}).items():
        if f.get("item"):  # 旧格式的状态（没记关注项名字）等下次收集后再记
            now[key] = {"item": f["item"], "kind": key.split(":")[0], "label": f.get("label"), "value": str(f["text"]),
                        "amount": None, "currency": None}
    for w in load_wishlist():
        if w.get("price") in (None, ""):
            continue
        cur = str(w.get("currency") or "").strip()
        now[f"wishlist:{w['name']}"] = {"item": w["name"], "kind": "wishlist", "label": "愿望清单价格",
                                        "value": f"{cur} {w['price']}".strip(), "amount": _amount(w["price"]),
                                        "currency": cur or None}
    rows = [r for k, r in now.items() if last.get(k) != r["value"]]
    if not rows:
        return
    try:
        if supabase("price_history", rows, "return=minimal") is None:
            return
    except Exception as err:
        hint = "（还没建表？在 Supabase 的 SQL Editor 里运行 db/history.sql）" if "PGRST205" in str(err) else ""
        print(f"  [数据库] 写入价格历史失败，下次再试{hint}：{err}", file=sys.stderr)
        return
    save_json(PRICES_SYNC_FILE, {"last": {**last, **{k: r["value"] for k, r in now.items()}}})
    print(f"数据库：价格 / 状态有变化 {len(rows)} 条", file=sys.stderr)


PHOTO_DIR = INBOX_DIR / "photos"


def export_photos():
    """愿望清单页「📷 拍照加愿望」上传的照片：从数据库 photo_inbox 表导出到 inbox/photos/<编号>.jpg / .json，
    标成 exported，等 Claude 定时任务按 PHOTOS.md 认出物品、加进 wishlist.yaml。
    wishlist.yaml 里已经有 photo: <编号> 的，标成 done 并记下名字（网页排队列表显示「已加入」）。"""
    import base64
    try:
        rows = supabase("photo_inbox?state=eq.new&select=id,created_at,status,note,image&order=id.asc")
        if rows is None:
            return  # 没配置数据库
        done = {w["photo"]: w["name"] for w in load_wishlist() if w.get("photo")}
        if done:
            open_ = supabase("photo_inbox?state=neq.done&select=id") or []
            for r in open_:
                if r["id"] in done:
                    supabase(f"photo_inbox?id=eq.{r['id']}", {"state": "done", "wish_name": done[r["id"]][:300]},
                             "return=minimal", method="PATCH")
                    print(f"照片：{r['id']} 已加入愿望清单「{done[r['id']]}」", file=sys.stderr)
    except Exception as err:
        hint = "（还没建表？在 Supabase 的 SQL Editor 里运行 db/photo_inbox.sql）" if "PGRST205" in str(err) else ""
        print(f"  [照片] 读收件箱失败{hint}：{err}", file=sys.stderr)
        return
    for r in rows:
        head, _, data = (r.get("image") or "").partition(",")
        if head != "data:image/jpeg;base64" or not data:
            continue
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        (PHOTO_DIR / f"{r['id']}.jpg").write_bytes(base64.b64decode(data))
        save_json(PHOTO_DIR / f"{r['id']}.json", {"id": r["id"], "status": r["status"], "note": r.get("note") or "",
                                                  "uploaded": r["created_at"]})
        try:
            supabase(f"photo_inbox?id=eq.{r['id']}", {"state": "exported"}, "return=minimal", method="PATCH")
        except Exception as err:  # 标不上的下次会再导出一次（同名文件覆盖，不会重复）
            print(f"  [照片] 标记 {r['id']} 失败：{err}", file=sys.stderr)
        print(f"照片：导出 {r['id']}（{r['status']}）到 inbox/photos/", file=sys.stderr)


# 设置页上能新增 / 修改的字段（按写进 items.yaml 的顺序）。值的检查规则：
#   str:N 不超过 N 字的一句话；list:N:M 最多 N 个、每个不超过 M 字的字符串列表
ITEM_FIELDS = {
    "type": "type", "parent": "str:80", "section": "section", "subs": "subs", "also": "also", "media": "list:8:20", "size": "size", "subtitle": "str:80",
    "keywords": "list:40:100", "match": "list:80:100", "exclude": "list:80:100", "news_langs": "langs",
    "priority": "str:300", "urgent_patterns": "regex", "site": "url",
    "steam_appid": "int", "anilist_id": "int", "anilist_type": "anilist_type", "tmdb": "tmdb", "notes": "str:1500",
}
WEB_ITEM_MARK = "从网页设置页加进来的"


def _clean_field(key, value):
    """检查设置页提交的一个字段。返回清理后的值；None = 删掉这个字段；不合规就抛 ValueError。"""
    rule = ITEM_FIELDS[key]
    if value is None or value == "" or value == []:
        return None
    if rule.startswith("str:"):
        if not isinstance(value, str) or len(value.strip()) > int(rule[4:]):
            raise ValueError(f"{key} 太长或不是文字")
        return value.strip() or None
    if rule.startswith("list:") or rule in ("langs", "regex"):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{key} 要是文字列表")
        out = list(dict.fromkeys(v.strip() for v in value if v.strip()))
        if rule.startswith("list:"):
            most, longest = map(int, rule.split(":")[1:])
            # re: の規則（「名前」と「面の言葉」が同時に出る、の先読み）は長くなるので 600 字まで
            if len(out) > most or any(len(v) > (600 if v.startswith("re:") else longest) for v in out):
                raise ValueError(f"{key} 太多或太长")
            for v in out:   # 壊れた re:（括弧の閉じ忘れ）は依頼の段で断る：通すと毎回の収集で re.search が例外を出す
                if v.startswith("re:"):
                    try:
                        re.compile(v[3:])
                    except re.error as err:
                        raise ValueError(f"{key} 的正则写错了：{v[:40]}（{err}）") from None
        elif rule == "langs":
            if any(v not in NEWS_LANGS for v in out):
                raise ValueError(f"news_langs 只支持 {'/'.join(NEWS_LANGS)}")
        else:
            if len(out) > 12 or any(len(v) > 600 for v in out):
                raise ValueError("urgent_patterns 太多或太长")
            for v in out:
                try:
                    re.compile(v)
                except re.error as err:
                    raise ValueError(f"要紧消息规则写错了：{v[:40]}（{err}）") from None
        return out or None
    if rule == "section":
        value = taxonomy.canonical(value) if isinstance(value, str) else value
        if value not in taxonomy.SECTIONS:
            raise ValueError(f"板块只能选 sections.yaml 里的：{'/'.join(taxonomy.SECTIONS)}")
        return value
    if rule == "also":   # ほかの板块：{板块: {分け方: 小分類}}（版面は section に 1 つ、ここに書いた板块には目次の乗換駅）
        value = {taxonomy.canonical(k): v for k, v in value.items()} if isinstance(value, dict) else value
        if not isinstance(value, dict) or len(value) > 4 or not all(k in taxonomy.SECTIONS for k in value):
            raise ValueError(f"also 的板块只能选 sections.yaml 里的：{'/'.join(taxonomy.SECTIONS)}")
        first = lambda k: taxonomy.SECTIONS[k]["schemes"][0]
        return {k: _clean_field("subs", v or {first(k)["id"]: taxonomy.values(first(k))[0]}) for k, v in value.items()} or None
    if rule == "subs":
        if not isinstance(value, dict) or len(value) > 6 or not all(
                isinstance(k, str) and re.fullmatch(r"[a-z_]{1,20}", k) and isinstance(v, str) and 0 < len(v.strip()) <= 20
                for k, v in value.items()):
            raise ValueError("小分类要写成 {分法: 值}，每个值 20 字以内")
        return {k: v.strip() for k, v in value.items()}
    if rule == "type":
        if value not in ITEM_TYPES:
            raise ValueError(f"type 必须是 {'/'.join(ITEM_TYPES)} 之一")
        return value
    if rule == "size":
        if value not in SIZE_STORIES:
            raise ValueError("size 只能是 S / M / L")
        return value
    if rule == "int":
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{key} 要是数字")
        return value
    if rule == "anilist_type":
        if value not in ("ANIME", "MANGA"):
            raise ValueError("anilist_type 只能是 ANIME / MANGA")
        return value
    if rule == "tmdb":
        if not isinstance(value, str) or not re.fullmatch(r"(tv|movie)/\d+", value.strip()):
            raise ValueError("tmdb 要写成 tv/1399 或 movie/693134")
        return value.strip()
    if rule == "url":
        if not isinstance(value, str) or not re.fullmatch(r"https?://\S{3,300}", value.strip()):
            raise ValueError("site 要是 http(s) 网址")
        return value.strip()
    raise ValueError(f"不认识的字段 {key}")


def clean_item_config(config):
    """设置页提交的 config → {字段: 值或 None}（None = 删掉）。不认识的字段忽略；有不合规的抛 ValueError。"""
    if not isinstance(config, dict):
        raise ValueError("内容不对")
    return {k: _clean_field(k, config[k]) for k in ITEM_FIELDS if k in config}


def _yaml_field(key, value):
    """一个字段写成 items.yaml 里的几行（4 格缩进；字符串都用 JSON 引号，YAML 也认）。"""
    q = lambda v: json.dumps(v, ensure_ascii=False)
    if isinstance(value, dict):   # flow mapping 1 行（also は {板块: {分け方: 小分類}} の 2 段）
        flow = lambda d: "{" + ", ".join(f"{k}: {flow(v) if isinstance(v, dict) else q(v)}" for k, v in d.items()) + "}"
        return [f"    {key}: {flow(value)}"]
    if isinstance(value, list):
        if key == "urgent_patterns":
            return [f"    {key}:"] + [f"      - {q(v)}" for v in value]
        return [f"    {key}: [{', '.join(q(v) for v in value)}]"]
    if isinstance(value, int) or key in ("type", "size", "anilist_type"):
        return [f"    {key}: {value}"]
    return [f"    {key}: {q(value)}"]


def item_entry_yaml(name, fields):
    """一个新关注项，写成 items.yaml 里的一段。"""
    lines = [f"  - name: {json.dumps(name, ensure_ascii=False)}"]
    for key in ITEM_FIELDS:
        if fields.get(key) is not None:
            lines += _yaml_field(key, fields[key])
    return "\n".join(lines) + "\n"


def _item_span(lines, name):
    """items.yaml 里名字是 name 的那一段：返回 (开始行, 结束行)，找不到返回 None。"""
    start = None
    for i, line in enumerate(lines):
        top = re.match(r"^  - name:(.*)$", line)
        if start is not None and (line.startswith("  - ") or re.match(r"^\S", line)):
            return start, i
        if top:
            try:
                if yaml.safe_load(top.group(1)) == name:
                    start = i
            except yaml.YAMLError:
                pass
    return (start, len(lines)) if start is not None else None


def _yaml_closed(lines):
    """items.yaml の 1 欄の行（`    key: …` から）が、それだけで YAML として読めるか（[ … ] が閉じているか）。"""
    try:
        yaml.safe_load("\n".join(lines))
        return True
    except yaml.YAMLError:
        return False


def set_item_fields(text, name, fields):
    """只改 items.yaml 里关注项 name 的这几个字段（None = 删掉），别的字段、注释、顺序都不动。返回新的全文。"""
    lines = text.split("\n")
    span = _item_span(lines, name)
    if span is None:
        raise ValueError(f"items.yaml 里没有「{name}」")
    start, end = span
    while end - 1 > start and not lines[end - 1].strip():  # 这一段末尾的空行不算
        end -= 1
    block = lines[start:end]
    for key, value in fields.items():
        at = next((i for i, l in enumerate(block) if re.match(rf"^    {key}:", l)), None)
        new = _yaml_field(key, value) if value is not None else []
        if at is None:
            block += new
            continue
        stop = at + 1   # 这个字段占的行：后面缩进更深的（列表、多行文字），中间的空行也算
        while stop < len(block) and (not block[stop].strip() or len(block[stop]) - len(block[stop].lstrip()) > 4):
            stop += 1
        # 複数行の [ … ] / { … }：閉じ括弧の行（`    ]`）は字下げが同じなので上では止まる。値が閉じるまで（間のコメント行も）一緒に置き換える
        # （閉じ括弧を残すと YAML が壊れ、take_item_requests が依頼を skipped にしていた：滑雪・猫用品・漫威电影 などの match / exclude）
        while stop < len(block) and not _yaml_closed(block[at:stop]) and re.match(r"^(?:    [\]}#]|\s{5,}|\s*$)", block[stop]):
            stop += 1
        while stop - 1 > at and not block[stop - 1].strip():
            stop -= 1
        block[at:stop] = new
    return "\n".join(lines[:start] + block + lines[end:])


def delete_item(text, name):
    """items.yaml から関注項 name の 1 段を消す（前の空行も 1 つ）。下級だったものは parent を外して残す。返り値：新しい全文。"""
    lines = text.split("\n")
    span = _item_span(lines, name)
    if span is None:
        raise ValueError(f"关注清单里没有「{name}」")
    start, end = span
    while start > 0 and not lines[start - 1].strip():
        start -= 1
    new = "\n".join(lines[:start] + lines[end:])
    for i in (yaml.safe_load(new) or {}).get("items") or []:
        if i.get("parent") == name:
            new = set_item_fields(new, i["name"], {"parent": None})
    return new


EMBLEM_REJECT_MAX = 50   # 1 回の依頼で外せる小元素の数（管理ページの「違う」は版面ごとに 1 件の依頼にまとめて送る）
EMBLEM_REJECT_KEEP = 1000   # 理由の記録（state/emblem_rejects.json）に残す件数


def _reject_marks(marks):
    """「違う」の依頼の中身 → {画像: (理由の id, ひとこと)}。古い形（画像の網址だけ）は理由「そのほか」。"""
    import emblem_rules
    if not isinstance(marks, list) or not marks or len(marks) > EMBLEM_REJECT_MAX:
        raise ValueError("外す画像の指定が正しくない")
    out = {}
    for m in marks:
        m = {"image": m} if isinstance(m, str) else m
        if not isinstance(m, dict) or not isinstance(m.get("image"), str) or not 0 < len(m["image"]) <= 2000:
            raise ValueError("外す画像の指定が正しくない")
        why = m.get("reason") or "misc"
        if why not in emblem_rules.REJECT_IDS:
            raise ValueError(f"理由「{why}」は一覧にない")
        out[m["image"]] = (why, str(m.get("note") or "")[:200])
    return out


def reject_emblems(text, name, marks):
    """管理ページの「違う」：関注項 name の小元素から marks の画像（items.yaml の image か source）を外し、
    元の画像を emblem_reject に足す（自動補完は二度と選ばない。足りなくなった分は次の後台で別の画像を探す）。
    返り値：(新しい全文, 外した小元素のリスト)。外した小元素には選ばれた理由（_reason・_note）が付く。どれも今の小元素になければ ValueError。"""
    import emblem
    want = _reject_marks(marks)
    item = next((i for i in (yaml.safe_load(text) or {}).get("items") or [] if i.get("name") == name), None)
    if item is None:
        raise ValueError(f"关注清单里没有「{name}」")
    ems = [x for x in item.get("emblem") or [] if isinstance(x, dict)]
    gone = []
    for x in ems:
        hit = next((want[u] for u in (x.get("image"), x.get("source")) if u in want), None)
        if hit:
            gone.append({**x, "_reason": hit[0], "_note": hit[1]})
    if not gone:
        raise ValueError("その画像はもう小元素にない（もう外れている）")
    out = {x.get("image") for x in gone}
    keep = [x for x in ems if x.get("image") not in out]
    rej = list(item.get("emblem_reject") or [])
    for x in gone:   # 元の網址（倉庫の webp は消すので、次に同じ画像を拾わないよう出所のほうを覚える）
        rej += [u for u in (x.get("source"), x.get("image")) if isinstance(u, str) and re.match(r"https?://", u)]
    text = emblem.item_text(text, name, keep)
    text = set_item_fields(text, name, {"emblem_reject": list(dict.fromkeys(rej))})
    return text, [{**x, "_board": name, "_kind": item.get("emblem_kind") or ""} for x in gone]


def log_emblem_rejects(gone, when=None):
    """外した小元素を理由つきで state/emblem_rejects.json に残す（版面・種類・どの取り方で選ばれたか（why）・網域・形）。
    管理ページ「「違う」の理由」がこれを数える：同じ理由・同じ取り方が溜まったら、その判断（emblem_rules.REJECT_REASONS の 3 つ目）を締める。"""
    if not gone:
        return
    when = when or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows = (load_json(EMBLEM_REJECTS_FILE) or {}).get("rows") or []
    for x in gone:
        src = x.get("source") or x.get("image") or ""
        rows.append({"at": when, "board": x["_board"], "kind": x.get("_kind") or "", "reason": x["_reason"], "note": x.get("_note") or "",
                     "subject": x.get("subject") or "", "why": x.get("why") or "", "shape": x.get("shape") or "",
                     "host": urllib.parse.urlsplit(src).hostname or "", "source": src, "page": x.get("page") or ""})
    save_json(EMBLEM_REJECTS_FILE, {"rows": rows[-EMBLEM_REJECT_KEEP:]})


def _drop_emblem_files(gone, items):
    """外した小元素の倉庫の画像（docs/home/emblems/*.webp）を消す。ほかの関注項・目次のアイコンが使っているものは残す。"""
    import emblem
    used = {str(x.get("image")) for i in items for x in (i.get("emblem") or []) + [i.get("icon")] if isinstance(x, dict)}
    for x in gone:
        img = str(x.get("image") or "")
        if re.fullmatch(r"emblems/[a-z0-9-]+\.webp", img) and img not in used:
            (emblem.EMB_DIR / img.split("/", 1)[1]).unlink(missing_ok=True)


def take_item_requests():
    """设置页上「新增 / 修改关注项」提交的：从数据库 item_requests 表读出待处理的，写进 items.yaml，再标成 done。
    新增的追加到文件末尾，修改的只改提交了的字段（不动原来的内容和注释）。
    名字重复、找不到、内容不对的标成 skipped，原因写在 note 里（设置页上看得到）。
    新增的这一次运行就会收集新闻（往前补抓 first_lookback_days 天），照常发「新增关注项」通知。"""
    try:
        rows = supabase("item_requests?status=eq.pending&select=id,action,name,config&order=id.asc")
    except Exception as err:
        hint = "（还没建表？在 Supabase 的 SQL Editor 里运行 db/item_requests.sql）" if "PGRST205" in str(err) else ""
        print(f"  [关注项] 读新增 / 修改请求失败{hint}：{err}", file=sys.stderr)
        return
    if not rows:
        return
    settings, items = load_config()
    today = dt.datetime.now(zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))).date().isoformat()
    text = ITEMS_FILE.read_text(encoding="utf-8")
    done, skipped, dropped = [], {}, []
    for r in rows:
        name = (r.get("name") or "").strip()
        names = {i["name"] for i in items}
        try:
            if r.get("action") == "edit" and "_emblem_reject" in (r.get("config") or {}):   # 管理ページの「違う」
                new, gone = reject_emblems(text, name, r["config"]["_emblem_reject"])
                got = (yaml.safe_load(new) or {}).get("items") or []
                assert [i for i in got if i.get("name") != name] == [i for i in items if i.get("name") != name], "别的关注项被改动了"
                text, items = new, got
                dropped += gone
                done.append(r)
                continue
            if r.get("action") == "edit" and (r.get("config") or {}).get("_delete") is True:   # 設定ページの「删」
                new = delete_item(text, name)
                got = (yaml.safe_load(new) or {}).get("items") or []
                assert name not in {i.get("name") for i in got}, "没删掉"
                assert len(got) == len(items) - 1, "删多了"
                text, items = new, got
                done.append(r)
                continue
            fields = clean_item_config(r.get("config") or {})
            if fields.get("parent"):   # 上級は今ある、自分には上級のない関注項だけ（1 層だけ）。板块は書いてなければ上級と同じ
                top = next((i for i in items if i["name"] == fields["parent"]), None)
                if top is None or top["name"] == name or top.get("parent"):
                    raise ValueError(f"上级「{fields['parent']}」不对：要是已有的、自己没有上级的关注项")
                if any(i.get("parent") == name for i in items):
                    raise ValueError(f"「{name}」下面已经有下级了，不能再挂到别人下面（只做一层）")
                fields["section"] = fields.get("section") or section_of(top)
            if fields.get("also") and fields.get("section"):
                fields["also"] = {k: v for k, v in fields["also"].items() if k != fields["section"]} or None
            if r.get("action") == "edit":
                if name not in names:
                    raise ValueError(f"关注清单里没有「{name}」")
                fields = {k: v for k, v in fields.items() if not (k == "type" and v is None)}
                if not fields:
                    raise ValueError("没有要改的")
                new = set_item_fields(text, name, fields)
            else:
                if name in names:
                    raise ValueError(f"关注清单里已经有「{name}」了")
                fields["type"] = fields.get("type") or "product"
                fields["keywords"] = fields.get("keywords") or [name]
                fields["notes"] = f"{today} {WEB_ITEM_MARK}。" + (fields.get("notes") or "")
                new = text.rstrip("\n") + "\n\n" + item_entry_yaml(name, fields)
            got = (yaml.safe_load(new) or {}).get("items") or []
            mine = next((i for i in got if i.get("name") == name), None)
            others = [i for i in got if i.get("name") != name]
            assert others == [i for i in (yaml.safe_load(text) or {}).get("items") or [] if i.get("name") != name], "别的关注项被改动了"
            assert mine and all(mine.get(k) == v for k, v in fields.items() if v is not None), "写进去的和提交的不一样"
            assert all(k not in mine for k, v in fields.items() if v is None), "该删的字段还在"
            for lang in mine.get("news_langs") or []:
                assert lang in NEWS_LANGS
        except (ValueError, AssertionError, yaml.YAMLError) as err:
            skipped[r["id"]] = str(err)[:300] or "内容不对"
            print(f"  [关注项] 「{name}」没处理：{skipped[r['id']]}", file=sys.stderr)
            continue
        text = new
        items = got
        done.append(r)
    if done:
        ITEMS_FILE.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        _drop_emblem_files(dropped, items)
        log_emblem_rejects(dropped)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        if done:
            supabase(f"item_requests?id=in.({','.join(str(r['id']) for r in done)})",
                     {"status": "done", "handled_at": now}, "return=minimal", method="PATCH")
        for rid, why in skipped.items():
            supabase(f"item_requests?id=eq.{rid}", {"status": "skipped", "handled_at": now, "note": why},
                     "return=minimal", method="PATCH")
    except Exception as err:  # 标不上的下次还会读到：新增的会因为名字已存在被跳过，修改的再改一次结果一样
        print(f"  [关注项] 标记请求失败：{err}", file=sys.stderr)
    for r in done:
        what = ("删除" if (r.get("config") or {}).get("_delete") is True else "外した小元素" if "_emblem_reject" in (r.get("config") or {})
                else "修改" if r.get("action") == "edit" else "加入")
        print(f"关注项：从设置页{what}「{r['name']}」", file=sys.stderr)


def sync_db():
    """收集到的消息、编排后的报道、价格 / 状态历史都写进数据库。连不上不影响出刊，下次再补。"""
    sync_news()
    sync_stories()
    sync_prices()


def load_feedback():
    """「我会喜欢？」上的 👍 / 👎：投票存在 Supabase（Postgres）的 feedback 表里，网页直接写入。
    有 SUPABASE_SERVICE_KEY 时从数据库读出全部投票，顺便存一份到 state/feedback.json；
    读不到（本地运行、没配置、数据库暂时连不上）就用上次存的那份。返回每个链接最新的一票。"""
    rows = (load_json(FEEDBACK_FILE) or {}).get("rows", [])
    try:
        got = supabase("feedback?select=url,vote,kind,title,work,because,hits,words,created_at&order=id.asc")
        if got is not None:
            rows = got
            save_json(FEEDBACK_FILE, {"rows": rows})
            print(f"投票：从数据库读到 {len(rows)} 条", file=sys.stderr)
    except Exception as err:
        print(f"  [投票] 读数据库失败，用上次存的：{err}", file=sys.stderr)
    latest = {}
    for r in rows:
        if r.get("url") and r.get("vote") in (-1, 0, 1):
            latest[r["url"]] = r
    return [r for r in latest.values() if r["vote"]]


def pack_batches(picks):
    """「気になるかも？」の頁（batch）を 0 から詰める。愿望清单がまだない新しいアカウントでは「欲しい物から」の候補（0 頁目）が
    1 件もなく、版面のほかのニュース（1 頁目〜）だけになる → 最初の頁が空の箱にならないように、前後の順はそのまま番号だけ詰める。"""
    order = sorted({p.get("batch") or 0 for p in picks})
    return [{**p, "batch": order.index(p.get("batch") or 0)} for p in picks]


def current_picks(items):
    """「気になるかも？」の候補のうち、今の関注清单にない版面（test1 の版面）に結び付いたものは出さない。
    推薦は収集のたびに作り直すので、これは作り直す前に残っている古い候補の掃除（作り直した後は何も落とさない）。"""
    names = {i["name"] for i in items}
    return pack_batches([p for p in (load_json(RECOMMEND_FILE) or {}).get("picks", []) if not p.get("work") or p["work"] in names])


SIZE_STORIES = {"S": 3, "M": 5, "L": 8}   # 篇幅 → 每期最多几条报道（网页上直接显示多高见 render.SIZE_HEIGHT）


def load_nav_schemes(settings):
    """板块ごとに選んだ「小分類の分け方」。⚙ 設定ページで選ぶ → Supabase の nav_schemes 表（db/nav_schemes.sql）。
    SUPABASE_SERVICE_KEY があれば表を読み、state/nav_schemes.json に写しを残す（読めなければ前回の写し）。
    候補（settings.sub_schemes）にない値・選んでいない板块は候補の 1 番目。返り値：{板块: 分け方の id}。"""
    chosen = load_json(NAV_SCHEMES_FILE) or {}
    try:
        got = supabase("nav_schemes?select=section,scheme")
        if got is not None:
            chosen = {r["section"]: r["scheme"] for r in got if r.get("section") and r.get("scheme")}
            save_json(NAV_SCHEMES_FILE, chosen)
    except Exception as err:
        hint = "（还没建表？在 Supabase 的 SQL Editor 里运行 db/nav_schemes.sql）" if "PGRST205" in str(err) else ""
        print(f"  [小分類の分け方] 读数据库失败，用上次存的{hint}：{err}", file=sys.stderr)
    out = {}
    for sec, schemes in (settings.get("sub_schemes") or {}).items():
        ids = [x.get("id") for x in schemes or [] if isinstance(x, dict) and x.get("id")]
        if ids:
            out[sec] = chosen.get(sec) if chosen.get(sec) in ids else ids[0]
    return out


def nav_scheme_rows(settings, items):
    """設定ページの「小分類の分け方」：板块ごとに、候補の分け方と、それぞれで分けたときの小分類（件数つき）、いま選んでいるもの。"""
    chosen = load_nav_schemes(settings)
    rows = []
    for sec, schemes in (settings.get("sub_schemes") or {}).items():
        ins = [i for i in items if section_of(i) == sec]
        if not ins:   # 関注項のない板块は網页に出ないので、分け方も選ばせない
            continue
        opts = []
        for x in schemes or []:
            if not (isinstance(x, dict) and x.get("id")):
                continue
            groups = {}
            for i in ins:
                g = sub_of(i, x["id"]) or "その他"
                groups[g] = groups.get(g, 0) + 1
            opts.append({"id": x["id"], "label": x.get("label") or x["id"], "groups": list(groups.items())})
        if opts:
            rows.append({"section": sec, "chosen": chosen.get(sec, opts[0]["id"]), "options": opts})
    return rows


def sub_of(item, scheme):
    """この関注項の小分類（選んだ分け方で）。subs に無ければ旧い sub、それも無ければ subs の最初の値。"""
    subs = item.get("subs") if isinstance(item.get("subs"), dict) else {}
    v = subs.get(scheme) if scheme else None
    return str(v or item.get("sub") or next(iter(subs.values()), "") or "")


@functools.lru_cache(maxsize=None)
def load_sizes():
    """每个关注项的篇幅 S / M / L，在数据库 sizes 表里管理（建表语句在 db/sizes.sql），网页上不显示。
    有 SUPABASE_SERVICE_KEY 时从数据库读，顺便存一份到 state/sizes.json；读不到就用上次存的那份。
    返回 {关注项: "S" | "M" | "L"}，表里没有的关注项按 M。

    不用手动往表里加：数据库里还没有的关注项自动补上一行（items.yaml 写了 size 就用它，没写按 M）；
    items.yaml 的 size 改了（和上次同步的不一样）也自动写进去。在数据库里直接改的，只要 items.yaml 没再改，就一直以数据库为准。"""
    sizes = load_json(SIZES_FILE) or {}
    try:
        got = supabase("sizes?select=item,size")
        if got is not None:
            sizes = {r["item"]: r["size"] for r in got if r.get("size") in SIZE_STORIES}
            sizes.update(_push_sizes(sizes))
            save_json(SIZES_FILE, sizes)
    except Exception as err:
        hint = "（还没建表？在 Supabase 的 SQL Editor 里运行 db/sizes.sql）" if "PGRST205" in str(err) else ""
        print(f"  [篇幅] 读数据库失败，用上次存的{hint}：{err}", file=sys.stderr)
    # 数据库还没有的（没配置、还没建表、刚加的关注项）：先用 items.yaml 写的 size
    for item in load_config()[1]:
        want = str(item.get("size") or "").upper()
        if item["name"] not in sizes and want in SIZE_STORIES:
            sizes[item["name"]] = want
    return sizes


def _push_sizes(db):
    """把数据库里缺的、和 items.yaml 里新改的篇幅写进数据库。返回写进去的 {关注项: 篇幅}。"""
    _, items = load_config()
    pushed = load_json(SIZES_PUSHED_FILE) or {}
    todo = {}
    for item in items:
        want = str(item.get("size") or "").upper()
        if want and want not in SIZE_STORIES:
            print(f"  [篇幅] {item['name']} 的 size 只能是 S / M / L，忽略 {item['size']!r}", file=sys.stderr)
            want = ""
        if item["name"] not in db:
            todo[item["name"]] = want or "M"
        elif want and want != pushed.get(item["name"]) and want != db[item["name"]]:
            todo[item["name"]] = want
    if todo:
        supabase("sizes?on_conflict=item", [{"item": k, "size": v} for k, v in todo.items()],
                 "resolution=merge-duplicates,return=minimal")
        print(f"篇幅：写进数据库 {'、'.join(f'{k}={v}' for k, v in todo.items())}", file=sys.stderr)
    now = {i["name"]: str(i["size"]).upper() for i in items if str(i.get("size") or "").upper() in SIZE_STORIES}
    if now != pushed:
        save_json(SIZES_PUSHED_FILE, now)
    return todo


TASTE_LIMIT = (-6, 4)   # 投票学到的口味最多让一条推荐 -6 ~ +4 分（推荐门槛是 PICK_THRESHOLD）


WORK_KEY = "作品:"   # 口味里按作品（关注项）记的那一类，如「作品:猫用品」


def like_tags(text, wishes, common):
    """一段文字命中愿望清单里哪些具体喜好：(标签, 关键词)，基本属性（马克杯、限定款）不算。"""
    text = text.lower()
    hits, words = set(), set()
    for w in wishes:
        basics = set(w.get("basics") or [])
        for label, kws in w["likes"].items():
            got = {_like_key(k) for k in kws if _like_hit(k, text)} - common
            if got and label not in basics:
                hits.add(label)
                words |= got
    return hits, words


def learn_taste(votes, wishes=(), common=frozenset()):
    """从投票学口味：赞过的消息命中的喜好标签、具体关键词、所属作品各 +1，踩过的各 -1，累加。
    推荐卡片带着推荐时算好的标签；普通消息卡片（kind = story）按标题现算。
    「同类新发现」的标签（如 动画风新作手游）也一样。返回 {标签 / 关键词 / 作品:名字: 分}。"""
    taste = {}
    for r in votes:
        keys = set(r.get("hits") or []) | set(r.get("words") or [])
        if r.get("kind") == "story":
            hits, words = like_tags(r.get("title") or "", wishes, common)
            keys |= hits | words
        if r.get("work") and r.get("kind") in ("story", "wish", "board"):
            keys.add(WORK_KEY + r["work"])
        for k in keys:
            taste[k] = taste.get(k, 0) + r["vote"]
    return {k: v for k, v in taste.items() if v}


def taste_bonus(taste, keys):
    """一条候选按学到的口味加减几分，并列出是哪些标签 / 关键词起的作用（网页上写明理由）。"""
    used = sorted(((k, taste[k]) for k in dict.fromkeys(keys) if k in taste), key=lambda kv: -abs(kv[1]))
    total = max(TASTE_LIMIT[0], min(TASTE_LIMIT[1], sum(v for _, v in used)))
    return total, [[k, v] for k, v in used]



# ---------- 「我会喜欢？」去重：同一件事（哪怕不同语言、不同媒体）只留一条 ----------

STORY_STOP = set("""the and for with new from this that will are more just what about your its how why has have
into after first now gets get you can all out one off not but was his her their they them our who when than then also
over via per each most much many some any very top best returns return here there see""".split())


try:  # 繁体字统一成简体再比（電台 / 电台 是同一个词）
    from opencc import OpenCC
    _to_simplified = OpenCC("t2s").convert
except Exception:  # 没装就不转，照样能用
    def _to_simplified(text):
        return text


def _clean_title(title):
    t = _to_simplified(unicodedata.normalize("NFKC", title)).lower()
    t = re.sub(r"[<＜]?画像\s*\d+\s*/\s*\d+[>＞]?", " ", t)       # 图集前缀「画像6 / 15＞」
    t = re.sub(r"\s*[-|｜–—]\s*[^-|｜–—]{1,40}$", " ", t)          # 结尾的「 - 媒体名」「｜Infoseekニュース」
    return t


def story_tokens(title):
    """标题里能说明「是哪件事」的词：英文词、数字、片假名词、韩文词、汉字两两一组。"""
    t, out = _clean_title(title), set()
    for w in re.findall(r"[a-z][a-z0-9'’\-]{2,}|[a-z]?\d{2,}[a-z]?", t):
        w = w.strip("'’-")
        if w not in STORY_STOP and not re.fullmatch(r"\d{1,2}", w):  # 一两位的数字多半是日期、数量，不说明是哪件事
            out.add(w)
    out |= set(re.findall(r"[\u30a0-\u30ffー]{3,}", t))
    out |= set(re.findall(r"[\uac00-\ud7af]{2,}", t))
    for run in re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]{2,}", t):
        out |= {run[i:i + 2] for i in range(len(run) - 1)}
    return out


def _token_weight(tok):
    return 0.5 if re.fullmatch(r"[\u4e00-\u9fff\u3400-\u4dbf]{2}", tok) else 1.0


def generic_tokens(pool_titles, corpus_titles, items):
    """哪些词太常见、不能拿来认「同一件事」：候选里 8% 以上都有的、最近两周所有消息里 3% 以上都有的、
    关注项自己的名字（关于 GTA 6 的消息都有 gta，不说明是哪件事）。"""
    def df(titles):
        out = {}
        for t in titles:
            for x in story_tokens(t):
                out[x] = out.get(x, 0) + 1
        return out
    pool_df, corpus_df = df(pool_titles), df(corpus_titles)
    generic = {x for x, n in pool_df.items() if n > max(3, len(pool_titles) * 0.08)}
    generic |= {x for x, n in corpus_df.items() if n > max(20, len(corpus_titles) * 0.03)}
    for item in items:
        for w in [item["name"]] + list(item.get("keywords") or []) + list(item.get("match") or []):
            generic |= story_tokens(str(w))
    return generic


class StoryDeduper:
    """同一件事只留一条。两条标题共有的「说明是哪件事的词」够多就算同一件事：
    英文 / 片假名 / 韩文词每个算 1，汉字两两一组算 0.5，合计 2 以上。
    先把所有候选一起分组（A≈B、B≈C 时三条是同一组，哪怕 A 和 C 没有共同的词，例如中文和英文的报道各自只和中间那条像），
    再按重要度一条条问 same()：这一组已经出过一条就返回 True。"""

    def __init__(self, generic, titles):
        self.generic = generic
        self.toks = {t: story_tokens(t) - generic for t in dict.fromkeys(titles)}
        names = list(self.toks)
        parent = {t: t for t in names}

        def find(t):
            while parent[t] != t:
                parent[t] = parent[parent[t]]
                t = parent[t]
            return t
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if self._close(self.toks[a], self.toks[b]):
                    parent[find(b)] = find(a)
        self.group = {t: find(t) for t in names}
        self.used = set()

    @staticmethod
    def _close(a, b):
        return sum(_token_weight(x) for x in a & b) >= 2

    def same_story(self, a, b):
        """两个标题是不是同一件事（不记账，只比较）。"""
        ta = self.toks.get(a)
        tb = self.toks.get(b)
        ta = story_tokens(a) - self.generic if ta is None else ta
        tb = story_tokens(b) - self.generic if tb is None else tb
        return a == b or self.group.get(a, a) == self.group.get(b, b) or self._close(ta, tb)

    def same(self, title):
        g = self.group.get(title)
        if g is None:  # 不在候选里的标题：和已经出过的各组比
            toks = story_tokens(title) - self.generic
            g = next((u for u in self.used if self._close(toks, self.toks.get(u, set()))), title)
            self.toks.setdefault(title, toks)
        if g in self.used:
            return True
        self.used.add(g)
        return False


def page_stories():
    """已经在网页各个版面里的消息：链接集合 + 标题（推荐区不再放它们，同一件事别家的报道也不放）。"""
    urls, titles = set(), []
    for path in REPORTS_DIR.glob("????-??-??.json"):
        for b in (load_json(path) or {}).get("items", []):
            for st in b.get("stories") or []:
                urls.add(st["url"])
                titles.append(st.get("headline") or "")
    return urls, [t for t in titles if t]


def recommend(force_discover=False):
    """「我会喜欢？」：从最近收集到的消息里挑推荐，写进 state/recommend.json，网页读它。四种来源，每条写明真实的理由：
    - wish：标题命中愿望清单里某件东西的喜好标签（likes），够分才推荐 →「因为你想要「那件东西」」；
    - board：关注的版面里收集到、但没上版面的其他消息（按投票学到的口味排）→「你关注的「作品」还有这条」；
    - follow / hesitate：同类新发现（见 discover）；
    赞过的消息和候选有共同的喜好 / 是同一个作品时，理由写「因为你赞过「那条」」。
    已经在网页版面里的消息（和别家报道的同一件事）不推荐：版面里已经看得到。不让 AI 联网，只用收集到的消息。"""
    wishes = [w for w in load_wishlist() if w.get("likes")]
    common = {_like_key(k) for w in wishes for label, kws in w["likes"].items()
              if label in (w.get("basics") or []) for k in kws}
    old = load_json(RECOMMEND_FILE) or {}
    # 配图缓存：找到的图一直用；没找到的（None）只当天不再找，第二天重新找（网站修好了、找图规则改进了都能补上）
    today = dt.date.today().isoformat()
    misses = {u: d for u, d in (old.get("image_misses") or {}).items() if d == today}
    images = {u: i for u, i in old.get("images", {}).items() if i or u in misses}
    wish_urls = {w.get("url") for w in wishes}
    votes = load_feedback()
    taste = learn_taste(votes, wishes, common)
    disliked = {r["url"] for r in votes if r["vote"] < 0}
    disliked_grams = [_title_grams(r.get("title") or "", []) for r in votes if r["vote"] < 0]
    liked = [r for r in votes if r["vote"] > 0 and r.get("title")]
    voted = {r["url"] for r in votes}  # 投过票的都看过了：不再推荐（赞过的拿来找相关的新消息）
    liked_keys = []
    # 「和你赞过的哪条有关」只看具体的关键词（Snoopy、Galaxy……）：喜好标签、同类的大类（动物 / 角色造型、超级英雄电影）太宽，
    # 同一类的每条都会说成和赞过的那条有关（IVE 的新专辑被说成和 Clayface 有关）。大类的口味加分另外显示在「あなたの投票」里
    for r in liked:
        keys = set(r.get("words") or [])
        if r.get("kind") == "story":
            keys |= like_tags(r["title"], wishes, common)[1]
        liked_keys.append((r, keys - common - {b for w in wishes for b in w.get("basics") or []}))

    def liked_reason(url, title, keys, work):
        """赞过的哪一条和这条有关（共同的具体喜好，或者同一个关注的作品）：网页上写「因为你赞过「那条」」。"""
        for r, rk in liked_keys:
            if r["url"] == url or dedupe.same_story(r["title"], title):
                continue
            if keys & rk or (work and r.get("work") == work and r.get("kind") in ("story", "wish", "board")):
                return r["title"]
        return None

    on_page, page_titles = page_stories()
    found = sorted(discover(force_discover, taste), key=lambda x: x.get("date") or "", reverse=True)
    probes = [x for x in found if x.get("probe")]
    found = [x for x in found if not x.get("probe")]
    entries = [(d, path.stem, item["name"]) for path in sorted(INBOX_DIR.glob("????-??-??.json"))[-PICK_DAYS:]
               for item in load_json(path)["items"] for d in item["entries"]]
    recent = sorted(INBOX_DIR.glob("????-??-??.json"))[-BOARD_DAYS:]
    recent = {p.stem for p in recent}
    pool, board = [], {}
    for d, day, work in entries + [(x, (x.get("date") or "")[:10], None) for x in probes]:
        if is_spam(d["title"], d.get("link") or d["url"]):
            continue   # 垃圾页（被黑的网站批量生成的）不推荐
        if d["url"] in on_page or d.get("link") in on_page:
            page_titles.append(d["title"])  # 版面里那条的原标题（版面上是改写过的中文标题）
            continue
        # 只看标题：摘要里顺带提到的词（Bad Bunny、某某巡演）不说明这条消息是关于它的
        text = d["title"].lower()
        best = None
        for w in wishes:
            hits = [label for label, kws in w["likes"].items() if any(_like_hit(k, text) for k in kws)]
            words = {_like_key(k) for kws in w["likes"].values() for k in kws if _like_hit(k, text)}
            score = 2 * len(hits) + (1 if work and w.get("watch") == work else 0)
            # 学到的口味只看具体的喜好，基本属性（马克杯、限定款）不跟着投票涨跌
            basics = set(w.get("basics") or [])
            bonus, why = taste_bonus(taste, [h for h in hits if h not in basics] + sorted(words - common)
                                     + ([WORK_KEY + work] if work else []))
            # 至少命中一个具体喜好：只命中基本属性（马克杯、限定）的说明不了是因为那件东西
            # 关注的版面里的消息要命中两个以上喜好才算「因为你想要」（只命中一个的，例如漫威新闻里的 Squirrel Girl，
            # 和那件东西扯不上关系，当作版面的其他消息推荐）
            if any(h not in basics for h in hits) and (not work or len(hits) >= 2) \
                    and (not best or score + bonus > best[0]):
                best = (score + bonus, w, hits, words, why)
        if best and best[0] >= PICK_THRESHOLD - 1:
            pool.append((best[0], d.get("date") or day, d, work or best[1].get("watch") or best[1]["name"], *best[1:]))
        elif work and day in recent and not sources.is_sns(entry_from_dict(d)):  # 网友的帖子（提问、闲聊）不当推荐
            hits, words = like_tags(d["title"], wishes, common)
            bonus, why = taste_bonus(taste, sorted(hits | words) + [WORK_KEY + work])
            board.setdefault(work, []).append((BOARD_SCORE + bonus, d.get("date") or day, d, work, hits, words, why))
    # 同分时，命中具体喜好（猫、角色造型……）的排在只命中基本属性（限定、马克杯）的前面
    pool.sort(key=lambda x: (x[0], len(set(x[5]) - set(x[4].get("basics") or [])), x[1]), reverse=True)
    # 每个关注项先挑最新的几条（有图的优先）再一起去重：候选太多时两两比标题很慢
    board = [c for cs in board.values()
             for c in sorted(cs, key=lambda c: (bool(c[2].get("image")), c[1]), reverse=True)[:BOARD_PER_ITEM * 3]]
    _, items_conf = load_config()
    corpus = [d["title"] for d, _, _ in entries]
    cand_titles = [x[2]["title"] for x in pool] + [x[2]["title"] for x in board] + [x["title"] for x in found]
    titles = page_titles + [r["title"] for r in votes if r.get("title")] + cand_titles
    dedupe = StoryDeduper(generic_tokens(cand_titles, corpus, items_conf), titles)
    for t in page_titles:
        dedupe.same(t)  # 版面里已经有的那件事（别家的报道也算）不再推荐
    for r in votes:
        if r.get("title"):
            dedupe.same(r["title"])  # 投过票的那件事（别家的报道也算）不再推荐：踩过的不想看，赞过的已经看过了
    picks, grams, used = [], list(disliked_grams), set()

    def taken(url):
        return url in on_page or url in wish_urls or url in voted or any(p["url"] == url for p in picks)

    for score, date, d, work, w, hits, words, why in pool:
        g = _title_grams(d["title"], [])
        key = words - common
        if len(picks) % PICK_COUNT == 0:
            used = set()  # 每一批各自分散
        # 推荐要分散：同一批里两条靠同一个具体关键词命中（如都是 Snoopy）只留一条；basics 里的基本属性（限定、马克杯）不算
        # 踩过的消息（和别家报道的同一件事）不再推荐
        if any(_similar(g, x) for x in grams) or key & used:
            continue
        if dedupe.same(d["title"]):
            continue  # 同一件事已经有一条了（不同媒体、不同语言的报道），或者版面里已经有了
        explore = score < PICK_THRESHOLD  # 候选按分数排好了，「换换口味」的排在够分的后面
        url = sources.resolve_url(d.get("link") or d["url"])
        if taken(url):
            continue
        used |= key
        if url not in images:
            images[url] = find_image(d.get("image"), [entry_from_dict(d)], url)
        grams.append(g)
        picks.append({"title": d["title"], "url": url, "source": d["source"], "date": date[:10], "work": work,
                      "image": images[url], "because": w["name"], "hits": hits, "score": score, "kind": "wish",
                      "words": sorted(key), "taste": why,
                      "batch": max(len(picks) // PICK_COUNT, EXPLORE_AFTER if explore else 0),  # 没有脚本时不先给看
                      **({"explore": True} if explore else {}),
                      **({"hesitating": True} if w.get("status") == HESITATE else {})})
        if len(picks) >= PICK_COUNT * PICK_BATCHES:
            break

    # 关注的版面里没上版面的其他消息：口味分高的先（赞过同一个作品的加分），每个关注项最多 BOARD_PER_ITEM 条；
    # 净踩过的作品（口味分把基础分扣到「换换口味」以下）不推荐
    boards, per = [], {}
    for score, date, d, work, hits, words, why in sorted(board, key=lambda c: (c[0], c[1]), reverse=True):
        if score < BOARD_SCORE or per.get(work, 0) >= BOARD_PER_ITEM:
            continue
        g = _title_grams(d["title"], [])
        if any(_similar(g, x) for x in grams) or dedupe.same(d["title"]):
            continue
        url = sources.resolve_url(d.get("link") or d["url"])
        if taken(url) or any(b["url"] == url for b in boards):
            continue
        if url not in images:
            images[url] = find_image(d.get("image"), [entry_from_dict(d)], url)
        grams.append(g)
        per[work] = per.get(work, 0) + 1
        boards.append({"title": d["title"], "url": url, "source": d["source"], "date": date[:10], "work": work,
                       "image": images[url], "because": work, "hits": sorted(hits), "score": score, "kind": "board",
                       "words": sorted(words), "taste": why, "batch": 1 + len(boards) // PICK_COUNT,
                       **({"liked": t} if (t := liked_reason(url, d["title"], set(words), work)) else {})})
    picks += boards
    picks = pack_batches(picks)

    # 同类新消息：按关注项轮流取最新的一条（有图的优先），每个关注项最多一条。
    # 投票学到的口味决定先后：常赞的同类排前面，净踩两次以上的同类先不推荐
    found = [x for x in found if not any(_similar(_title_grams(x["title"], []), g) for g in disliked_grams)]
    names = list(dict.fromkeys(x["item"] for x in found))
    label_of = {x["item"]: x["label"] for x in found}
    names = [n for n in names if taste.get(label_of[n], 0) > -2]
    names.sort(key=lambda n: -taste.get(label_of[n], 0))  # sort 是稳定的：同分时保持按时间
    # 每个关注项准备最多 FOLLOW_PER_ITEM 条（有图的优先），再轮流排：每一批里尽量是不同的关注项
    cands, seen_urls = {}, {p["url"] for p in picks}
    for name in names:
        got = []
        for x in [x for x in found if x["item"] == name][:FOLLOW_PER_ITEM * 2]:
            url = sources.resolve_url(x["url"])
            if url in voted or url in seen_urls or url in on_page or dedupe.same(x["title"]):
                continue
            if url not in images:
                images[url] = find_image(x.get("image"), [entry_from_dict(x)], url)
            seen_urls.add(url)
            got.append((x, images[url], url))
        got.sort(key=lambda c: not c[1])  # 有图的排前面（sort 是稳定的：同样有图时保持按时间）
        cands[name] = got[:FOLLOW_PER_ITEM]
    order = [c for r in range(FOLLOW_PER_ITEM) for n in names if len(cands[n]) > r for c in [cands[n][r]]]
    follow = []
    for x, img, url in order[:DISCOVER_PICKS * PICK_BATCHES]:
        words = sorted(like_tags(x["title"] + " " + (x.get("summary") or ""), wishes, common)[1])
        follow.append({"title": x["title"], "url": url, "source": x["source"], "date": (x.get("date") or "")[:10],
                       "work": x["item"], "image": img, "because": x["item"], "hits": [x["label"]],
                       "kind": "hesitate" if x.get("wish") else "follow", "batch": len(follow) // DISCOVER_PICKS,
                       "words": words, "taste": taste_bonus(taste, [x["label"]])[1],
                       **({"liked": t} if (t := liked_reason(url, x["title"], set(words), None)) else {})})
    picks += follow
    keep = {p["url"] for p in picks}
    # 投票から学んだ口味の上位（トップの右の「あなたの好み」に出す）
    top = sorted(((k, v) for k, v in taste.items() if v > 0), key=lambda kv: -kv[1])[:8]
    misses.update({u: today for u, i in images.items() if not i and u not in misses})
    save_json(RECOMMEND_FILE, {"picks": picks, "images": {u: i for u, i in images.items() if u in keep},
                               "image_misses": {u: d for u, d in misses.items() if u in keep},
                               "taste": [[k, v] for k, v in top]})
    print(f"我会喜欢？：{len(picks) - len(follow) - len(boards)} 条按愿望清单 + {len(boards)} 条关注版面的其他消息 + "
          f"{len(follow)} 条同类新消息（学自 {len(votes)} 次投票，{len(liked)} 次赞）", file=sys.stderr)


def with_new_items(issues, items):
    """刚加的关注项（items.yaml 里有、但还没有任何一期简报收录）：先在最新一期里放一个「正在收集新闻」的小栏，
    设置页一提交、网页一重新生成，首页上马上就有它的版面；收集完出刊后换成真正的报道。
    只改这次生成网页用的数据，不写回 reports/。"""
    shown = {b["name"] for issue in issues for b in issue.get("items", [])}
    new = [i for i in items if i["name"] not in shown]
    if not new:
        return issues
    themes = load_json(THEMES_FILE) or {}
    blocks = [{"name": i["name"], "section": section_of(i), "subtitle": i.get("subtitle", ""),
               "theme": theme.resolve(i, None, themes), "quiet": True, "collecting": True,
               "status": "刚加进关注清单，正在收集新闻，几分钟后这里会换成报道",
               "cover": None, "last": None, "facts": [], "stories": []} for i in new]
    return [{**issues[0], "items": issues[0]["items"] + blocks}] + issues[1:]


def with_manual_themes(issues, items):
    """items.yaml に手で書いた theme（小元素に合わせた配色など）を、次の収集を待たずに網页へ反映する。
    版面の見た目は最新の一期で決まるので、最新の一期の版面だけを上書きする。reports/ には書き戻さない。
    板块（section）も items.yaml の今の値にする（板块を移した関注項が、次の出刊を待たずに新しい板块に出る）。
    設定ページで消した関注項の版面も次の出刊を待たずに消える。"""
    manual = {i["name"]: i["theme"] for i in items if isinstance(i.get("theme"), dict)}
    secs = {i["name"]: section_of(i) for i in items}
    if not issues:
        return issues
    blocks = [{**b, "theme": {**(b.get("theme") or {}), **manual[b["name"]]}} if b.get("name") in manual else b
              for b in issues[0].get("items", [])]
    blocks = [{**b, "section": secs[b["name"]]} for b in blocks if b.get("name") in secs]   # 消した関注項の版面は出さない
    return [{**issues[0], "items": blocks}] + issues[1:]

ADMIN_ID_BY_TYPE = {"game": "steam_appid", "anime": "anilist_id", "show": "tmdb"}  # 種類ごとに、あると話題度・現状が取れる ID


def emblem_status(item):
    """管理ページ用：小元素の種類・目標・枚数・内訳（scripts/emblem_fill.py と同じ規則）。"""
    import emblem_fill
    st = emblem_fill.status(item)
    shapes = {}
    for x in item.get("emblem") or []:
        if isinstance(x, dict):
            k = {"cutout": "切り抜き", "badge": "カード", "logo": "ロゴ", "icon": "アイコン"}.get(x.get("shape"), x.get("shape") or "?")
            shapes[k] = shapes.get(k, 0) + 1
    return {**st, "kind_ja": emblem_fill.KIND_JA[st["kind"]], "shapes": shapes}


def edit_diff(inbox_path):
    """管理ページ「AI 編集の前後」：その日の収集（inbox）と AI 編集（edit.json）を比べる。
    作品ごとに、集めた件数・記事に使った件数（refs）・載せた記事の本数・hero / lead・AI が選んだ配図、
    整理待ち（new：_covered より後の、または edit.json にない版面の全件。版面には載らない）と、そのうち要紧で先に載せたもの（urgent）。"""
    if not inbox_path:
        return None
    raw = load_json(inbox_path) or {}
    edit_path = inbox_path.with_name(f"{inbox_path.stem}.edit.json")
    edit = (load_json(edit_path) if edit_path.exists() else None) or {}
    covered = edit.get("_covered") or {}
    rows = []
    for block in raw.get("items", []):
        name = block.get("name")
        entries = block.get("entries") or []
        ns = {x.get("n") for x in entries}
        total = len(entries)
        stories = [x for x in (edit.get(name) or []) if isinstance(x, dict)]
        used = {r for x in stories for r in x.get("refs") or [] if r in ns}
        cov = min(total, int(covered[name] or 0) if name in covered else total if name in edit else 0)   # publish と同じ読み方
        rows.append({"name": name, "total": total, "used": min(len(used), total), "stories": len(stories),
                     "hero": sum(1 for x in stories if x.get("weight") == "hero"),
                     "lead": sum(1 for x in stories if x.get("weight") == "lead"),
                     "images": sum(1 for x in stories if x.get("image")),
                     "new": total - cov,
                     "urgent": sum(1 for x in entries if x.get("urgent") and int(x.get("n") or 0) > cov)})
    rows.sort(key=lambda r: (-r["total"], r["name"]))
    return {"date": inbox_path.stem, "edited": bool(edit), "rows": rows,
            "total": sum(r["total"] for r in rows), "used": sum(r["used"] for r in rows),
            "stories": sum(r["stories"] for r in rows), "images": sum(r["images"] for r in rows),
            "hero": sum(r["hero"] for r in rows), "new": sum(r["new"] for r in rows),
            "urgent": sum(r["urgent"] for r in rows)}


def admin_data(items, issues, analysis, tz, updated):
    """管理ページ（docs/admin.html）に書き込む数字：収集・編集の状況、作品ごとの記事数と未設定の項目、投票。"""
    today = dt.datetime.now(tz).date()
    inbox = sorted(INBOX_DIR.glob("????-??-??.json"))
    week, urgent, last = {}, {}, {}
    today_n = week_n = 0
    for path in inbox:
        day = dt.date.fromisoformat(path.stem)
        recent = (today - day).days < 7
        for block in (load_json(path) or {}).get("items", []):
            entries = block.get("entries") or []
            name = block.get("name")
            if recent:
                week[name] = week.get(name, 0) + len(entries)
                urgent[name] = urgent.get(name, 0) + sum(1 for x in entries if x.get("urgent"))
                week_n += len(entries)
                if day == today:
                    today_n += len(entries)
            for x in entries:
                d = (x.get("date") or "")[:10] or path.stem
                if d <= today.isoformat() and d > last.get(name, ""):
                    last[name] = d
    unedited = [p.stem for p in inbox[-7:] if not (INBOX_DIR / f"{p.stem}.edit.json").exists()]
    heat_items = (analysis or {}).get("items") or {}
    rows = []
    for i in items:
        name = i["name"]
        need = ["motif", "emblem", "wiki", "status", "similar"]
        if ADMIN_ID_BY_TYPE.get(i.get("type")):
            need.append(ADMIN_ID_BY_TYPE[i["type"]])
        h = heat_items.get(name)
        rows.append({"name": name, "section": section_of(i), "type": i.get("type"), "size": load_sizes().get(name, "M"),
                     "week": week.get(name, 0), "urgent": urgent.get(name, 0),
                     "last_days": (today - dt.date.fromisoformat(last[name])).days if name in last else None,
                     "heat": {"score": h["score"], "delta": h.get("delta")} if h else None,
                     "missing": [k for k in need if not i.get(k)], "web": WEB_ITEM_MARK in str(i.get("notes") or ""),
                     "emblem": emblem_status(i)})
    beat = (STATE_DIR / "heartbeat.txt")
    pipeline = {"report": issues[0]["date"] if issues else None, "inbox": inbox[-1].stem if inbox else None,
                "today_entries": today_n, "week_entries": week_n, "unedited": unedited, "updated": updated,
                "items": len(items), "stale": sum(1 for r in rows if r["last_days"] is None or r["last_days"] >= render.ADMIN_STALE_DAYS),
                "weekly": " ".join(beat.read_text(encoding="utf-8").split()[:2])[5:].replace("-", "/") if beat.exists() else None}
    # 投票：同じ記事は最後の一票。作品ごとの 👍 / 👎 と、最近押したもの
    raw = (load_json(FEEDBACK_FILE) or {}).get("rows", [])
    latest = {}
    for r in raw:
        if r.get("url") and r.get("vote") in (-1, 0, 1):
            latest[r["url"]] = r
    now_votes = [r for r in latest.values() if r["vote"]]
    by_work = {}
    for r in now_votes:
        k = r.get("work") or r.get("because") or "（その他）"
        a, b = by_work.get(k, (0, 0))
        by_work[k] = (a + (r["vote"] > 0), b + (r["vote"] < 0))

    def stamp(s):
        try:
            return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(tz)
        except ValueError:
            return None
    times = [t for t in (stamp(r.get("created_at")) for r in raw) if t]
    recent = sorted(now_votes, key=lambda r: str(r.get("created_at") or ""), reverse=True)[:10]
    votes = {"total": len(now_votes), "up": sum(1 for r in now_votes if r["vote"] > 0),
             "down": sum(1 for r in now_votes if r["vote"] < 0),
             "week": sum(1 for t in times if (today - t.date()).days < 7),
             "last": max(times).strftime("%m/%d %H:%M") if times else None,
             "works": sorted(((k, a, b) for k, (a, b) in by_work.items()), key=lambda x: (-(x[1] + x[2]), x[0]))[:10],
             "recent": [{**{k: r.get(k) for k in ("url", "title", "work", "kind", "vote")},
                         "when": t.strftime("%m/%d %H:%M") if (t := stamp(r.get("created_at"))) else ""} for r in recent]}
    run = emblem_progress(items, tz)
    backend_cells(items, rows, inbox[-1] if inbox else None, run)
    return {"pipeline": pipeline, "items": rows, "votes": votes, "emblem_run": run,
            "edit_diff": edit_diff(inbox[-1] if inbox else None),
            "todo": backend_todo(items, rows, run), "log": backend_log(tz), "edit_tokens": edit_tokens(tz), "resources": backend_resources(tz)}


def backend_resources(tz, days=7):
    """「リソース」：リポジトリと公開ページの大きさ（上限と比べる）、仕組みごとの最近の実行のサーバーの様子、トークン。"""
    import resources
    import runlog
    today = dt.datetime.now(dt.timezone.utc)
    runs, tokens = {}, {}
    for proc, name in runlog.PROCS.items():
        rows = runlog.load(proc)
        last = next((r for r in reversed(rows) if r.get("res")), None)
        if last:
            try:
                when = dt.datetime.fromisoformat(last["at"]).astimezone(tz).strftime("%m/%d %H:%M")
            except (KeyError, ValueError):
                when = ""
            runs[proc] = {"name": name, "when": when, "secs": last.get("secs"), "workers": last.get("workers"), "res": last["res"]}
        week = []
        for r in rows:
            try:
                if r.get("tokens") and (today - dt.datetime.fromisoformat(r["at"])).days < days:
                    week.append(int(r["tokens"]))
            except (KeyError, ValueError):
                pass
        tok = [r for r in rows if r.get("tokens")]
        tokens[proc] = {"name": name, "last": int(tok[-1]["tokens"]) if tok else None, "week": sum(week), "runs": len(week)}
    return {"sizes": resources.repo_sizes(), "limits": resources.LIMITS, "runs": runs, "tokens": tokens}


def backend_todo(items, rows, run):
    """「待ち行列」：次の回にそれぞれの仕組みが何をするか（版面の名前つき）。"""
    edit = [r for r in rows if (r.get("bg") or {}).get("edit", {}).get("state") == "wait"]
    design = [r["name"] for r in rows if (r.get("bg") or {}).get("design", {}).get("state") == "wait"]
    n_new = sum(int(re.search(r"\d+", r["bg"]["edit"]["text"]).group()) for r in edit if re.search(r"\d+", r["bg"]["edit"]["text"]))
    import gate
    gj = (gate.load().get("jobs") or {}).get("edit") or {}
    fired = gj.get("fired") or {}   # ゲートが最後に AI 編集を起こした記録
    lb, le = gate.last_batch(), gate.last_error()
    gstate, gwhy = gate.work_state(gj, last_batch=lb, last_error=le)   # 起こしたあとに本当に進んだか（running / progress / idle / unpublished / stalled / gave_up）。動いているかは最後のバッチの時刻で
    queue = run.get("queue") or []
    review = [n for n, x in (run.get("items") or {}).items() if x["state"] == "review"]
    return {
        "collect": {"text": f"全 {len(items)} 版面の記事を集める", "items": []},
        "edit": {"text": (f"新しい記事 {n_new} 件（{len(edit)} 版面）を編集" if edit else "編集する新着なし")
                 + (f" · 版面の設計 {len(design)} 件" if design else ""), "items": [r["name"] for r in edit],
                 "n": n_new, "boards": len(edit), "fired": fired.get("at") or "",
                 "state": gstate, "why": gwhy, "due": gate.due_slot(gj, last_batch=lb, last_error=le),   # due：今の回（まだ起こしていない）の時刻
                 "attempts": int(fired.get("attempts") or 0), "resp": fired.get("resp") or ""},
        "emblem-cron": {"text": (f"足りない {len(queue)} 版面を順に" if queue else "全部そろっている")
                        + (f" · 要確認 {len(review)}" if review else ""), "items": queue},
        "photos": {"text": "受付の写真があれば認識して愿望清单へ", "items": []},
        "gate": {"text": (f"小元素 {len(queue)} 版面を Python で（AI なし）" if queue else "小元素の仕事なし")
                 + (f" · AI 編集の仕事 {len(edit)} 版面" if edit else "") + " · AI が要る仕事があるときだけ Claude", "items": queue},
    }


def edit_tokens(tz, days=7):
    """管理ページ「AI 編集のトークン」：AI 編集の回（セッション）ごとに、バッチごとの版面・本数・トークン（state/log/edit.json の tok）。
    → {"runs": [{"when", "batches": [...], "sum": {...}}…（新しい順）], "today": 合計, "week": 合計}。"""
    import runlog
    import usage
    now = dt.datetime.now(tz)
    runs, today, week = {}, {}, {}
    for r in runlog.load("edit"):
        tok = r.get("tok")
        if not isinstance(tok, dict):
            continue
        try:
            at = dt.datetime.fromisoformat(r["at"]).astimezone(tz)
        except (KeyError, ValueError):
            continue
        key = str(r.get("run") or r["at"])
        g = runs.setdefault(key, {"when": at.strftime("%m/%d %H:%M"), "at": r["at"], "batches": [], "sum": {}})
        g["batches"].append({"when": at.strftime("%H:%M"), "batch": r.get("batch"), "boards": r.get("boards") or [],
                             "stories": r.get("stories"), "tok": tok, "total": usage.total(tok)})
        for k in usage.KEYS:
            g["sum"][k] = g["sum"].get(k, 0) + int(tok.get(k) or 0)
            if (now - at).days < days:
                week[k] = week.get(k, 0) + int(tok.get(k) or 0)
            if at.date() == now.date():
                today[k] = today.get(k, 0) + int(tok.get(k) or 0)
    out = sorted(runs.values(), key=lambda g: g["at"], reverse=True)[:10]
    return {"runs": out, "today": today, "week": week}


def backend_log(tz, n=40):
    """実行ログ（state/log/*.json）を新しい順に。時刻は表示用に現地時間へ。"""
    import runlog
    out = []
    for r in runlog.recent(n):
        try:
            when = dt.datetime.fromisoformat(r["at"]).astimezone(tz).strftime("%m/%d %H:%M")
        except (KeyError, ValueError):
            when = ""
        out.append({"when": when, "at": r.get("at") or "", "proc": r["proc"], "name": r["name"], "level": r.get("level", "info"), "text": r.get("text", "")})
    return out


DESIGN_KEYS = (("motif", "テーマ"), ("theme", "配色"))   # like_fx は書かなければテーマの演出なので要らない


def backend_cells(items, rows, latest, run):
    """管理ページ「バックグラウンド」の表：版面（行）× プロセス（列）の今の状態を rows[i]["bg"] に書く。
    状態：ok 済 / wait 待ち（次の回で動く）/ review 要確認 / failed 失敗 / idle 対象なし。
      collect  最新の収集（inbox）にその版面の記事が何件あるか
      edit     その日の AI 編集（edit.json の _covered）がその件数まで編集したか
      design   版面の設計（motif・theme）がそろっているか（足りなければ次の AI 編集で）
      emblem   小元素の自動補完の状態（state/emblem_progress.json）と、順番待ちなら何番目か"""
    day = latest.stem if latest else None
    got = {b.get("name"): len(b.get("entries") or []) for b in ((load_json(latest) or {}).get("items") or [])} if latest else {}
    edit = load_json(INBOX_DIR / f"{day}.edit.json") if day else None
    covered = (edit or {}).get("_covered") or {}
    by_name = {i["name"]: i for i in items}
    eprog = run.get("items") or {}
    queue = run.get("queue") or []
    import emblem_fill
    raw = emblem_fill.load_progress().get("items") or {}   # 時刻（UTC）・failed_at・漏斗の数字はこちらから
    rejects = {}   # 管理ページの「違う」の記録（理由つき）→ 版面ごと
    for x in (load_json(EMBLEM_REJECTS_FILE) or {}).get("rows") or []:
        rejects.setdefault(x.get("board"), []).append(x)
    md = (lambda d: f"{int(d[5:7])}/{int(d[8:10])}") if day else (lambda d: "")
    for r in rows:
        name, item = r["name"], by_name.get(r["name"]) or {}
        n = got.get(name, 0)
        cells = {"collect": ("ok", f"{md(day)} {n} 件") if n else ("idle", f"{md(day)} 新着なし" if day else "まだ収集なし")}
        if not n:
            cells["edit"] = ("idle", "編集するものなし")
        elif edit is None:
            cells["edit"] = ("wait", f"整理待ち {n} 件（今日まだ AI 編集なし）")
        else:
            c = int(covered.get(name) or 0)
            cells["edit"] = ("ok", f"{n} 件 編集済み") if c >= n else ("wait", f"整理待ち {n - c} 件（今日 {n} 件のうち）")
        miss = [ja for k, ja in DESIGN_KEYS if not item.get(k)]
        cells["design"] = ("ok", "設計済み") if not miss else ("wait", "未設定：" + "・".join(miss))
        em = r.get("emblem") or {}
        st = (eprog.get(name) or {}).get("state") or ("ok" if em.get("state") == "ok" else "running")
        count = f'{em.get("have", 0)}/{em.get("target", 0)} 枚'
        if st == "ok":
            cells["emblem"] = ("ok", count)
        elif st == "review":
            cells["emblem"] = ("review", f"{count} · 一覧から選ぶ")
        elif st == "failed":
            cells["emblem"] = ("failed", f"{count} · 新しい材料が来たらすぐ・来なくても {emblem_fill.RETRY_HOURS} 時間後に再挑戦")
        else:
            pos = queue.index(name) + 1 if name in queue else None
            cells["emblem"] = ("wait", f"{count} · 順番 {pos} 番目" if pos else count)
        r["bg"] = {k: {"state": a, "text": b} for k, (a, b) in cells.items()}
        r["bg"]["emblem"]["detail"] = emblem_detail(item, raw.get(name) or {}, st, queue, run.get("tz"))
        r["bg"]["emblem"]["detail"]["reject_log"] = rejects.get(name, [])
        r["thumbs"] = [(x["image"], x.get("shape") or "", x.get("subject") or "") for x in item.get("emblem") or [] if isinstance(x, dict)
                       and re.fullmatch(r"https?://\S+|emblems/[a-z0-9-]+\.webp", str(x.get("image") or ""))]   # 全部（表の行は先頭だけ、「小元素の探し方」を開くと全部）


def _next_slot(after, slots):
    """after（UTC の datetime）より後の、いちばん近い定時（UTC の [時, 分] のリスト）。"""
    best = None
    for k in range(0, 3):
        for h, m in slots:
            t = (after + dt.timedelta(days=k)).replace(hour=h, minute=m, second=0, microsecond=0)
            if t > after and (best is None or t < best):
                best = t
    return best


def emblem_detail(item, entry, state, queue, tz_name=None):
    """管理ページ「小元素の探し方」：その版面で、何を目標に、どの取り方を順に試し、何枚残り、次に何をするか。
    取り方の列 = emblem_fill.source_chain（試した数は進捗の tried）。次の回 = 定時（processes の emblem-cron）。"""
    import emblem_fill
    import processes
    tz = zoneinfo.ZoneInfo(tz_name or "Asia/Tokyo")
    st = emblem_fill.status(item) if item else {}
    kind = st.get("kind", "topic")
    tried = entry.get("tried") or {}
    chain = [{"src": src, "auto": auto, "n": tried.get(src)} for src, auto in emblem_fill.source_chain(item or {})]
    known = {c["src"] for c in chain}   # 実際に試したのに一覧にない取り方（実写の作品の「役の記事」「作品の動画の場面」など）も出す。
    chain[1:1] = [{"src": k, "auto": True, "n": v} for k, v in tried.items() if k not in known]   # 出さないと「まだ試していない」と誤って出る
    who = item.get("emblem_who") or []
    why = {"person": "本人の別の写真", "group": f"メンバー {len(who)} 人" if who else "メンバー全員",
           "character": (f"出演者 {len(who)} 人" if item.get("emblem_people") else f"キャラ {len(who)} 人") if who else "主役級のキャラ",
           "brand": "公式ロゴ", "topic": "主題を表す物"}.get(kind, "")
    now = dt.datetime.now(dt.timezone.utc)
    slots = processes.slots(next(p for p in processes.PROCESSES if p["id"] == "emblem-cron")) or [[h, 47] for h in range(24)]
    after = now
    if state == "failed" and entry.get("failed_at"):
        try:
            after = max(now, dt.datetime.fromisoformat(entry["failed_at"]) + dt.timedelta(hours=emblem_fill.RETRY_HOURS))
        except ValueError:
            pass
    nxt = _next_slot(after, slots) if slots and state != "ok" else None
    when = nxt.astimezone(tz).strftime("%m/%d %H:%M") if nxt else ""
    found = sum(v for v in tried.values() if v)
    if state == "ok":
        todo = "そろっている（足りなくなったら次の回に）"
    elif state == "review":
        todo = f"一覧から手で選べる（python scripts/emblem_fill.py \"{item.get('name')}\" --commit 番号）"
    elif state == "failed":
        todo = f"新しい記事・手がかりが来たらすぐ、来なくても {when} に再挑戦"
    else:
        pos = queue.index(item.get("name")) + 1 if item.get("name") in queue else None
        todo = f"次の回 {when} に" + (f"（順番 {pos} 番目）" if pos else "")
    advice = ""
    if state in ("failed", "review") or (state == "running" and entry.get("at")):
        if item.get("emblem_urls"):
            advice = ""
        elif emblem_fill.needs_face(item) and sum(tried.get(s) or 0 for s in ("Wikidata", "Wikipedia")) <= 1 and not st.get("have"):
            advice = "Wikipedia・Wikidata に本人の記事・写真がない → 公式サイトの写真を emblem_urls に書くと確実"
        elif kind == "character" and not item.get("emblem_people") and not item.get("emblem_fandom"):
            advice = "キャラの Fandom（emblem_fandom）か公式の立ち絵（emblem_urls）を書くと自動で埋まる"
        elif kind == "brand":
            advice = "Wikidata に公式ロゴ（P154）がない → 公式サイトのロゴを emblem_urls に"
        elif kind == "topic" and not item.get("emblem_icon"):
            advice = "emblem_icon に絵文字を書くと Twemoji で埋まる"
        elif found and not (entry.get("funnel") or {}).get("added"):
            advice = "候補はあるが規則で外れた（理由は ③）→ 確かな画像を emblem_urls に書くと確実"
    try:
        at = dt.datetime.fromisoformat(entry["at"]).astimezone(tz).strftime("%m/%d %H:%M") if entry.get("at") else ""
    except ValueError:
        at = ""
    return {"kind": emblem_fill.KIND_JA.get(kind, kind), "why": why, "target": st.get("target"), "have": st.get("have"),
            "lo": st.get("lo"), "hi": st.get("hi"), "chain": chain, "funnel": entry.get("funnel") or {},
            "faces": emblem_fill.needs_face(item) if item else False, "rejects": len(item.get("emblem_reject") or []),
            "note": entry.get("note") or "", "at": at, "todo": todo, "advice": advice,
            "next_at": nxt.isoformat() if nxt and state == "failed" else ""}   # 失敗の自動の再挑戦（管理ページで残り時間を数える）


def emblem_progress(items, tz):
    """管理ページの「進捗」：小元素の定時の自動補完（emblem_fill.py --background）が残した state/emblem_progress.json。
    枚数は items.yaml の今の値で数え直す（後で AI が一覧から選んだ分も入る）。時刻は表示用に現地時間へ。"""
    import emblem_fill
    prog = emblem_fill.sync_progress(emblem_fill.load_progress(), items)

    def local(s):
        try:
            return dt.datetime.fromisoformat(s).astimezone(tz).strftime("%m/%d %H:%M")
        except (TypeError, ValueError):
            return None
    last = prog.get("last_run") or {}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return {"queue": [i["name"] for i in emblem_fill.due(prog, items, now)], "tz": str(tz), "ok": prog["summary"]["ok"], "total": prog["summary"]["total"], "started": local(prog.get("started")),
            "last_run": local(last.get("at")), "minutes": last.get("minutes"), "done": len(last.get("done") or []),
            "items": {n: {"state": x["state"], "note": x.get("note", ""), "at": local(x.get("at")),
                          "tried": x.get("tried") or {}} for n, x in prog["items"].items()}}


def write_page():
    """網页を作る。本番の収集（digest.yml が WL_RENDER_SOFT=1）では失敗しても止めない：集めたデータの push を先に通し、
    網页は次の生成（render.yml・次の収集）で作り直す（2026-10-21 KeyError でページ生成が 4 回止まり、その回の収集ごと消えた。全体の検査 H4）。
    CI（ci.yml）では今までどおり失敗で止まる。"""
    if os.environ.get("WL_RENDER_SOFT") != "1":
        return _write_page()
    try:
        return _write_page()
    except Exception as e:  # noqa: BLE001
        import traceback
        import runlog
        traceback.print_exc()
        print(f"::warning::網页の生成に失敗（データは保存して続ける）：{type(e).__name__}: {e}", file=sys.stderr)
        runlog.add("publish", f"網页の生成に失敗（データは保存、次の生成で作り直す）：{type(e).__name__}: {str(e)[:100]}", "error")
        return None


def _write_page():
    issues = [load_json(p) for p in sorted(REPORTS_DIR.glob("????-??-??.json"), reverse=True)[:ISSUES_ON_PAGE]]
    issues = [i for i in issues if i]
    settings, items = load_config()
    render.AUTH_ITEMS = [[i["name"], section_of(i)] for i in items if not i.get("parent")]   # お客さまが選ぶときの候補
    if not issues:   # まだ一期も出ていない（test2 を空から始めた直後）：空の号で入口・設定・管理ページだけ作る
        issues = [{"date": dt.datetime.now(zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))).date().isoformat(),
                   "no": 0, "items": []}]
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    tz = display_tz(settings)
    langs = lang.order(settings)   # 読者の言語（主言語 → 副言語）：言語違いの同じニュースは主言語の 1 本だけ
    updated = dt.datetime.now(tz).strftime("%m.%d %H:%M")
    issues = with_manual_themes(with_new_items(issues, items), items)
    themes = load_json(THEMES_FILE) or {}
    analysis = heat.analyze(items, sorted(INBOX_DIR.glob("????-??-??.json")), issues, load_json(HEAT_FILE) or {},
                            issues[0]["date"])
    heat_scores = analysis["items"]
    # 目次と版面の並び：板块の中は「小分類の話題度」→「作品の話題度」の順（heat.heat_order）。
    # 小分類の話題度は、中の作品の材料をまとめて 1 つとして測る（足し算ではない）。下級は上級の小分類に入れて測る
    names = {i["name"] for i in items}
    schemes = load_nav_schemes(settings)   # 板块ごとに選んだ小分類の分け方（⚙ 設定ページ）
    own_sub = {i["name"]: sub_of(i, schemes.get(section_of(i))) for i in items}
    placed = [{"name": i["name"], "section": section_of(i), "parent": i.get("parent"),
               "sub": own_sub[i["parent"]] if i.get("parent") in names else own_sub[i["name"]]} for i in items]
    groups = {}
    for i in placed:
        groups.setdefault((i["section"], i["sub"]), []).append(i["name"])
    sub_heat = heat.group_scores(items, sorted(INBOX_DIR.glob("????-??-??.json")), issues, load_json(HEAT_FILE) or {},
                                 issues[0]["date"], groups)
    order = heat.heat_order(placed, heat_scores, sub_heat, list(render.SECTIONS))
    adm = admin_data(items, issues, analysis, tz, updated)  # 管理ページの数字（「待ち行列」は簡報の「更新中」の帯にも使う）
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    render.AUTH_DB = {"url": settings.get("supabase_url") or "", "key": settings.get("supabase_key") or ""}  # 登录（render.AUTH_JS）
    html_ = render.render(issues, settings.get("nav_style", "line"), order, updated,
                          load_wishlist(), current_picks(items),
                          {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}, load_sizes(),
                          {i["name"]: render.template_for(i) for i in items}, themes,
                          [x for x in (load_json(RECOMMEND_FILE) or {}).get("taste", [])
                           if not str(x[0]).startswith(WORK_KEY) or str(x[0])[len(WORK_KEY):] in {i["name"] for i in items}], heat_scores,
                          {i["name"]: (i["emblem"], i.get("emblem_ring", "accent")) for i in items if isinstance(i.get("emblem"), list)},
                          {i["name"]: i["like_fx"] for i in items if i.get("like_fx")},
                          {n: v for n, v in own_sub.items() if v}, settings.get("nav_hide", render.NAV_HIDE),
                          {i["name"]: i["icon"].get("image") for i in items if isinstance(i.get("icon"), dict)},
                          render.busy_plan([i["name"] for i in items],
                                           {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}), generated,
                          {i["name"]: str(i["parent"]) for i in items if i.get("parent")},
                          {k: v["score"] for k, v in sub_heat.items()}, langs, also_map(items, schemes),
                          {i["name"]: [str(m) for m in i["media"]] for i in items if isinstance(i.get("media"), list) and i["media"]})
    save_json(THEMES_FILE, themes)  # トップのポスターの取色を書き足した分
    html_, ver_index = render.stamp(html_, updated, generated)  # 自動更新の指紋（開いたままのページが version.json と見比べる）
    (DOCS_DIR / "index.html").write_text(html_, encoding="utf-8")
    heat_html, ver_heat = render.stamp(render.render_heat(analysis, render.collect(issues, order, langs), updated), updated)
    (DOCS_DIR / "heat.html").write_text(heat_html, encoding="utf-8")
    (DOCS_DIR / "terms.html").write_text(render.render_terms(updated), encoding="utf-8")   # 利用規約・プライバシーポリシー（ログイン）
    (DOCS_DIR / "me.html").write_text(render.render_me(), encoding="utf-8")   # お客さまの本人のページを読み込む殻（render.render_me、user_pages.py）
    try:   # 入口（docs/index.html：何のサイトか・新しく始める）。24 時間より古いときだけ作り直す（話題の候補を新しく）
        import welcome
        welcome.build_if_stale()
    except Exception as ex:
        print("入口", ex)
    (DOCS_DIR / "themes.html").write_text(render.render_themes(  # テーマ見本（30 のテーマと 👍 の演出）
        [{"name": i["name"], "motif": render.template_for(i), "theme": i.get("theme")} for i in items], updated), encoding="utf-8")
    wishes = load_wishlist()
    vers = {}
    # 愿望清单が空でも（新しいアカウント）ページは作る：写真を送って最初の 1 件を足す入口になる
    works = render.collect(issues, [i["name"] for i in items], langs)
    finds = [x for x in (load_json(DISCOVER_FILE) or {}).get("entries", []) if x.get("wish")]
    wish_html, vers["wishlist"] = render.stamp(render.render_wishlist(wishes, works, updated, finds,
                                                                    {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}), updated)
    (DOCS_DIR / "wishlist.html").write_text(wish_html, encoding="utf-8")
    (DOCS_DIR / "settings.html").write_text(render.render_settings(
        [{"name": i["name"], "section": section_of(i), "subtitle": i.get("subtitle", ""),
          "size": load_sizes().get(i["name"], "M"),
          "fields": {**{k: i[k] for k in ITEM_FIELDS if k in i and k != "size"}, "section": section_of(i)}} for i in items],
        {"url": settings.get("supabase_url"), "key": settings.get("supabase_key"), "langs": settings.get("news_langs") or []},
        updated, nav_scheme_rows(settings, items)), encoding="utf-8")
    admin_html, ver_admin = render.stamp(render.render_admin(  # 管理ページ（見るだけ）
        adm, {"url": settings.get("supabase_url"), "key": settings.get("supabase_key"), "tz": str(tz)}, updated), updated)
    (DOCS_DIR / "admin.html").write_text(admin_html, encoding="utf-8")
    # 開いたままのページはこれを 1 分ごとに読み、自分の指紋と違えば新しい内容を出す（render.LIVE_JS）
    save_json(DOCS_DIR / "version.json", {"index": ver_index, "admin": ver_admin, "heat": ver_heat, **vers, "updated": updated,
                                          # どの版面・パネルが変わったか（開いたままのページが通知に名前を出す：render.LIVE_JS）
                                          "index_marks": render.page_marks(html_), "admin_marks": render.page_marks(admin_html),
                                          "heat_marks": render.page_marks(heat_html)})
    (DOCS_DIR / ".nojekyll").touch()


def write_issue_markdown(issue, settings):
    """GitHub Issue 正文：标题列表 + 网页链接，用于邮件提醒。"""
    lines = [f"**[查看本期简报 →]({pages_url(settings)})**", ""]
    for block in issue["items"]:
        if block.get("quiet"):
            continue
        lines.append(f"### {block['name']}")
        lines += [f"- **{f['label']}**：{f['text']}" + ("（有变化）" if f["changed"] else "")
                  for f in block["facts"] if f["changed"]]
        lines += [f"- {'**[重大]** ' if s['weight'] == 'hero' else ''}[{s['headline']}]({s['url']})"
                  for s in block["stories"]]
        lines.append("")
    (ROOT / "issue.md").write_text("\n".join(lines), encoding="utf-8")


# ---------- 主流程 ----------

def load_config():
    config = yaml.safe_load(ITEMS_FILE.read_text(encoding="utf-8")) or {}
    settings = config.get("settings") or {}
    settings["sub_schemes"] = taxonomy.sub_schemes()   # 小分類の分け方は sections.yaml が唯一の元
    items = config.get("items") or []
    by_name = {i.get("name"): i for i in items}
    for item in items:   # 以前の 17 板块の名前（宠物・时尚…）は今の 8 大類に（taxonomy.LEGACY）
        if item.get("section"):
            item["section"] = taxonomy.canonical(item["section"])
        if isinstance(item.get("also"), dict):
            item["also"] = {taxonomy.canonical(k): v for k, v in item["also"].items()}
    for item in items:   # 下級は上級と同じ板块（目次で上級の下の支線に並ぶ。docs/rules/sections.md「判断上下级」）。
        top = by_name.get(item.get("parent"))   # section を自分で書いた下級（面ごとに分けた「ちいかわ アニメ」→ 映像）はそのまま
        if top is not None and top is not item and not item.get("section"):
            item["section"] = top.get("section") or taxonomy.BY_TYPE.get(top.get("type", "product"), "好物")
    for item in items:   # also：本来の板块と同じもの・表にないものは捨てる
        if isinstance(item.get("also"), dict):
            mine = item.get("section") or taxonomy.BY_TYPE.get(item.get("type", "product"), "好物")
            item["also"] = {k: v if isinstance(v, dict) else {} for k, v in item["also"].items() if k in taxonomy.SECTIONS and k != mine}
    for item in items:
        item.setdefault("type", "product")
        if item["type"] not in ITEM_TYPES:
            sys.exit(f"{item['name']} 的 type 必须是 {'/'.join(ITEM_TYPES)} 之一")
    all_langs = (settings.get("news_langs") or []) + [l for i in items for l in i.get("news_langs") or []]
    for lang in all_langs:
        if lang not in NEWS_LANGS:
            sys.exit(f"news_langs 只支持 {'/'.join(NEWS_LANGS)}，不支持 {lang!r}")
    return settings, items


def entry_to_dict(n, e):
    d = {"n": n, "date": e.published.isoformat() if e.published else None, "source": e.source,
         "title": e.title, "summary": e.summary, "url": e.url, "image": e.image}
    if e.image_via:
        d["image_via"] = e.image_via
    if e.link:
        d["link"] = e.link
    if e.site:
        d["site"] = e.site   # Google ニュースの媒体の網站：link を還元する前でも exclude_hosts（drop_reason）で見られる
    return d


def entry_from_dict(d):
    return sources.Entry(title=d["title"], url=d["url"], source=d["source"], summary=d.get("summary", ""),
                         image=d.get("image", ""), image_via=d.get("image_via", ""), link=d.get("link", ""),
                         site=d.get("site", ""),
                         published=dt.datetime.fromisoformat(d["date"]) if d.get("date") else None)


def is_urgent(e, item):
    """要紧消息：标题命中 items.yaml 里该项的 urgent_patterns（正则）。
    Reddit / YouTube 不算（传闻和二手消息多，避免误报）。"""
    if e.source.startswith("r/") or e.source in ("Reddit", "YouTube"):
        return False
    return any(re.search(p, e.title, re.I) for p in item.get("urgent_patterns") or [])


def split_unedited(pairs, item):
    """AI 编辑还没整理的条目 [(编号, Entry)] → (要紧的报道, 整理待ち)。
    版面只放 AI 整理过的报道；例外是要紧消息（is_urgent）：等不了，马上以「重大」上版面（Discord 通知另走 notify.urgent）。
    其余不上版面，只在版面底部折叠的「整理待ち N 件」里列原标题和来源（render._pending），下次 AI 编辑时再整理。"""
    hot = [(n, e) for n, e in pairs if is_urgent(e, item)]
    stories = fallback_stories([e for _, e in hot], item) if hot else []
    for x in stories:
        x["refs"], x["weight"] = [hot[r - 1][0] for r in x["refs"]], "hero"
    taken = {r for x in stories for r in x["refs"]}
    pending = [{"n": n, "title": e.title, "url": e.url, "source": e.source,
                "date": e.published.date().isoformat() if e.published else ""}
               for n, e in pairs if n not in taken and not is_spam(e.title, e.link or e.url)]   # 垃圾页は「整理待ち」にも出さない
    return stories, pending


def merge_inbox(old, new):
    """同一天多次运行：新条目接在已有条目后面（编号顺延），状态以最新为准但保留“当天有变化”。"""
    by_name = {i["name"]: i for i in old["items"]}
    for item in new["items"]:
        cur = by_name.get(item["name"])
        if cur is None:
            old["items"].append(item)
            continue
        start = len(cur["entries"])
        # 垃圾页不接进来（同一天的旧版 inbox 和这次的合并时，别的回收集的结果里可能还留着）
        for k, entry in enumerate([d for d in item["entries"] if not is_spam(d.get("title", ""))], 1):
            cur["entries"].append({**entry, "n": start + k})
        changed_before = {f["label"] for f in cur["facts"] if f["changed"]}
        cur["facts"] = [{**f, "changed": f["changed"] or f["label"] in changed_before} for f in item["facts"]] or cur["facts"]
        cur["cover"] = cur.get("cover") or item.get("cover")
        if item.get("reddit_cold"):
            have = {d["url"] for d in cur.get("reddit_cold") or []}
            cur["reddit_cold"] = (cur.get("reddit_cold") or []) + [d for d in item["reddit_cold"] if d["url"] not in have]
    return old


def update_heat():
    """話題度用的外部数据：维基浏览量（一天一次）、Steam 在线、AniList / TMDB 人气。取不到的下次再取。"""
    settings, items = load_config()
    today = dt.datetime.now(zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))).date().isoformat()
    print("話題度：取外部数据", file=sys.stderr)
    save_json(HEAT_FILE, heat.fetch_signals(items, load_json(HEAT_FILE) or {}, today))


COLLECT_WORKERS = 6   # 收集时同时抓几个关注项（GitHub Actions 的机器 4 核；等网络为主，所以比核数多一点）
LIVE_AFTER_MIN = 3    # 收集・出刊结束后到新网页出现大约几分钟（提交・推送 + Pages 发布）
LIVE_EDIT_FILE = pathlib.Path("/tmp/wishlist-live-edit.json")  # AI 编辑这一回从几点开始、编哪些版面（同一个容器里用）
# 収集の締め切り：始めてからこの分数を過ぎたら新しい版面を始めない（残りは次の回へ、次の回はそれを先に取る）。
# digest.yml の timeout-minutes（40）の前に、出刊・通知・push の時間を残す（2026-10-22：22 分かかった回があり、30 分で切れると push の前に全部消える）
COLLECT_DEADLINE_MIN = 18
# 始まった版面が固まったとき（GDELT の 429 の空待ちなど）も、締め切り＋この分数で待つのをやめて先へ進む（その版面は次の回へ）
COLLECT_GRACE_MIN = 5
LAST_INGEST = {}   # この回の締め切り・失敗（logged_ingest がログに書く）：{"deferred": [名前], "failed": {名前: 理由}}


def deferred_from_log(log_dir=None):
    """前の回に時間切れで取らなかった版面（state/log/collect.json の最後の deferred）。この回はそれを先に取る。"""
    import runlog
    for r in reversed(runlog.load("collect", log_dir)):
        if "secs" in r:   # 収集が終わった行（secs つき）までさかのぼって、その回の deferred
            return []
        if r.get("deferred"):
            return list(r["deferred"])
    return []


def fetch_order(items, deferred, backfill=()):
    """取る順番：前の回に取れなかった版面と、初めて取る版面（backfill：新しく加えた関注項は items の末尾に入り、42 日分で重い）を先に。
    毎回同じ版面が時間切れにならないように・新関注項の「すぐ AI 編集」が時間切れで黙って失われないように。去重はあとで元の順に戻してする。"""
    first = set(deferred or []) | set(backfill or [])
    return [i for i in items if i["name"] in first] + [i for i in items if i["name"] not in first]


def run_parallel(fn, items, workers, timeout, key=lambda i: i["name"]):
    """items を workers 本で fn にかける。→ (結果 {key: 値}, 終わらなかった key のリスト)。
    timeout 秒たっても終わらない版面は待たない（daemon のスレッドなので、固まった 1 本がプロセスの終わりも止めない。
    ThreadPoolExecutor は with を抜けるときも終了時も全部のスレッドを待つので、1 本固まると 40 分の timeout で push の前に全部消える）。"""
    import queue
    import threading
    import time
    todo, lock, done, out = queue.Queue(), threading.Lock(), threading.Event(), {}
    for i in items:
        todo.put(i)
    left = [len(items)]

    def worker():
        while not done.is_set():
            try:
                i = todo.get_nowait()
            except queue.Empty:
                return
            try:
                r = fn(i)
            except Exception:  # noqa: BLE001  fn が自分で拾う。ここまで来たら空
                r = None
            with lock:
                if not done.is_set():
                    out[key(i)] = r
                    left[0] -= 1
                    if not left[0]:
                        done.set()
    if not items:
        return {}, []
    for _ in range(max(1, min(workers, len(items)))):
        threading.Thread(target=worker, daemon=True).start()
    done.wait(timeout)
    with lock:
        done.set()   # これより後に終わった版面の結果は捨てる（もう順番の処理に入っている）
        got = dict(out)
    return got, [key(i) for i in items if key(i) not in got]


def _run_min(proc, default_secs):
    """这个仕组み平常要跑几分钟（state/log 里最近 10 回的中位数；没有记录用 default_secs）。"""
    import runlog
    return runlog.typical(proc, "secs", default_secs) / 60


def live_mark(board, state=None, found=0, started=None, eta=None, proc="collect"):
    """简报网页的版面「更新中」条（render.BUSY_JS 读 Supabase 的 live_status()）：这个版面现在在做什么。
    state：fetch（正在找新记事）/ found（有新记事：网页上显示「新着 N 件 · AI 整理待ち」——新记事等 AI 编辑整理后才成为报道，
    出刊后先列在版面底部的「整理待ち」里，要紧消息除外）；None = 删掉这一行（没有新记事，条消失）。
    board=None 且 state=None：删掉这个 proc 的全部行（每次收集开始时清空）。失败也不影响收集本身。"""
    try:
        if state is None:
            q = f"proc=eq.{proc}" + (f"&board=eq.{urllib.parse.quote(board)}" if board else "")
            supabase(f"live_status?{q}", method="DELETE")
            return
        now = dt.datetime.now(dt.timezone.utc)
        supabase("live_status?on_conflict=board,proc", {
            "board": board, "proc": proc, "state": state, "found": found,
            "started_at": (started or now).isoformat(), "eta_at": eta.isoformat() if eta else None,
            "updated_at": now.isoformat()}, prefer="resolution=merge-duplicates,return=minimal", method="POST")
    except Exception as err:  # noqa: BLE001  条只是给人看的，出错不能让收集停下
        print(f"  （版面状态没写进数据库：{err}）", file=sys.stderr)


def _ingest_one(item, raw, bconf, settings, facts, seen, now, compare, dry_run, late=False):
    """1 版面分の順番どおりの処理（去重・状態・封面）。→ (inbox の 1 項目 か None, 収めた entries)。
    seen / known は呼ぶ側が、ここが最後まで通ったときだけ足す（途中で例外なら、その版面は何も残さない）。
    late = 締め切りを過ぎた：封面はネットに出ずに取れる分だけ（site の og:image は scrapling・ブラウザで数分のびることがある）。"""
    backfill, conf = bconf
    if backfill:
        print(f"  {item['name']} 第一次收集：往前看 {conf['lookback_days']} 天", file=sys.stderr)
    entries = filter_entries(raw, item, conf, seen, now, compare)
    # 不火的 Reddit 帖子（sources.reddit_hot）不上版面，只记下来给話題度数帖子数；以后上了最热榜还会再收进来
    cold = [e for e in entries if not getattr(e, "hot", True)]
    entries = [e for e in entries if getattr(e, "hot", True)]
    print(f"  {item['name']} 新条目 {len(entries)} 条" + (f"（另有不火的 SNS {len(cold)} 帖，只算話題度）" if cold else ""),
          file=sys.stderr)
    if dry_run:
        print(f"===== {item['name']} =====\n{format_entries(entries)}\n")
        return None, entries
    item_facts, status_cover = status_facts(item, settings, facts)
    if not entries and not cold and not any(f["changed"] for f in item_facts):
        return None, entries
    cover = (item.get("cover") or status_cover) if late else find_cover(item, status_cover)
    return {
        "name": item["name"],
        "priority": item.get("priority", ""),
        **({"backfill": True} if backfill else {}),
        "facts": item_facts,
        "cover": cover,
        # 补抓的是旧闻，不算要紧，不发 Discord
        "entries": [{**entry_to_dict(n, e), "urgent": not backfill and is_urgent(e, item)}
                    for n, e in enumerate(entries, 1)],
        **({"reddit_cold": [{"url": e.url, "date": e.published.isoformat() if e.published else None, "source": e.source}
                            for e in cold]} if cold else {}),
    }, entries


def ingest(dry_run=False):
    """收集本期原始条目到 inbox/。返回写入的文件路径（没有新内容时返回 None）。"""
    settings, items = load_config()
    now = dt.datetime.now(dt.timezone.utc)
    # “每天一期”按你所在时区的日期划分（默认北京时间）
    today = now.astimezone(zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))).date().isoformat()
    seen, facts = seen_from_inbox(), load_json(FACTS_FILE)
    known = recent_titles()

    # 新加的关注项第一次收集时往前多看几周，补上加入之前的报道；之后照常只看 lookback_days
    confs = {}
    for item in items:
        backfill = not has_history(item["name"])
        confs[item["name"]] = (backfill, dict(settings, lookback_days=settings.get("first_lookback_days", 42)) if backfill else settings)
    # 联网抓取最花时间，各关注项互不相干：并行抓（同一网站的间隔由 sources._pace 在线程之间共享）。
    # 去重要按顺序（前面的关注项收过的，后面的不再收），所以抓完后照原来的顺序一项一项处理（run_parallel）

    live = not dry_run
    started = {}
    if live:
        live_mark(None)  # 上一次收集留下的行清掉
    import threading
    import time
    t_start, budget = time.monotonic(), COLLECT_DEADLINE_MIN * 60
    # 待つのをやめた（固まった）版面のスレッドは daemon で走り続ける。打ち切ったあと（cut）は帯（live_status）を立て直さない：
    # 本体が消した帯に、今回 inbox に何も書かない版面の「新着 N 件 · AI 整理待ち」が次の収集まで残らないように
    cut = threading.Event()
    t_deferred, t_failed = [], {}   # スレッドが書く（固まった 1 本があとで書き足すこともある）。順番の処理は写しの deferred / failed
    LAST_INGEST.clear()

    def compare_for(item):
        compare = known.get(item["name"], [])
        if item.get("dedupe_others"):  # 别的关注项已经收过的同一件事，这一项不再重复收
            compare = compare + [t for name, ts in known.items() if name != item["name"] for t in ts]
        return compare

    run_min = _run_min("collect", 290) + LIVE_AFTER_MIN  # 最近の収集の長さから（固定値ではない）

    def eta():
        return max(now + dt.timedelta(minutes=run_min), dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2))

    shown = {}  # 版面 → 网页上现在显示的新记事件数（None = 条已消失）

    def fetch(item):
        name = item["name"]
        if time.monotonic() - t_start > budget:   # 締め切りを過ぎた：この版面は始めない（次の回に先に取る）
            t_deferred.append(name)
            return None
        print(f"抓取：{item['name']}", file=sys.stderr)
        if live:  # 网页上只有这个版面出「正在找新记事」的条
            started[name] = dt.datetime.now(dt.timezone.utc)
            if cut.is_set():
                return None
            live_mark(name, "fetch", started=started[name])   # Supabase への書き込みはロックの外（遅くてもほかの版面を待たせない）
            if cut.is_set():   # 書いている間に打ち切られた：自分の帯は自分で消す
                live_mark(name, None)
                return None
        try:
            raw = collect(item, confs[name][1])
        except Exception as err:  # noqa: BLE001  1 版面の失敗で収集全体を止めない（その版面は空・ログに残す）
            t_failed[name] = f"{type(err).__name__}: {str(err)[:80]}"
            print(f"  {name} の取得に失敗（この版面は空で続ける）：{t_failed[name]}", file=sys.stderr)
            if live:
                live_mark(name, None)
            return None
        if live:  # 这个版面一抓完就判断：没有新记事 → 条消失；有 → 「新着 N 件」。
            # 抓取期间 seen / known 都不变（只读），所以在线程里先数一遍；之后按顺序去重时件数变了再改
            try:
                n = len(filter_entries(raw, item, confs[name][1], seen, now, compare_for(item)))
            except Exception:  # noqa: BLE001
                n = None
            if cut.is_set():   # 打ち切ったあとに終わった：結果は捨てられる（run_parallel）ので帯も書かない
                return raw
            if n is not None:
                shown[name] = n or None
                live_mark(name, "found" if n else None, n, started.get(name), eta())
                if cut.is_set():   # 書いている間に打ち切られた：帯を残さない
                    live_mark(name, None)
        return raw
    order = fetch_order(items, [] if dry_run else deferred_from_log(), [n for n, (b, _) in confs.items() if b])
    got, stuck = run_parallel(fetch, order, COLLECT_WORKERS, budget + COLLECT_GRACE_MIN * 60)
    cut.set()
    deferred, failed = list(t_deferred), dict(t_failed)   # 固まったスレッドがあとで書き足しても、ここからは手元の写しを使う
    for name in stuck:   # 締め切り＋余裕を過ぎても終わらなかった（固まった）版面：次の回へ
        if name not in deferred:
            deferred.append(name)
        if name in started and live:
            live_mark(name, None)
    if stuck:
        print(f"  {len(stuck)} 版面が {COLLECT_DEADLINE_MIN + COLLECT_GRACE_MIN} 分で終わらず、待たずに先へ：{'、'.join(stuck[:8])}", file=sys.stderr)
    fetched = [got.get(i["name"]) for i in items]   # 去重は元の順番（前の関注項が収めたものは後ろで収めない）
    if deferred:
        print(f"時間切れ（{COLLECT_DEADLINE_MIN} 分）で {len(deferred)} 版面を次の回へ：{'、'.join(deferred[:8])}", file=sys.stderr)

    inbox_items = []
    for item, raw in zip(items, fetched):
        if raw is None:   # 時間切れで始めなかった・取得に失敗した版面：今回は何も書かない
            continue
        name = item["name"]
        before = {k: v for k, v in facts.items() if (v or {}).get("item") == name}
        try:
            rec, entries = _ingest_one(item, raw, confs[name], settings, facts, seen, now, compare_for(item),
                                       dry_run, late=time.monotonic() - t_start > budget)
        except Exception as err:  # noqa: BLE001  1 版面の失敗（壊れた re: の match など）で収集全体を止めない
            failed[name] = f"{type(err).__name__}: {str(err)[:80]}"
            print(f"  {name} の処理に失敗（この版面は空で続ける）：{failed[name]}", file=sys.stderr)
            for k in [k for k, v in facts.items() if (v or {}).get("item") == name]:   # 途中で書いた状態は元に戻す
                facts.pop(k)
            facts.update(before)
            if live:
                live_mark(name, None)
            continue
        if live and shown.get(name, -1) != (len(entries) or None):  # 按顺序去重后件数变了（被前面的版面收走）才改
            live_mark(name, "found" if entries else None, len(entries), started.get(name), eta())
        if rec:
            inbox_items.append(rec)
        for e in entries:
            seen.update((e.url, title_key(e.title)))
        known.setdefault(name, []).extend(e.title for e in entries)
    LAST_INGEST.update(deferred=deferred, failed=failed)

    if dry_run:
        return None
    save_json(FACTS_FILE, facts)
    path = INBOX_DIR / f"{today}.json"
    data = {"date": today, "items": inbox_items}
    if path.exists():  # 当天已经收集过：合并进去
        data = merge_inbox(load_json(path), data)
    data, carried = carry_over(data, today)
    if not inbox_items and not carried:
        print("本期没有新消息", file=sys.stderr)
        return None
    save_json(path, data)
    urgent = sum(e.get("urgent", False) for i in inbox_items for e in i["entries"])
    if urgent:
        print(f"  其中要紧消息 {urgent} 条", file=sys.stderr)
    print(f"已收集：{path.relative_to(ROOT)}", file=sys.stderr)
    return path


CARRY_DAYS = 2    # 何日前の inbox まで持ち越すか
CARRY_PER_SIZE = 2   # 1 版面で持ち越す件数 = 篇幅の本数（SIZE_STORIES：S 3・M 5・L 8）× これ（S 6・M 10・L 16）
CARRY_SEEN_DAYS = 3  # 今日とその前のこの日数の reports にもう載った記事（同じ網址・同じ見出し）は持ち越さない


def _carry_caps():
    """版面 → 持ち越す件数の上限（篇幅 × CARRY_PER_SIZE）。篇幅は load_sizes（数据库 → items.yaml の size）、なければ M。"""
    try:
        sizes = dict(load_sizes())
    except Exception:  # noqa: BLE001  読めなくても持ち越しは止めない（全部 M）
        sizes = {}
    try:
        for item in load_config()[1]:
            want = str(item.get("size") or "").upper()
            if item["name"] not in sizes and want in SIZE_STORIES:
                sizes[item["name"]] = want
    except Exception:  # noqa: BLE001
        pass
    return lambda name: SIZE_STORIES.get(sizes.get(name), SIZE_STORIES["M"]) * CARRY_PER_SIZE


def _published(today, days=CARRY_SEEN_DAYS):
    """today と前の days 日（days=3 なら 4 号）の reports に載った記事 → {版面: (網址の集合, 見出しのリスト)}。"""
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=days)).isoformat()
    out = {}
    for path in sorted(REPORTS_DIR.glob("????-??-??.json")):
        if not start <= path.stem <= today:
            continue
        for b in (load_json(path) or {}).get("items") or []:
            urls, titles = out.setdefault(b.get("name"), (set(), []))
            for st in b.get("stories") or []:
                if st.get("url"):
                    urls.add(st["url"])
                if st.get("headline"):
                    titles.append(st["headline"])
    return out


CARRY_KEY_MIN = 12      # 末尾の媒体名を除いた見出しの鍵を使うのは、残りがこの字数以上
CARRY_KEY_SHARE = 0.6   # かつ元の鍵のこの割合以上のときだけ（「討論牆 | 本文」の本文ごと消して頭だけで比べない）
# 末尾の媒体名：「 - 媒体名」（前後に空白のある -・–・—）か「|」「｜」の後ろ 40 字まで。_clean_title（空白なしの - も切る）は使わない：
# 「Spider-Man: …」「2026-27シーズン…」の - で本文が消える
_MEDIA_TAIL = re.compile(r"(?:\s+[-–—]\s+|\s*[|｜]\s*)[^|｜–—]{1,40}$")


def _title_keys(title):
    """見出し → 比べる鍵の集合。title_key（既存の重複判定と同じ）＋ 末尾の媒体名を除いた鍵（十分長く残るときだけ）。"""
    raw = title_key(title or "")
    clean = title_key(_MEDIA_TAIL.sub("", unicodedata.normalize("NFKC", title or "")))
    n_raw, n_clean = len(raw) - 2, len(clean) - 2   # 頭の「t:」を除く
    return {raw} | ({clean} if n_clean >= CARRY_KEY_MIN and n_clean >= CARRY_KEY_SHARE * n_raw else set())


def _not_published(name, entries, pub):
    """もう版面に載った記事（同じ網址、または同じ見出し：title_key。持ち越す側の見出しだけ末尾の媒体名を除いた形も、残りが十分長いときは比べる）を除く。
    媒体名を除いて短く残った頭だけで比べると、別の話まで落とす（2026-10-22 検査：「討論牆 | 周杰倫…」が別の「討論牆 | …」と同じに）。
    StoryDeduper（見出しの共通の語）は使わない：2026-10-21 の本物で試すと、別の試合・別のリーク記事まで「同じ話」にして落とした。
    同じ話の別の網址は、今までどおり AI 編集がまとめる（持ち越しでニュースを落とさない）。"""
    urls, titles = pub.get(name) or (set(), [])
    # 載った見出しは生の鍵だけ。末尾を切った鍵どうしでは比べない：「共通の頭 | 品目」の別の記事が同じ鍵になる
    # （残るのは「AI が書いた見出し ＝ 元の題から媒体名を除いたもの」の場合）
    keys = {title_key(h) for h in titles}
    return [e for e in entries if not ({e.get("url"), e.get("link")} & urls)
            and not (_title_keys(e.get("title", "")) & keys)]


def carry_over(data, today):
    """前の日の「整理待ち」（AI 編集がまだ整理していない記事）を今日の inbox に持ち越す（その日の最初の 1 回だけ、_carried に印）。
    AI 編集は最新の inbox しか見ないので、日付が変わる前（JST 18:00 の回のあと〜1:00）に集めた分は、持ち越さないと二度と版面に載らない
    （2026-10-22 全体の検査 H3：10-17〜10-21 で 829 件が残ったまま）。数え方は gate.edit_work と同じ：_covered より後の記事、edit.json にない版面は全部。
    要紧（urgent）はもう「重大」で載っているので持ち越さない。前の日に持ち越した記事（carried）も、もう一度は持ち越さない。今日と前の CARRY_SEEN_DAYS 日の reports にもう載った記事（同じ網址・同じ見出し）も持ち越さない。
    1 版面の上限は篇幅 × CARRY_PER_SIZE（新しいほうから。AI 編集が読む一覧を太らせない）。→ (data, 持ち越した件数)"""
    if data.get("_carried"):
        return data, 0
    prev = [p for p in sorted(INBOX_DIR.glob("????-??-??.json")) if p.stem < today]
    data["_carried"] = prev[-1].stem if prev else "-"
    if not prev or (dt.date.fromisoformat(today) - dt.date.fromisoformat(prev[-1].stem)).days > CARRY_DAYS:
        return data, 0
    old = load_json(prev[-1]) or {}
    edit = load_edits(prev[-1])
    covered = edit.get("_covered") or {}
    carry, cap, pub, dropped = [], _carry_caps(), _published(today), 0
    for b in old.get("items") or []:
        entries = b.get("entries") or []
        c = int(covered[b["name"]] or 0) if b["name"] in covered else len(entries) if b["name"] in edit else 0
        left = [e for e in entries if int(e.get("n") or 0) > c and not e.get("urgent") and not e.get("carried")   # 持ち越しは 1 回だけ
                and not is_spam(e.get("title", ""), e.get("url", ""))]
        fresh = _not_published(b["name"], left, pub)
        dropped += len(left) - len(fresh)
        left = fresh[-cap(b["name"]):]
        if left:
            carry.append({"name": b["name"], "priority": b.get("priority", ""), "facts": [], "cover": b.get("cover"),
                          "entries": [{**e, "n": k, "carried": prev[-1].stem} for k, e in enumerate(left, 1)]})
    if not carry:
        return data, 0
    n = sum(len(b["entries"]) for b in carry)
    print(f"  前の日（{prev[-1].stem}）の整理待ち {n} 件を今日に持ち越し（もう載った {dropped} 件は除いた）", file=sys.stderr)
    merged = merge_inbox(data, {"date": today, "items": carry})
    merged["_carried"] = prev[-1].stem
    return merged, n


def load_edits(inbox_path):
    """读取人工 / Claude 写的编排：inbox/YYYY-MM-DD.edit.json，格式：
    {"关注项名称": [{"headline": "原文标题（不翻译）", "highlight": "标题里要强调的字", "blurb": "一句话",
                    "weight": "hero|lead|normal", "refs": [inbox 里条目的 n]}, ...],
     "_covered": {"关注项名称": 编排时 inbox 里该项的条目数}}
    某个关注项写成空列表 [] 表示本期不出现。详细规则见 EDITING.md。"""
    path = inbox_path.with_suffix(".edit.json")
    return load_json(path) if path.exists() else {}


def last_story(name, before):
    """往期里这个关注项最近的一条报道（优先 hero / lead），给“暂无新消息”小栏用。"""
    for path in sorted(REPORTS_DIR.glob("????-??-??.json"), reverse=True):
        if path.stem >= before:
            continue
        for block in (load_json(path) or {}).get("items", []):
            if block["name"] == name and block.get("stories"):
                s = min(block["stories"], key=lambda s: {"hero": 0, "lead": 1}.get(s.get("weight"), 2))
                return {"headline": s["headline"], "url": s["url"], "date": path.stem}
    return None


def also_map(items, schemes):
    """目次の乗換駅：{作品: [(ほかの板块, その板块で選んでいる分け方の小分類)]}（items.yaml の also）。"""
    out = {}
    for i in items:
        for sec, subs in (i.get("also") or {}).items():
            if sec == section_of(i) or sec not in taxonomy.SECTIONS:
                continue
            first = taxonomy.SECTIONS[sec]["schemes"][0]
            sb = (subs or {}).get(schemes.get(sec) or first["id"]) or next(iter((subs or {}).values()), "") or taxonomy.values(first)[0]
            out.setdefault(i["name"], []).append((sec, sb))
    return out


def section_of(item):
    """头版上的板块（sections.yaml 的 key）。没写 section 的按 type（taxonomy.BY_TYPE）。"""
    return taxonomy.canonical(item.get("section") or taxonomy.BY_TYPE.get(item.get("type", "product"), "好物"))


def quiet_block(item, themes, date):
    """本期没有新消息的关注项：只留一个小栏（名字、现状、最近一条），配色照旧。"""
    cover = find_cover(item, None)
    return {
        "name": item["name"],
        "section": section_of(item),
        "subtitle": item.get("subtitle", ""),
        "theme": theme.resolve(item, cover, themes),
        "quiet": True,
        "status": item.get("status", ""),
        "cover": cover,
        "last": last_story(item["name"], date),
        "facts": [],
        "stories": [],
    }


def edit_sig(inbox_path):
    """その日の edit.json の指紋（なければ ""）。出刊した報告に書いておき、あとで edit.json と見比べる。"""
    p = pathlib.Path(inbox_path).with_suffix(".edit.json")
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12] if p.exists() else ""


def stale_report():
    """最新の inbox の報告が、いまの edit.json を取り込んでいなければその inbox のパス（古い＝網页に AI 編集が出ていない）。
    起きる場面：収集（Actions）が古い checkout で出刊している間に AI 編集が edit.json を push する／push 競合で
    報告ファイルだけ相手側が残る。どちらも `render` は報告から作るだけなので、edit.json があるのに網页が変わらなかった。"""
    cands = sorted(INBOX_DIR.glob("????-??-??.json"))
    if not cands:
        return None
    rep = load_json(REPORTS_DIR / f"{cands[-1].stem}.json")
    if rep and rep.get("edit_sig", "") != edit_sig(cands[-1]):
        return cands[-1]
    return None


def publish(inbox_path=None, heal=False):
    """heal=True：edit.json を取り込み直すだけの出刊（おすすめ・Reddit・配図の再探しは飛ばして速く）。"""
    settings, items = load_config()
    by_name = {i["name"]: i for i in items}
    if inbox_path is None:
        candidates = sorted(INBOX_DIR.glob("????-??-??.json"))
        if not candidates:
            print("inbox 里没有可出刊的内容", file=sys.stderr)
            return
        inbox_path = candidates[-1]
    inbox = load_json(inbox_path)
    date = inbox["date"]
    edits = load_edits(inbox_path)
    themes = load_json(THEMES_FILE)
    sizes = load_sizes()
    langs = lang.order(settings)   # 読者の言語：主言語 → 副言語（items.yaml の settings.languages）

    client = None
    if settings.get("summarize", False) and any(i["name"] not in edits for i in inbox["items"]):
        client = make_client()
        if client is None:
            print("没有可用的 Claude 凭据：未整理的条目等 AI 编辑（要紧消息先上版面）", file=sys.stderr)
    model = settings.get("model", "claude-haiku-5-5")

    blocks, inbox_changed, stats, used = [], False, images.Stats(), set()
    for raw in inbox["items"]:
        item = by_name.get(raw["name"], {"name": raw["name"], "type": "product"})
        if raw.get("backfill"):  # 补抓的旧闻不做“重大”
            item = {**item, "urgent_patterns": []}
        if raw["name"] in sizes:  # 数据库里定的篇幅优先于 items.yaml 的 max_stories
            item = {**item, "max_stories": SIZE_STORIES[sizes[raw["name"]]]}
        elif not item.get("max_stories"):
            item = {**item, "max_stories": SIZE_STORIES["M"]}
        entries = [entry_from_dict(d) for d in raw["entries"]]
        pending = []
        if raw["name"] in edits and not raw["name"].startswith("_"):
            stories = [dict(s) for s in edits[raw["name"]]]
            for s in stories:
                s.setdefault("highlight", ""), s.setdefault("blurb", ""), s.setdefault("weight", "normal")
                s["refs"] = [r for r in s.get("refs", []) if 0 < r <= len(entries)]
            stories = [s for s in stories if s["refs"]]
            for s in stories:   # AI 編集が見出しを書き忘れた（title と書いた）記事は、依拠の 1 本目の原題で補う（ページ生成を止めない）
                s["headline"] = str(s.get("headline") or s.get("title") or entries[s["refs"][0] - 1].title)
            # 编排写好之后当天又来的消息（编号大于 _covered）：不上版面，等下次 AI 编辑整理。
            # 例外是要紧消息：马上做“重大”放在最前面；其余列进版面底部折叠的「整理待ち」
            covered = edits.get("_covered", {}).get(raw["name"], len(entries))
            urgent, pending = split_unedited([(n, e) for n, e in enumerate(entries, 1) if n > covered], item)
            stories = urgent + stories
        elif entries:
            # 还没被 AI 编辑整理过的关注项：有 API 凭据时当场用 AI 编；没有（GitHub Actions）就等 AI 编辑，
            # 只把要紧消息先放上去，其余放进「整理待ち」（不是空白版面，也不放未整理的原标题报道）
            stories = edit_stories(client, model, item, entries, langs) if client else None
            if not stories:
                stories, pending = split_unedited(list(enumerate(entries, 1)), item)
        else:
            stories = []
        # 言語（lang.py、ルール）：好みの言語の出典があれば見出しをその原題に；言語違いの同じニュースは主言語の 1 本に。
        # 主言語・副言語にない言語の記事は載せない。篇幅で切る前にやる（重複で枠を使わない）
        titles = {n: e.title for n, e in enumerate(entries, 1)}
        stories = lang.dedupe([lang.prefer_ref(s, titles, langs) for s in stories], langs)
        if item.get("max_stories"):  # 篇幅上限：要紧的排在最前，截掉的是后面次要的
            stories = stories[:item["max_stories"]]
        if not stories and not pending and not any(f["changed"] for f in raw["facts"]):
            continue
        stories = [s for s in stories if not is_spam(s.get("headline", ""))]  # 收集后才进 inbox 的垃圾页（合并的旧版）也不出刊
        stories = attach_media(stories, entries, raw.get("cover"), raw["name"], stats, used, langs, item)  # 原文已删的报道会被去掉
        stories = [s for s in stories if not is_spam(s.get("headline", ""), s.get("url", ""))]  # 还原后的网址里塞着广告的
        # 出刊时补到的配图写回 inbox，下次出刊直接用，不必再找（Reddit 限流、网站偶尔打不开时也不会丢图）
        for d, e in zip(raw["entries"], entries):
            if e.image and not d.get("image"):
                d["image"], d["image_via"], inbox_changed = e.image, e.image_via, True
            if e.link and not d.get("link"):
                d["link"], inbox_changed = e.link, True
        if not stories and not pending and not any(f["changed"] for f in raw["facts"]):
            continue
        blocks.append({
            "name": raw["name"],
            "section": section_of(item),
            "subtitle": item.get("subtitle", ""),
            "cover": raw.get("cover"),
            "theme": theme.resolve(item, raw.get("cover"), themes),
            "facts": raw["facts"],
            "stories": stories,
            **({"pending": pending} if pending else {}),
        })
    # 没有新消息的关注项也留一个小栏，排在有消息的后面
    shown = {b["name"] for b in blocks}
    blocks += [quiet_block(i, themes, date) for i in items if i["name"] not in shown]
    save_json(THEMES_FILE, themes)
    if inbox_changed:
        save_json(inbox_path, inbox)
    print(stats.summary(), file=sys.stderr)

    if not blocks:
        print("本期没有可出刊的内容", file=sys.stderr)
        return
    existing = sorted(p.stem for p in REPORTS_DIR.glob("????-??-??.json"))
    no = existing.index(date) + 1 if date in existing else len(existing) + 1
    issue = {"no": no, "date": date, "edit_sig": edit_sig(inbox_path), "items": blocks}
    save_json(REPORTS_DIR / f"{date}.json", issue)
    if not heal:
        recommend()
        prune_reddit()
        hd_images()            # 配图看不清・期限付き → 本站保存；打不开了的记 dead
        if retry_images():     # 没图・dead 的报道去原文重新找图
            hd_images()        # 新找到的图（期限付きの網址など）也存一份
    write_page()
    write_issue_markdown(issue, settings)
    print(f"第 {no} 期：reports/{date}.json → docs/index.html", file=sys.stderr)


IMG_RETRY_FILE = STATE_DIR / "img_retry.json"
IMG_RETRY_HOURS = 6    # 同一条报道隔几小时再找一次图
IMG_RETRY_MAX = 6      # 每次出刊最多再找几条（每条最多 IMG_RETRY_BUDGET 秒，别拖慢出刊）
IMG_RETRY_BUDGET = 25
IMG_RETRY_DAYS = 8     # 网页显示最近 7 天，多看 1 天


def retry_images(days=IMG_RETRY_DAYS):
    """已经出刊、但没有自己配图的报道（当时原文被挡、限流、网站临时打不开），和配图后来打不开了的报道
    （期限付きの網址が切れた・削除された，hdimg 记的 dead），以后每次出刊自动再找：
    同一条最多每 IMG_RETRY_HOURS 小时找一次，一次出刊最多 IMG_RETRY_MAX 条，找图顺序和出刊时一样
    （images.pick，原文 → 同一件事的别家报道 → 转载）。很久没试的先试。找到了就写回报告。返回找到几条。"""
    _, items = load_config()
    by_name = {i["name"]: i for i in items}
    now = dt.datetime.now(dt.timezone.utc)
    tried = load_json(IMG_RETRY_FILE) or {}
    paths = sorted(REPORTS_DIR.glob("????-??-??.json"))[-days:]
    reports = [(p, load_json(p)) for p in paths]
    import hdimg
    dead = {u for u, r in hdimg.load_state().items() if isinstance(r, dict) and r.get("dead")}   # 期限切れ・削除で開けなくなった図
    used = {st["image"] for _, r in reports for b in r["items"] for st in b.get("stories") or []
            if st.get("image") and st.get("image_via") != "作品封面"} | dead
    raw, boards = {}, {}   # 链接 → inbox 里的原始条目；(日期, 关注项) → 那天的全部条目
    for ip in sorted(INBOX_DIR.glob("????-??-??.json"))[-days - 2:]:
        for it in load_json(ip).get("items") or []:
            for d in it["entries"]:
                for key in (d.get("url"), d.get("link")):
                    if key:
                        raw.setdefault(key, (d, ip.stem, it["name"]))
            boards.setdefault((ip.stem, it["name"]), []).extend(it["entries"])
    todo = []
    for path, rep_ in reports:
        for b in rep_["items"]:
            for st in b.get("stories") or []:
                img = st.get("image")
                generic = bool(img) and bool(images.GENERIC.search(urllib.parse.urlparse(img).path))   # 後から広げた「網站の既定画像」の規則に当たるもの
                if not st.get("url") or img and st.get("image_via") != "作品封面" and img not in dead and not generic:
                    continue
                last = tried.get(st["url"])
                if last and now - dt.datetime.fromisoformat(last) < dt.timedelta(hours=IMG_RETRY_HOURS):
                    continue
                todo.append((last or "", path, rep_, b, st))
    todo.sort(key=lambda x: x[0])
    found, changed = 0, set()
    for _, path, rep_, b, st in todo[:IMG_RETRY_MAX]:
        hit = raw.get(st["url"])
        e = entry_from_dict(hit[0]) if hit else sources.Entry(title=st.get("headline", ""), url=st["url"], published=None, source=st.get("source") or "")
        others = [entry_from_dict(d) for d in boards.get((hit[1], hit[2]), [])] if hit else []
        res = images.pick(None, [e], st["url"], budget=IMG_RETRY_BUDGET, avoid=used,
                          siblings=same_event(by_name.get(b["name"], {"name": b["name"]}), [e], others, st.get("headline", "")))
        tried[st["url"]] = now.isoformat(timespec="seconds")
        print(images.log_line(b["name"], st.get("headline", ""), res) + "（再找）", file=sys.stderr)
        if res.image:
            st["image"], st["image_via"] = res.image, res.source
            used.add(res.image)
            found += 1
            changed.add(path)
    for path, rep_ in reports:
        if path in changed:
            save_json(path, rep_)
    cutoff = (now - dt.timedelta(days=days)).isoformat()
    save_json(IMG_RETRY_FILE, {u: t for u, t in tried.items() if t >= cutoff})
    if todo:
        print(f"配图再找：试了 {min(len(todo), IMG_RETRY_MAX)} 条（还有 {max(0, len(todo) - IMG_RETRY_MAX)} 条等下次），找到 {found} 条", file=sys.stderr)
    return found


REDDIT_CHECK_FILE = STATE_DIR / "reddit_check.json"
REDDIT_CHECK_DAYS = 8   # 网页显示最近 7 天，多查 1 天


def prune_reddit(days=REDDIT_CHECK_DAYS):
    """已经出刊的 Reddit 帖子每天复查一次（结果记在 state/reddit_check.json）：
    - 删了（正文 [removed] / [deleted]、帖子 404）→ 从版面撤掉，点开也看不到
    - 不火了：专门版块（subreddits）的帖子不在那个版块本周最热榜上（sources.reddit_hot_ids）、
      全站搜索来的帖子不在这个关注项的 Reddit 搜索（按热度排）前 5（和收集时同一个规则）→ 撤掉
    拿不到结果（Reddit 限流）的这次不判断，下次再查。返回有没有改动。"""
    _, items = load_config()
    subs = {i["name"]: {x.lower() for x in i.get("subreddits") or []} for i in items}
    by_name = {i["name"]: i for i in items}
    searched = {}

    def search_hot(name):  # 这个关注项的 Reddit 搜索前 5（收集时的规则）；没做全站搜索 / 拿不到 → None
        item = by_name.get(name) or {}
        if "reddit" not in (item.get("use") or ["google", "bing", "reddit"]):
            return None
        if name not in searched:
            kw = (item.get("keywords") or [name])[0]
            found = sources.reddit_search(f'"{kw}"', strict=True)
            searched[name] = None if found is None else {sources.reddit_id(e.url) for e in found if e.hot}
        return searched[name]
    today = dt.date.today().isoformat()
    checks = load_json(REDDIT_CHECK_FILE) or {}
    changed_any = False
    for path in sorted(REPORTS_DIR.glob("????-??-??.json"))[-days:]:
        rep_, changed = load_json(path), False
        for b in rep_["items"]:
            keep = []
            for st in b.get("stories") or []:
                url = st.get("url") or ""
                if not images.REDDIT_POST.match(url):
                    keep.append(st)
                    continue
                c = checks.get(url)
                if not c or c.get("day") != today:
                    removed = sources.reddit_removed(url)
                    m = re.search(r"/r/([^/]+)/", url)
                    hot = None
                    in_sub = bool(m) and m.group(1).lower() in subs.get(b["name"], set())
                    ids = sources.reddit_hot_ids(m.group(1)) if in_sub else search_hot(b["name"])
                    hot = None if ids is None else sources.reddit_id(url) in ids
                    # 没删、但该看的榜没拿到（限流）：今天先不记，下次出刊再查（不然一整天都不判断火不火）
                    checkable = in_sub or "reddit" in ((by_name.get(b["name"]) or {}).get("use") or ["google", "bing", "reddit"])
                    if removed is None and hot is None or not removed and hot is None and checkable:
                        keep.append(st)
                        continue
                    c = checks[url] = {"day": today, "removed": removed, "hot": hot}
                if c.get("removed") or c.get("hot") is False:
                    why = "已删除" if c.get("removed") else "不在本周最热榜上"
                    print(f"  [Reddit] {b['name']} | {st.get('headline', '')[:30]} | {why}，撤掉", file=sys.stderr)
                    changed = True
                    continue
                keep.append(st)
            b["stories"] = keep
        if changed:
            save_json(path, rep_)
            changed_any = True
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    save_json(REDDIT_CHECK_FILE, {u: c for u, c in checks.items() if c.get("day", "") >= cutoff})
    return changed_any


def hd_images():
    """网页上看不清的配图（要放大 1.6 倍以上而且量出来是糊的）用 OpenCV 处理，看得清的不动；
    Bing 的小缩略图、防盗链的图（新浪 sinaimg）存一份到本站：都放 docs/pics/，网页优先用它（见 hdimg.py）。出问题也不挡出刊。"""
    import hdimg
    try:
        hdimg.run()
    except Exception as ex:
        print(f"配图高清化失败（照常出刊，用原图）：{type(ex).__name__}: {ex}", file=sys.stderr)


def new_item_names():
    """items.yaml 里有、但 state/known_items.json 还没记下的关注项，也就是刚加的。
    要在 notify-new-items 之前调用（发完通知它会把新项记进去）。"""
    known = load_json(STATE_DIR / "known_items.json") or []
    return [i["name"] for i in load_config()[1] if i["name"] not in known]


def unedited(only=None):
    """今天的 inbox 里有条目、但当天的 edit.json 里还没有的关注项。only 给了就只看这些。
    工作流在推送新关注项后用它判断要不要立刻叫 AI 编辑。今天还没有 inbox 就返回空。"""
    settings, _ = load_config()
    today = dt.datetime.now(zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))).date().isoformat()
    path = INBOX_DIR / f"{today}.json"
    if not path.exists():
        return []
    edits = load_edits(path)
    return [i["name"] for i in load_json(path)["items"]
            if i["entries"] and i["name"] not in edits and (only is None or i["name"] in only)]


PICK_DIR = pathlib.Path(os.environ.get("PICK_DIR", "/tmp/wishlist-pick"))


def live_edit():
    """AI 编辑开始编排时（EDITING.md 第 2 步）：今天还没编的版面，在网页上出「AI が編集しています · あと約 N 分」的条。
    预计时间 = 最近几回 AI 编辑的长度（state/log/edit.json 的 secs）。之后 pick-images・publish 会把条往下推进。"""
    import livestatus
    boards = [n for batch in edit_queue() for n, _ in batch] or unedited()   # 整理待ちのある版面全部（途中まで編集済みのものも）
    est = _run_min("edit", 1200)
    paths = sorted(INBOX_DIR.glob("????-??-??.json"))
    done = sorted(_edit_done_boards(paths[-1])) if paths else []   # 始める前に編集済みの版面（バッチの記録に数えない）
    LIVE_EDIT_FILE.write_text(json.dumps({"start": time.time(), "boards": boards, "est": est, "done": done}, ensure_ascii=False), encoding="utf-8")
    for b in boards:
        livestatus.report(b, "edit", "work", "AI が編集しています", est + LIVE_AFTER_MIN)
    print(f"網页の帯：{len(boards)} 版面（予想 {est:.0f} 分）", file=sys.stderr)


EDIT_BATCH = 1   # AI 编辑一次编几个版面：编好就出刊・推送，网页上这个版面先更新（用户定的，2026-10-19：一个一个来，方便试错）


def edit_control():
    """AI 编辑的开关（Supabase edit_control_get()，db/edit_control.sql）→ {"mode": run|step|pause, "redo": [版面…]}。读不到就当作 run。"""
    import livestatus
    url, key = livestatus._db()
    if not (url and key):
        return {"mode": "run", "redo": []}
    req = urllib.request.Request(f"{url}/rest/v1/rpc/edit_control_get", method="POST",
                                 data=json.dumps({"p_account": sitedir.NAME}).encode("utf-8"),
                                 headers={"apikey": key, "Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=15).read() or b"{}") or {}
        return {"mode": d.get("mode") if d.get("mode") in ("run", "step", "pause") else "run", "redo": list(d.get("redo") or [])}
    except Exception as err:  # noqa: BLE001
        print(f"  （AI 编辑的开关读不到，当作 run：{err}）", file=sys.stderr)
        return {"mode": "run", "redo": []}


def set_edit_control(mode=None, redo_clear=None):
    """AI 编辑自己改开关：1 版面ずつ（step）做完一个就变 pause；重做的版面做完从 redo 拿掉。失败也不停。"""
    import livestatus
    url, key = livestatus._db()
    if not (url and key):
        return
    body = json.dumps({"p_account": sitedir.NAME, "p_mode": mode, "p_redo_add": None, "p_redo_clear": redo_clear}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{url}/rest/v1/rpc/edit_control_set", data=body, method="POST",
                                 headers={"apikey": key, "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as err:  # noqa: BLE001
        print(f"  （AI 编辑的开关写不进去：{err}）", file=sys.stderr)


def edit_queue(date=None, batch=EDIT_BATCH, ctl=None):
    """AI 编辑的顺序：管理页点了「やり直す」的版面（redo）最先，然后今天还有整理待ち的版面（编号 > _covered，或 edit.json 里没有），整理待ち多的先，每 batch 个一批。
    → [[(版面, 整理待ち件数), …], …]。规则（不用 AI）：和 gate.edit_work 同一个数法。ctl = edit_control() 的结果（测试用）。"""
    import gate
    paths = sorted(INBOX_DIR.glob(f"{date or '????-??-??'}.json"))
    if not paths:
        return []
    work = gate.edit_work(INBOX_DIR, today=paths[-1].stem)
    sizes = {i["name"]: len(i.get("entries") or []) for i in (load_json(paths[-1]) or {}).get("items", [])}
    redo = [(n, sizes[n]) for n in (ctl if ctl is not None else edit_control()).get("redo") or [] if n in sizes]
    order = redo + sorted(((n, c) for n, c in work.items() if n not in dict(redo)), key=lambda kv: (-kv[1], kv[0]))
    return [order[i:i + batch] for i in range(0, len(order), batch)]


def undesigned(items=None):
    """設定ページで足したのに、まだ AI が版面を設計していない関注項（DESIGN_KEYS のどれかが空）。"""
    items = items if items is not None else load_config()[1]
    return [i["name"] for i in items if WEB_ITEM_MARK in str(i.get("notes") or "") and any(not i.get(k) for k, _ in DESIGN_KEYS)]


def edit_next(ctl=None):
    """AI 编辑每编一个版面之前问一次（EDITING.md 第 4 步）：→ ("DESIGN", 版面) / ("NEXT", 版面) / ("STOP", 理由) / ("DONE", "")。
    管理页的开关：pause = 停（正在编的那个版面已经编完）；step = 这次会话只编 1 个版面，编完自动变 pause。"""
    import runlog
    ctl = ctl if ctl is not None else edit_control()
    try:
        run = json.loads(LIVE_EDIT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        run = {}
    if ctl.get("mode") == "pause":
        runlog.add("edit", "管理ページで一時停止中：ここで止めた（「続けて全部」か「次の 1 版面」で再開）", "warn")
        return "STOP", "一時停止中"
    if ctl.get("mode") == "step" and int(run.get("batch") or 0) >= 1:
        set_edit_control(mode="pause")
        runlog.add("edit", "1 版面ずつ：この版面で止めた（管理ページの「次の 1 版面」で続き）", "info")
        return "STOP", "1 版面ずつ：1 つ終わったので止める"
    # 版面の設計が済んでいない関注項（設定ページで足したもの）が先：設計（motif・theme・emblem…、EDITING.md 第 1 步）を
    # 終えるまで記事の編集には進ませない（説明書に書くだけでは飛ばされた、2026-10-19）
    todo = undesigned()
    if todo:
        return "DESIGN", f"{todo[0]}（未設定：{'・'.join(ja for k, ja in DESIGN_KEYS if not next(i for i in load_config()[1] if i['name'] == todo[0]).get(k))}）"
    q = edit_queue(ctl=ctl)
    if not q:
        return "DONE", ""
    name = q[0][0][0]
    if run:
        run["current"] = name
        LIVE_EDIT_FILE.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    return "NEXT", name


def _edit_done_boards(inbox_path):
    """今天已经编完（_covered ≥ 条目数）的版面。"""
    import gate
    pending = gate.edit_work(inbox_path.parent, today=inbox_path.stem)
    return {i["name"] for i in (load_json(inbox_path) or {}).get("items", [])} - set(pending)


def _live_edit_step(note, left_min=None, only=None):
    """AI 编辑的途中：开始时记下的版面的条，换成新的说明和剩下的时间。only 给了就只改这些版面（分批：编好的那批先「反映を待っています」）。"""
    import livestatus
    try:
        run = json.loads(LIVE_EDIT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if left_min is None:
        left_min = max(2, run["est"] - (time.time() - run["start"]) / 60) + LIVE_AFTER_MIN
    for b in run["boards"]:
        if only is None or b in only:
            livestatus.report(b, "edit", "work" if left_min > LIVE_AFTER_MIN else "wait", note, left_min)
    return run


PICK_WEIGHTS = ("hero", "lead")   # AI が目で配図を選ぶのは重大・頭の記事だけ（ほかは規則で。画像を見るとトークンを多く使う：1 枚の一覧 ≈ 横×縦/750 トークン）
PICK_THUMB = (270, 180)           # 一覧の 1 枚の大きさ。4 列 × 2 段 = 1120×380 ≈ 570 トークン（前は 360×240・12 枚で ≈ 1,500）
PICK_MAX = 8                      # 1 記事の候補は 8 枚まで


def edit_brief(date=None, batch=None, summary=120):
    """AI 編集に読ませる、短い一覧（省トークン）：inbox の JSON をそのまま読むと、網址・画像の網址・長い要約でトークンがかさむ。
    版面ごとに「番号 日付 出典｜題｜要約（summary 字まで）」だけ。batch（1〜）を指定するとその分批の版面だけ。→ 文字列。"""
    paths = sorted(INBOX_DIR.glob(f"{date or '????-??-??'}.json"))
    if not paths:
        return ""
    inbox_path = paths[-1]
    q = edit_queue(inbox_path.stem)
    if batch and not 0 < batch <= len(q):
        return ""   # そのバッチはない（もう全部終わった）
    want = {n for n, _ in q[batch - 1]} if batch else {n for b in q for n, _ in b}
    edits = load_edits(inbox_path)
    out = []
    for raw in (load_json(inbox_path) or {}).get("items", []):
        if raw["name"] not in want:
            continue
        cov = (edits.get("_covered") or {}).get(raw["name"], 0) if raw["name"] in edits else 0
        out.append(f"## {raw['name']}（{len(raw['entries'])} 件・前回の編集は {cov} 件まで）")
        for d in raw["entries"]:
            summ = " ".join(str(d.get("summary") or "").split())[:summary]
            out.append(f"{d['n']} {(d.get('date') or '')[:10]} {d.get('source', '')}｜{d.get('title', '')}" + (f"｜{summ}" if summ else "")
                       + (" ★要紧" if d.get("urgent") else ""))
    return "\n".join(out)


def pick_images(date=None):
    """给 AI 编辑挑图用：按 edit.json 里每条报道，收集原文候选图，拼成带编号的对照图。
    对照图在 PICK_DIR（不进仓库），候选链接写在 PICK_DIR/candidates.json。"""
    import io
    from PIL import Image, ImageDraw
    paths = sorted(INBOX_DIR.glob(f"{date or '????-??-??'}.json"))
    if not paths:
        print("inbox 里没有内容", file=sys.stderr)
        return
    inbox_path = paths[-1]
    inbox, edits = load_json(inbox_path), load_edits(inbox_path)
    todo = {n for n, v in edits.items() if not n.startswith("_") and any(isinstance(s, dict) and not s.get("image") for s in v or [])}
    _live_edit_step("AI が配図を選んでいます", only=todo)
    PICK_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for raw in inbox["items"]:
        entries = [entry_from_dict(d) for d in raw["entries"]]
        for k, story in enumerate(edits.get(raw["name"], []) or []):
            if story.get("image"):   # 前のバッチで選んだ配図はそのまま（分批で同じ報道をもう一度並べない）
                continue
            if story.get("weight") not in PICK_WEIGHTS:   # 省トークン：普通の記事は目で選ばず、出刊の規則（images.pick）に任せる
                continue
            refs = [entries[r - 1] for r in story.get("refs", []) if 0 < r <= len(entries)]
            urls = []
            for e in refs[:3]:
                if e.image and e.image not in urls:
                    urls.append(e.image)
                p = images.page(sources.entry_link(e))
                for u in p.og + p.jsonld + p.body:
                    if u not in urls:
                        urls.append(u)
            thumbs = []
            for u in urls:
                if not images.check(u)[0]:  # 打不开、太大、太小、不是图片的先排除
                    continue
                try:
                    req = urllib.request.Request(u, headers={"User-Agent": sources.USER_AGENT})
                    im = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=15).read())).convert("RGB")
                except Exception:
                    continue
                if im.width < 300 or im.height < 160:
                    continue
                im.thumbnail(PICK_THUMB)
                thumbs.append((u, im))
                if len(thumbs) >= PICK_MAX:
                    break
            key = f"{raw['name']}#{k}"
            out[key] = {"headline": story.get("headline", ""), "current": story.get("image"),
                        "candidates": [u for u, _ in thumbs]}
            if not thumbs:
                continue
            cols = 4
            rows = (len(thumbs) + cols - 1) // cols
            cw, ch = PICK_THUMB[0] + 10, PICK_THUMB[1] + 10
            sheet = Image.new("RGB", (cols * cw, rows * ch), "white")
            draw = ImageDraw.Draw(sheet)
            for i, (_, im) in enumerate(thumbs):
                x, y = (i % cols) * cw + 5, (i // cols) * ch + 5
                sheet.paste(im, (x, y))
                draw.rectangle([x, y, x + 34, y + 26], fill="black")
                draw.text((x + 8, y + 6), str(i + 1), fill="white")
            name = f"{len(out):02d}.jpg"
            sheet.save(PICK_DIR / name, quality=85)
            out[key]["sheet"] = str(PICK_DIR / name)
            print(f"{key}  {story.get('headline', '')}  → {PICK_DIR / name}（{len(thumbs)} 张）")
    (PICK_DIR / "candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"候选链接：{PICK_DIR / 'candidates.json'}")


def _saved_ref(st):
    """防盗链、要带原文网页作 Referer 才拿得到的图（来源名带 images.SAVED）：检查时也带上。"""
    return st.get("url") if images.SAVED in (st.get("image_via") or "") else None


def repair_images():
    """修已经出刊的各期（新的找图规则只管新出刊的，旧几期要补一遍）：
    - 原文已删（404 / 410）的报道撤掉
    - 没有自己图的报道重新找图：没图、用作品封面顶替、网站 logo / 默认图、和别的报道同一张图（先出现的那条留着）、
      图现在下载不了或不合格
    Google 跳转链接先还原；在 inbox 里找回这条报道的原始条目（原标题、自带图），找转载更准。改完重新生成网页。"""
    paths = sorted(REPORTS_DIR.glob("????-??-??.json"))
    reports = [(p, load_json(p)) for p in paths]
    raw = {}  # 链接 → inbox 里的原始条目
    for ip in sorted(INBOX_DIR.glob("????-??-??.json")):
        for it in load_json(ip)["items"]:
            for d in it["entries"]:
                for key in (d["url"], d.get("link")):
                    if key:
                        raw.setdefault(key, d)
    first_user = {}  # 图 → 最早用它的报道链接
    for _, rep_ in reports:
        for b in rep_["items"]:
            for st in b["stories"]:
                if st.get("image") and st.get("image_via") != "作品封面":
                    first_user.setdefault(st["image"], st["url"])
    used = set(first_user)
    fixed = dropped = still = 0
    for path, rep_ in reports:
        changed = False
        for b in rep_["items"]:
            keep = []
            for st in b["stories"]:
                img = st.get("image")
                bad = (not img or st.get("image_via") == "作品封面" or "验证不了" in (st.get("image_via") or "")
                       or images.is_bing_thumb(img)  # Bing 的缩略图是 Bing 裁过的（横长的图变成竖的一截），先找原文的图
                       or not images.check(img, _saved_ref(st))[0]  # 图后来被删、或者不合格（太小、打不开）
                       or images.GENERIC.search(urllib.parse.urlparse(img).path)
                       or first_user.get(img) not in (None, st["url"]))
                d = raw.get(st["url"])
                e = entry_from_dict(d) if d else sources.Entry(title=st["headline"], url=st["url"], published=None, source="")
                url = sources.entry_link(e) if "news.google.com" in st["url"] else st["url"]
                if url != st["url"]:
                    st["url"], changed = url, True
                if images.gone(url):
                    print(f"  [修复] {b['name']} | {st['headline'][:30]} | 原文已删，撤掉", file=sys.stderr)
                    dropped, changed = dropped + 1, True
                    continue
                if bad:
                    if img and img in used and first_user.get(img) == st["url"]:
                        used.discard(img)
                    res = images.pick(None, [e], url, avoid=used)
                    if res.image:
                        st["image"], st["image_via"], changed = res.image, res.source, True
                        used.add(res.image)
                        fixed += 1
                    elif img and (images.GENERIC.search(urllib.parse.urlparse(img).path) or first_user.get(img) != st["url"]
                                  or "验证不了" in (st.get("image_via") or "") or not images.check(img, _saved_ref(st))[0]):
                        st["image"], changed = None, True  # 错的图宁可不放（网页上用作品封面或作品名封面块）
                        st.pop("image_via", None)
                        still += 1
                    else:
                        still += 1
                    print(images.log_line(b["name"], st["headline"], res), file=sys.stderr)
                keep.append(st)
            b["stories"] = keep
        if changed:
            save_json(path, rep_)
    print(f"修复：{fixed} 条找到自己的图 · {dropped} 条原文已删撤掉 · {still} 条还是没图", file=sys.stderr)
    hd_images()
    write_page()


def _inbox_counts(days=3):
    """最近の inbox の版面ごとの記事数（収集の前後で比べて、新着の数をログに残す）。"""
    out = {}
    for path in sorted(INBOX_DIR.glob("????-??-??.json"))[-days:]:
        for b in (load_json(path) or {}).get("items", []):
            out[b.get("name")] = out.get(b.get("name"), 0) + len(b.get("entries") or [])
    return out


def logged_ingest():
    """収集して、新着の数・かかった時間・サーバーの様子を実行ログ（state/log/collect.json）に書く。"""
    import time
    import resources
    import runlog
    t0 = time.time()
    before = _inbox_counts()
    try:
        path = ingest()
    except Exception as e:
        runlog.add("collect", f"収集に失敗：{str(e)[:120]}", "error")
        raise
    after = _inbox_counts()
    new = {k: v - before.get(k, 0) for k, v in after.items() if v > before.get(k, 0)}
    top = "、".join(f"{k} {v}" for k, v in sorted(new.items(), key=lambda kv: -kv[1])[:5])
    runlog.add("collect", f"新着 {sum(new.values())} 件（{len(new)} 版面）" + (f"：{top}" if top else ""),
               "ok" if new else "info", count=sum(new.values()), secs=round(time.time() - t0), workers=COLLECT_WORKERS,
               res=resources.snapshot())
    deferred, failed = LAST_INGEST.get("deferred") or [], LAST_INGEST.get("failed") or {}
    if deferred:   # 次の回はこの版面から取る（deferred_from_log）
        runlog.add("collect", f"時間切れで {len(deferred)} 版面を次の回へ（{COLLECT_DEADLINE_MIN} 分）：" + "、".join(deferred[:6]),
                   "warn", deferred=list(deferred))
    if failed:
        runlog.add("collect", f"取得・処理に失敗した {len(failed)} 版面は空で続けた：" + "、".join(f"{k}（{v}）" for k, v in list(failed.items())[:3]),
                   "warn", failed=dict(failed))
    try:
        health = intel.health()   # 情報員の情報源ごとの様子（取れなかった所は名前と理由）
    except Exception as e:  # noqa: BLE001  ログの 1 行が抜けるだけ：収集の結果（inbox）の push を止めない
        health = ""
        print(f"情報員の様子が読めない：{e}", file=sys.stderr)
    if health:
        print("情報員：" + health, file=sys.stderr)
        runlog.add("collect", "情報員 " + health, "info")
    return path


def logged_publish(path=None):
    """出刊して、実行ログに書く（Actions の自動出刊は publish、Claude の AI 編集は edit に分けて書く）。"""
    import os
    import runlog
    proc = "publish" if os.environ.get("GITHUB_ACTIONS") else "edit"
    latest = path or (sorted(INBOX_DIR.glob("????-??-??.json")) or [None])[-1]
    try:
        publish(path)
    except Exception as e:
        runlog.add(proc, f"出刊に失敗：{str(e)[:120]}", "error")
        raise
    if latest:
        latest = pathlib.Path(latest)
        edit = load_json(INBOX_DIR / f"{latest.stem}.edit.json")
        n = len([k for k in (edit or {}) if not k.startswith("_")])
        import resources
        if proc == "edit":
            _log_edit_batch(latest, edit, n)
            return
        runlog.add(proc, f"{latest.stem} を出刊" + (f"（AI 編集 {n} 版面）" if edit else "（AI 編集なし・キーワードの規則）"), "ok",
                   res=resources.snapshot(), **({"tokens": TOKENS["in"] + TOKENS["out"], "tokens_in": TOKENS["in"]} if TOKENS["calls"] else {}))


def _log_edit_batch(latest, edit, n):
    """AI 編集の 1 バッチ（EDITING.md 第 4 步：5 版面ずつ編集 → 出刊 → push）を実行ログ（state/log/edit.json）に 1 行。
    このバッチで編集が終わった版面・記事の本数・このバッチで使ったトークン（usage.py：セッションの記録から本物の数字。
    前のバッチの出刊からの差）。管理ページのライブログ・「AI 編集のトークン」に出る。"""
    import resources
    import runlog
    import usage
    try:
        run = json.loads(LIVE_EDIT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        run = {}
    done = _edit_done_boards(latest)
    cur = run.get("current")
    new = sorted({cur} if cur and cur in done else done - set(run.get("done") or []))   # edit-next が渡した版面（やり直しの版面は前から済でも数える）
    if cur and cur in (edit_control().get("redo") or []):
        set_edit_control(redo_clear=cur)   # やり直しが終わった
    now_u = usage.session_usage()
    batch_u = usage.diff(now_u, run.get("usage"))
    no = int(run.get("batch") or 0) + 1
    left = sum(len(b) for b in edit_queue(latest.stem))   # まだ整理待ちの版面
    stories = sum(len(v or []) for k, v in (edit or {}).items() if k in new)
    if run:
        run.update(batch=no, done=sorted(done), usage=now_u, current=None)
        LIVE_EDIT_FILE.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    _live_edit_step("編集済み · 網页への反映を待っています", LIVE_AFTER_MIN, only=set(new))
    names = "、".join(new[:6]) + (f" ほか {len(new) - 6}" if len(new) > 6 else "")
    text = (f"{latest.stem} 第 {no} バッチを出刊：{names or '（新しく終わった版面なし）'}（{len(new)} 版面・{stories} 本"
            + (f"・残り {left} 版面" if left else "・今日の整理待ちは全部終わり") + "）" + (f" · {usage.short(batch_u)}" if batch_u else ""))
    extra = {"batch": no, "boards": new, "stories": stories, "left": left, "edited": n, "run": run.get("start")}
    if batch_u:
        extra.update(tok=batch_u, tokens=usage.total(batch_u))
    if not left and run.get("start"):
        extra["secs"] = round(time.time() - run["start"])   # 1 回分の長さ（「あと約 N 分」用）は最後のバッチだけ
        if now_u:
            extra["run_tok"] = now_u   # この回（セッション）全部のトークン
    runlog.add("edit", text, "ok", res=resources.snapshot(), **extra)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", nargs="?", default="all",
                        choices=["all", "ingest", "publish", "render", "notify-urgent", "notify-weekly", "notify-new-items", "notify-changes", "notify-wishlist", "recommend", "pick-images", "unedited", "new-items", "repair-images", "sync-db", "photos", "take-items", "heat", "audit-match", "live-edit", "edit-queue", "edit-next", "edit-brief", "hd-images", "prune-reddit", "retry-images"])
    parser.add_argument("date", nargs="?", help="pick-images 用：指定日期，默认最新一期")
    parser.add_argument("--only", help="unedited / audit-match 用：只看这些关注项（用「、」分隔）；edit-brief 用：第几批")
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印，不写文件")
    args = parser.parse_args()
    if args.dry_run:
        ingest(dry_run=True)
    elif args.step == "repair-images":
        repair_images()
    elif args.step == "retry-images":
        retry_images()
        write_page()
    elif args.step == "prune-reddit":
        prune_reddit()
        write_page()
    elif args.step == "hd-images":
        hd_images()
        write_page()
    elif args.step == "pick-images":
        pick_images(args.date)
    elif args.step == "new-items":
        print("、".join(new_item_names()))
    elif args.step == "unedited":
        print("、".join(unedited(args.only.split("、") if args.only is not None else None)))
    elif args.step == "render":
        stale = stale_report()
        if stale:   # edit.json が報告に入っていない（競合で落ちた）→ 出刊し直してから網页を作る
            print(f"{stale.stem} の報告が最新の edit.json を取り込んでいない → 出刊し直します", file=sys.stderr)
            publish(stale, heal=True)
        else:
            write_page()
    elif args.step == "ingest":
        logged_ingest()
        update_heat()
        sync_db()
    elif args.step == "live-edit":
        live_edit()
    elif args.step == "edit-brief":
        print(edit_brief(batch=int(args.only) if args.only and args.only.isdigit() else None))
    elif args.step == "edit-next":
        what, why = edit_next()
        print(f"{what} {why}".strip())
    elif args.step == "edit-queue":
        for i, b in enumerate(edit_queue(), 1):
            print(f"第 {i} 批：" + "、".join(f"{n}（{c}）" for n, c in b))
    elif args.step == "audit-match":
        audit_match(only=args.only.split("、") if args.only else None)
    elif args.step == "heat":
        update_heat()
        write_page()
    elif args.step == "sync-db":
        sync_db()
    elif args.step == "publish":
        logged_publish()
    elif args.step == "notify-urgent":
        import notify
        notify.urgent(pages_url(load_config()[0]))
    elif args.step == "recommend":
        recommend(force_discover=True)
        write_page()
    elif args.step == "notify-wishlist":
        import notify
        notify.wishlist(pages_url(load_config()[0]))
        notify.hesitate(pages_url(load_config()[0]))
    elif args.step == "notify-changes":
        import notify
        notify.changes(pages_url(load_config()[0]))
    elif args.step == "notify-new-items":
        import notify
        notify.new_items(pages_url(load_config()[0]))
    elif args.step == "notify-weekly":
        import notify
        if not notify.weekly(pages_url(load_config()[0])):   # 送れなかったら失敗で終わる（digest.yml が心拍に「送れなかった」と書く）
            sys.exit(1)
    elif args.step == "photos":
        export_photos()
    elif args.step == "take-items":
        take_item_requests()
    else:
        take_item_requests()  # 设置页上新增的关注项先写进 items.yaml，这次就开始收集
        export_photos()  # 拍照加愿望：导出新照片给 Claude 定时任务处理
        path = logged_ingest()
        update_heat()
        if path:
            logged_publish(path)
        sync_db()


if __name__ == "__main__":
    main()
