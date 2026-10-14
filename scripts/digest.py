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
import re
import sys
import urllib.parse
import urllib.error
import urllib.request
import zoneinfo

import yaml

import images
import render
import sources
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
SIZES_PUSHED_FILE = STATE_DIR / "sizes_pushed.json"   # items.yaml 里的 size 上次同步进数据库时是什么
INBOX_DIR = ROOT / "inbox"
DOCS_DIR = ROOT / "docs"
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
- headline：中文，22 字以内，像报纸标题，有信息量。
- highlight：headline 里最关键的几个字（日期、数字、结论），必须原样出现在 headline 中；没有就留空。
- blurb：一句话补充（40 字以内），只给头条和 hero 写，其余留空。
- refs：这条报道依据的条目编号。
- Reddit 帖子是玩家讨论（摘要里有赞数、评论数），热度高时可以归纳成一条“社区热议”报道。
- 来源优先用国外媒体（含港台、日韩、欧美）：同一件事国外媒体也报了，refs 第一个放国外媒体；
  标了（大陆网站）的条目只在这件事只有大陆网站报道时才用。
- 外文一律译成中文；传闻要在标题里注明“传闻”。"""

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
    return entries


TRUSTED_SOURCES = {"Steam 官方公告"}


def title_key(title):
    return "t:" + re.sub(r"\W+", "", title.lower())


def _norm(text):
    return re.sub(r"\s+", "", text.lower())


# 图片画廊、附图页这类“同一篇文章的分页”，标题只差编号，直接丢掉
JUNK_PATTERNS = [r"^画像ギャラリー", r"\d+枚目の写真", r"写真・画像$", r"^图集", r"^사진\s*\d"]
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


def filter_entries(entries, item, settings, seen, now, known=()):
    names = [item["name"], *(item.get("keywords") or []), *(item.get("match") or [])]
    since = now - dt.timedelta(days=settings.get("lookback_days", 7))
    exclude = [w.lower() for w in item.get("exclude") or []]
    # 新闻搜索会混入不相关结果：标题或摘要里必须出现某个匹配词（忽略大小写和空格）
    match = [_norm(w) for w in item.get("match") or item.get("keywords") or [item["name"]]]
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
    skip_sources = set(settings.get("exclude_sources", ["YouTube"])) | set(item.get("exclude_sources") or [])
    # 标题相近的转载只留先看到的那条：国外网站先看，同一件事有国外报道就不收大陆网站的；最后再按时间排回来
    for e in sorted(best.values(), key=lambda e: (sources.is_domestic(e.url, e.source),
                                                  -(e.published or now).timestamp())):
        key = title_key(e.title)
        if e.url in seen or key in seen or e.source in skip_sources:
            continue
        if any(re.search(p, e.title) for p in JUNK_PATTERNS):
            continue
        g = _title_grams(e.title, names)
        if any(_similar(g, h) for h in grams):
            continue
        if e.published and e.published < since:
            continue
        if any(w in e.title.lower() for w in exclude):
            continue
        trusted = e.source in TRUSTED_SOURCES or e.source in {f"r/{s}" for s in item.get("subreddits") or []}
        # Reddit 全站搜索来的帖子：正文是闲聊，「from Season 5」这种说法到处都是，匹配词必须出现在标题里
        text = e.title if e.source == "Reddit" else e.title + e.summary
        if not trusted and not any(w in _norm(text) for w in match):
            continue
        grams.append(g)
        out.append(e)
    # Reddit 帖子多且杂（同人图、闲聊），单独限额，不和媒体报道抢名额
    out.sort(key=lambda e: e.published or now, reverse=True)
    news = [e for e in out if not e.source.startswith("r/") and e.source != "Reddit"]
    posts = [e for e in out if e not in news]
    cap = item.get("max_entries") or settings.get("max_entries_per_item", 30)
    return news[:cap] + posts[: settings.get("max_reddit_per_item", 10)]


def status_facts(item, settings, facts):
    """Steam 价格、番剧/剧集播出状态等“当前状态”。返回 (状态列表, 封面图)。"""
    tz = zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))
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
        line = f"[{i}] {date} | {e.source}{'（大陆网站）' if sources.is_domestic(e.url, e.source) else ''} | {e.title}"
        if e.summary:
            line += f" | {e.summary}"
        lines.append(line)
    return "\n".join(lines)


def edit_stories(client, model, item, entries):
    """让 LLM 把条目编成报道；失败返回 None。"""
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
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:  # API 错误或凭据错误：这一项退回原标题，不影响整期
        print(f"  [警告] LLM 调用失败：{type(e).__name__}: {e}", file=sys.stderr)
        return None
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
    media = [i for i, e in enumerate(entries, 1) if not sources.is_reddit(e)]

    def hits(e):
        return sum(w in e.title.lower() for w in words)

    def domestic(e):
        return sources.is_domestic(e.url, e.source)

    def heat(i):
        return sum(1 for j in media if j != i and _same_topic(topics[i], topics[j]))

    def score(pair):
        i, e = pair
        if by_heat:
            return (i in urgent, heat(i), not sources.is_reddit(e), hits(e), not domestic(e),
                    bool(e.image) or "news.google.com" not in e.url, -i)
        return (i in urgent, hits(e) > 0, not sources.is_reddit(e), hits(e), not domestic(e),
                bool(e.image) or "news.google.com" not in e.url, -i)

    candidates = [(i, e) for i, e in enumerate(entries, 1)
                  if (hits(e) or not sources.is_reddit(e)) and not side_mention(e.title, item)]
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


def attach_media(stories, entries, cover, name="", stats=None, used=None):
    """给每条报道配链接和图（候选、检查和回退见 images.pick），没图的头条用作品封面。
    一条报道有好几个来源时，国外来源排前面（链接和配图都先用它），中国大陆网站垫后。
    原文已经删了（404 / 410）的来源不用；来源全删了的报道不出刊。
    出刊时补到的图写回条目（entry.image / image_via），还原出的原文地址写回 entry.link，publish 会存回 inbox，下次直接用。
    used：这一期已经用掉的图，别的报道不再用（几张卡片同一张图很难看）。
    每条报道的配图结果打一行日志，stats 记整期汇总。返回要出刊的报道。"""
    used = set() if used is None else used
    out = []
    for s in stories:
        refs = sorted((entries[r - 1] for r in s.pop("refs")), key=lambda e: sources.is_domestic(e.url, e.source))
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
        res = images.pick(s.get("image"), refs, s["url"], avoid=used)
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
    if not WISHLIST_FILE.exists():
        return []
    return (yaml.safe_load(WISHLIST_FILE.read_text(encoding="utf-8")) or {}).get("wishlist") or []


PICK_COUNT = 5       # 「我会喜欢？」一批几条（1 大 + 4 小正好排满）
PICK_BATCHES = 6     # 候选池有几批那么多：网页每次打开随机抽一批（看过的少抽），「换一批」再抽
EXPLORE_AFTER = 2    # 前几批只放够分的；之后可以放差一点的（少命中一个标签），网页上标「换换口味」
PICK_DAYS = 14       # 从最近几天收集到的消息里挑
PICK_THRESHOLD = 5   # 每命中一个喜好标签 2 分，和愿望清单同一个关注项再加 1 分；至少 5 分才推荐


DISCOVER_HOURS = 12    # 「同类新消息」每隔多久搜一次
DISCOVER_PICKS = 4     # 「我会喜欢？」每批放几条同类新消息
FOLLOW_PER_ITEM = 4    # 同类新消息每个关注项最多准备几条（找配图要花时间，不跟着批数无限加）


HESITATE = "纠结"   # 愿望清单里还在犹豫买不买的状态：它的 similar 也会每天搜，找类似的好产品


def discover(force=False):
    """按 items.yaml 里每个关注项的 similar（同类搜索词）抓 Google 新闻，去掉已经在关注清单里的作品。
    愿望清单里 status 是「纠结」的东西也一样：按它的 similar 搜类似的好产品（条目带 "wish": true）。
    结果存 state/discover.json；每 DISCOVER_HOURS 小时最多搜一次。"""
    settings, items = load_config()
    old = load_json(DISCOVER_FILE) or {}
    now = dt.datetime.now(dt.timezone.utc)
    if not force and old.get("at") and now - dt.datetime.fromisoformat(old["at"]) < dt.timedelta(hours=DISCOVER_HOURS):
        return old.get("entries", [])
    tracked = {_norm(w) for i in items for w in (i.get("match") or i.get("keywords") or [i["name"]])}
    since = now - dt.timedelta(days=settings.get("lookback_days", 7))
    out, grams = [], []
    hesitating = [dict(w, _wish=True) for w in load_wishlist() if w.get("status") == HESITATE]
    for item in items + hesitating:
        for q in item.get("similar") or []:
            try:
                found = sources.google_news(q["query"], settings.get("lookback_days", 7), NEWS_LANGS[q.get("lang", "zh-CN")])
            except Exception as err:
                print(f"  [同类] {q['query']} 失败：{err}", file=sys.stderr)
                continue
            for e in found[:20]:
                if e.source == "YouTube" or any(re.search(p, e.title) for p in JUNK_PATTERNS):
                    continue
                if e.published and e.published < since:
                    continue
                if any(w and w in _norm(e.title + e.summary) for w in tracked):  # 已经在关注的不算“新发现”
                    continue
                if not all(_like_hit(n, (e.title + " " + e.summary).lower()) for n in q.get("need") or []):
                    continue
                g = _title_grams(e.title, [])
                if any(_similar(g, x) for x in grams):
                    continue
                grams.append(g)
                out.append({"title": e.title, "url": e.url, "source": e.source, "summary": e.summary, "image": e.image,
                            "date": e.published.isoformat() if e.published else "", "item": item["name"], "label": q["label"],
                            **({"wish": True} if item.get("_wish") else {})})
    save_json(DISCOVER_FILE, {"at": now.isoformat(), "entries": out})
    print(f"同类新消息：{len(out)} 条", file=sys.stderr)
    return out


def _like_hit(keyword, text):
    """喜好关键词可以用 | 写同一个东西的几种写法（Snoopy|スヌーピー|史努比），命中任意一种就算。"""
    return any(alt.strip().lower() in text for alt in str(keyword).split("|") if alt.strip())


def _like_key(keyword):
    return str(keyword).split("|")[0].strip().lower()


def supabase(path, body=None, prefer=None, method=None):
    """用 secret key（SUPABASE_SERVICE_KEY）调 Supabase 的数据接口。没配置时返回 None。"""
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


WISH_IMAGE_DIR = DOCS_DIR / "wishlist"


def _save_wish_image(url):
    """把新闻配图存进 docs/wishlist/（别直接引用外站图，可能防盗链或失效）。存不下来就返回原链接。"""
    if not url or not url.startswith("http"):
        return None
    name = f"news-{hashlib.sha1(url.encode()).hexdigest()[:10]}.jpg"
    try:
        import io
        from PIL import Image
        req = urllib.request.Request(url, headers={"User-Agent": sources.USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            img = Image.open(io.BytesIO(resp.read())).convert("RGB")
        img.thumbnail((1200, 1200))
        WISH_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        img.save(WISH_IMAGE_DIR / name, "JPEG", quality=90)
        return name
    except Exception as err:
        print(f"  [心愿单] 配图存不下来，用原链接：{err}", file=sys.stderr)
        return url


def wish_entry_yaml(row, image, today, watch):
    """一条从新闻加进来的愿望，写成 wishlist.yaml 里的一段（字符串都用 JSON 引号，YAML 也认）。"""
    q = lambda v: json.dumps(v, ensure_ascii=False)
    lines = [f"  - name: {q(row['title'])}"]
    if image:
        lines.append(f"    image: {q(image)}")
    if row.get("source"):
        lines.append(f"    shop: {q(row['source'])}")
    lines.append(f"    url: {q(row['url'])}")
    lines.append(f"    added: {today}")
    lines.append("    status: 想要")
    if watch:
        lines.append(f"    watch: {q(watch)}")
    where = f"「{row['work']}」的" if row.get("work") else ""
    lines.append(f"    note: {q(f'从{where}新闻里点「加入心愿单」加进来的；名字、价格、喜好标签还没整理（跟 Claude 说「整理愿望清单」）')}")
    return "\n".join(lines) + "\n"


def take_wish_requests():
    """新闻卡片上点了「♥ 加入心愿单」的：从数据库 wish_requests 表读出待处理的，加进 wishlist.yaml
    （直接在文件末尾追加，不动原来的内容和注释），再标成 done；已经在愿望清单里的标成 skipped。
    推送后照常会在愿望清单页面出现、发 Discord 通知。"""
    try:
        rows = supabase("wish_requests?status=eq.pending&select=id,url,title,work,image,source&order=id.asc")
    except Exception as err:
        hint = "（还没建表？在 Supabase 的 SQL Editor 里运行 db/wish_requests.sql）" if "PGRST205" in str(err) else ""
        print(f"  [心愿单] 读加入请求失败{hint}：{err}", file=sys.stderr)
        return
    if not rows:
        return
    settings, items = load_config()
    names = {i["name"] for i in items}
    today = dt.datetime.now(zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))).date().isoformat()
    have = {w.get("url") for w in load_wishlist()}
    added, skipped, text = [], [], ""
    for r in rows:
        host = (urllib.parse.urlsplit(r["url"]).hostname or "").lower()
        # 已经在愿望清单里的、测试用的保留域名（example.com 之类，RFC 2606，不可能是真新闻）都跳过
        if r["url"] in have or host.split(".")[-2:] in (["example", "com"], ["example", "org"], ["example", "net"]) \
                or host.endswith(".example"):
            skipped.append(r["id"])
            continue
        have.add(r["url"])
        watch = r.get("work") if r.get("work") in names else None
        text += "\n" + wish_entry_yaml(r, _save_wish_image(r.get("image")), today, watch)
        added.append(r)
    if text:
        old = WISHLIST_FILE.read_text(encoding="utf-8")
        new = old.rstrip("\n") + "\n" + text
        try:
            assert len((yaml.safe_load(new) or {}).get("wishlist") or []) == len(load_wishlist()) + len(added)
        except Exception as err:
            print(f"  [心愿单] 追加后 wishlist.yaml 不对，这次不加：{err}", file=sys.stderr)
            return
        WISHLIST_FILE.write_text(new, encoding="utf-8")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for status, ids in (("done", [r["id"] for r in added]), ("skipped", skipped)):
        if ids:
            try:
                supabase(f"wish_requests?id=in.({','.join(map(str, ids))})", {"status": status, "handled_at": now},
                         "return=minimal", method="PATCH")
            except Exception as err:  # 标不上的下次还会读到，但链接已经在愿望清单里了，会被当成 skipped
                print(f"  [心愿单] 标记请求失败：{err}", file=sys.stderr)
    for r in added:
        print(f"心愿单：从新闻加入「{r['title'][:40]}」", file=sys.stderr)


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


SIZE_STORIES = {"S": 3, "M": 5, "L": 8}   # 篇幅 → 每期最多几条报道（网页上直接显示多高见 render.SIZE_HEIGHT）


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
        if r.get("work") and r.get("kind") in ("story", "wish"):
            keys.add(WORK_KEY + r["work"])
        for k in keys:
            taste[k] = taste.get(k, 0) + r["vote"]
    return {k: v for k, v in taste.items() if v}


def taste_bonus(taste, keys):
    """一条候选按学到的口味加减几分，并列出是哪些标签 / 关键词起的作用（网页上写明理由）。"""
    used = sorted(((k, taste[k]) for k in dict.fromkeys(keys) if k in taste), key=lambda kv: -abs(kv[1]))
    total = max(TASTE_LIMIT[0], min(TASTE_LIMIT[1], sum(v for _, v in used)))
    return total, [[k, v] for k, v in used]


def recommend(force_discover=False):
    """「我会喜欢？」：按愿望清单里每件东西的 likes（喜好标签），从最近收集到的所有消息里打分挑推荐。
    不让 AI 联网，只用已经收集到的消息；结果写进 state/recommend.json，网页读它。"""
    wishes = [w for w in load_wishlist() if w.get("likes")]
    common = {_like_key(k) for w in wishes for label, kws in w["likes"].items()
              if label in (w.get("basics") or []) for k in kws}
    old = load_json(RECOMMEND_FILE) or {}
    images = old.get("images", {})
    wish_urls = {w.get("url") for w in wishes}
    votes = load_feedback()
    taste = learn_taste(votes, wishes, common)
    disliked = {r["url"] for r in votes if r["vote"] < 0}
    disliked_grams = [_title_grams(r.get("title") or "", []) for r in votes if r["vote"] < 0]
    pool = []
    for path in sorted(INBOX_DIR.glob("????-??-??.json"))[-PICK_DAYS:]:
        for item in load_json(path)["items"]:
            for d in item["entries"]:
                text = (d["title"] + " " + d.get("summary", "")).lower()
                best = None
                for w in wishes:
                    hits = [label for label, kws in w["likes"].items() if any(_like_hit(k, text) for k in kws)]
                    words = {_like_key(k) for kws in w["likes"].values() for k in kws if _like_hit(k, text)}
                    score = 2 * len(hits) + (1 if w.get("watch") == item["name"] else 0)
                    # 学到的口味只看具体的喜好，基本属性（马克杯、限定款）不跟着投票涨跌
                    basics = set(w.get("basics") or [])
                    bonus, why = taste_bonus(taste, [h for h in hits if h not in basics] + sorted(words - common)
                                             + [WORK_KEY + item["name"]])
                    if hits and (not best or score + bonus > best[0]):
                        best = (score + bonus, w, hits, words, why)
                if best and best[0] >= PICK_THRESHOLD - 1:
                    pool.append((best[0], d.get("date") or path.stem, d, item["name"], *best[1:]))
    # 同分时，命中具体喜好（猫、角色造型……）的排在只命中基本属性（限定、马克杯）的前面
    pool.sort(key=lambda x: (x[0], len(set(x[5]) - set(x[4].get("basics") or [])), x[1]), reverse=True)
    picks, grams, used = [], list(disliked_grams), set()
    for score, date, d, work, w, hits, words, why in pool:
        g = _title_grams(d["title"], [])
        key = words - common
        if len(picks) % PICK_COUNT == 0:
            used = set()  # 每一批各自分散
        # 推荐要分散：同一批里两条靠同一个具体关键词命中（如都是 Snoopy）只留一条；basics 里的基本属性（限定、马克杯）不算
        # 踩过的消息（和别家报道的同一件事）不再推荐
        if any(_similar(g, x) for x in grams) or key & used:
            continue
        explore = score < PICK_THRESHOLD
        if explore and len(picks) < PICK_COUNT * EXPLORE_AFTER:
            continue  # 「换换口味」的只放进后面几批
        url = sources.resolve_url(d["url"])
        if url in wish_urls or url in disliked or any(p["url"] == url for p in picks):
            continue
        used |= key
        if url not in images:
            images[url] = find_image(d.get("image"), [entry_from_dict(d)], url)
        grams.append(g)
        picks.append({"title": d["title"], "url": url, "source": d["source"], "date": date[:10], "work": work,
                      "image": images[url], "because": w["name"], "hits": hits, "score": score, "kind": "wish",
                      "words": sorted(key), "taste": why, "batch": len(picks) // PICK_COUNT,
                      **({"explore": True} if explore else {}),
                      **({"hesitating": True} if w.get("status") == HESITATE else {})})
        if len(picks) >= PICK_COUNT * PICK_BATCHES:
            break

    # 同类新消息：按关注项轮流取最新的一条（有图的优先），每个关注项最多一条。
    # 投票学到的口味决定先后：常赞的同类排前面，净踩两次以上的同类先不推荐
    found = sorted(discover(force_discover), key=lambda x: x.get("date") or "", reverse=True)
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
            if url in disliked or url in seen_urls:
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
        follow.append({"title": x["title"], "url": url, "source": x["source"], "date": (x.get("date") or "")[:10],
                       "work": x["item"], "image": img, "because": x["item"], "hits": [x["label"]],
                       "kind": "hesitate" if x.get("wish") else "follow", "batch": len(follow) // DISCOVER_PICKS,
                       "words": [], "taste": taste_bonus(taste, [x["label"]])[1]})
    picks += follow
    keep = {p["url"] for p in picks}
    save_json(RECOMMEND_FILE, {"picks": picks, "images": {u: i for u, i in images.items() if u in keep}})
    print(f"我会喜欢？：{len(picks) - len(follow)} 条按愿望清单 + {len(follow)} 条同类新消息，"
          f"共 {1 + max([p['batch'] for p in picks] or [0])} 批（学自 {len(votes)} 次投票）", file=sys.stderr)


def write_page():
    issues = [load_json(p) for p in sorted(REPORTS_DIR.glob("????-??-??.json"), reverse=True)[:ISSUES_ON_PAGE]]
    issues = [i for i in issues if i]
    if not issues:
        return
    DOCS_DIR.mkdir(exist_ok=True)
    settings, items = load_config()
    tz = zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))
    updated = dt.datetime.now(tz).strftime("%m.%d %H:%M")
    html_ = render.render(issues, settings.get("nav_style", "line"), [i["name"] for i in items], updated,
                          load_wishlist(), (load_json(RECOMMEND_FILE) or {}).get("picks", []),
                          {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}, load_sizes())
    (DOCS_DIR / "index.html").write_text(html_, encoding="utf-8")
    wishes = load_wishlist()
    if wishes:
        works = render.collect(issues, [i["name"] for i in items])
        finds = [x for x in (load_json(DISCOVER_FILE) or {}).get("entries", []) if x.get("wish")]
        (DOCS_DIR / "wishlist.html").write_text(render.render_wishlist(wishes, works, updated, finds), encoding="utf-8")
    (DOCS_DIR / "settings.html").write_text(render.render_settings(
        [{"name": i["name"], "section": section_of(i), "subtitle": i.get("subtitle", ""),
          "size": load_sizes().get(i["name"], "M")} for i in items],
        {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}, updated), encoding="utf-8")
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
    items = config.get("items") or []
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
    return d


def entry_from_dict(d):
    return sources.Entry(title=d["title"], url=d["url"], source=d["source"], summary=d.get("summary", ""),
                         image=d.get("image", ""), image_via=d.get("image_via", ""), link=d.get("link", ""),
                         published=dt.datetime.fromisoformat(d["date"]) if d.get("date") else None)


def is_urgent(e, item):
    """要紧消息：标题命中 items.yaml 里该项的 urgent_patterns（正则）。
    Reddit / YouTube 不算（传闻和二手消息多，避免误报）。"""
    if e.source.startswith("r/") or e.source in ("Reddit", "YouTube"):
        return False
    return any(re.search(p, e.title, re.I) for p in item.get("urgent_patterns") or [])


def merge_inbox(old, new):
    """同一天多次运行：新条目接在已有条目后面（编号顺延），状态以最新为准但保留“当天有变化”。"""
    by_name = {i["name"]: i for i in old["items"]}
    for item in new["items"]:
        cur = by_name.get(item["name"])
        if cur is None:
            old["items"].append(item)
            continue
        start = len(cur["entries"])
        for k, entry in enumerate(item["entries"], 1):
            cur["entries"].append({**entry, "n": start + k})
        changed_before = {f["label"] for f in cur["facts"] if f["changed"]}
        cur["facts"] = [{**f, "changed": f["changed"] or f["label"] in changed_before} for f in item["facts"]] or cur["facts"]
        cur["cover"] = cur.get("cover") or item.get("cover")
    return old


def ingest(dry_run=False):
    """收集本期原始条目到 inbox/。返回写入的文件路径（没有新内容时返回 None）。"""
    settings, items = load_config()
    now = dt.datetime.now(dt.timezone.utc)
    # “每天一期”按你所在时区的日期划分（默认北京时间）
    today = now.astimezone(zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))).date().isoformat()
    seen, facts = seen_from_inbox(), load_json(FACTS_FILE)
    known = recent_titles()

    inbox_items = []
    for item in items:
        print(f"抓取：{item['name']}", file=sys.stderr)
        # 新加的关注项第一次收集时往前多看几周，补上加入之前的报道；之后照常只看 lookback_days
        backfill = not has_history(item["name"])
        conf = dict(settings, lookback_days=settings.get("first_lookback_days", 42)) if backfill else settings
        if backfill:
            print(f"  第一次收集：往前看 {conf['lookback_days']} 天", file=sys.stderr)
        compare = known.get(item["name"], [])
        if item.get("dedupe_others"):  # 别的关注项已经收过的同一件事，这一项不再重复收
            compare = compare + [t for name, ts in known.items() if name != item["name"] for t in ts]
        entries = filter_entries(collect(item, conf), item, conf, seen, now, compare)
        print(f"  新条目 {len(entries)} 条", file=sys.stderr)
        if dry_run:
            print(f"===== {item['name']} =====\n{format_entries(entries)}\n")
            continue
        item_facts, status_cover = status_facts(item, settings, facts)
        if not entries and not any(f["changed"] for f in item_facts):
            continue
        inbox_items.append({
            "name": item["name"],
            "priority": item.get("priority", ""),
            **({"backfill": True} if backfill else {}),
            "facts": item_facts,
            "cover": find_cover(item, status_cover),
            # 补抓的是旧闻，不算要紧，不发 Discord
            "entries": [{**entry_to_dict(n, e), "urgent": not backfill and is_urgent(e, item)}
                        for n, e in enumerate(entries, 1)],
        })
        for e in entries:
            seen.update((e.url, title_key(e.title)))
        known.setdefault(item["name"], []).extend(e.title for e in entries)

    if dry_run:
        return None
    save_json(FACTS_FILE, facts)
    if not inbox_items:
        print("本期没有新消息", file=sys.stderr)
        return None
    path = INBOX_DIR / f"{today}.json"
    data = {"date": today, "items": inbox_items}
    if path.exists():  # 当天已经收集过：合并进去
        data = merge_inbox(load_json(path), data)
    save_json(path, data)
    urgent = sum(e.get("urgent", False) for i in inbox_items for e in i["entries"])
    if urgent:
        print(f"  其中要紧消息 {urgent} 条", file=sys.stderr)
    print(f"已收集：{path.relative_to(ROOT)}", file=sys.stderr)
    return path


def load_edits(inbox_path):
    """读取人工 / Claude 写的编排：inbox/YYYY-MM-DD.edit.json，格式：
    {"关注项名称": [{"headline": "中文标题", "highlight": "标题里要强调的字", "blurb": "一句话",
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


SECTION_BY_TYPE = {"game": "游戏", "anime": "影视", "show": "影视", "product": "好物", "category": "好物", "event": "演出"}


def section_of(item):
    """头版上的板块。"""
    return item.get("section") or SECTION_BY_TYPE.get(item.get("type", "product"), "好物")


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


def publish(inbox_path=None):
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

    client = None
    if settings.get("summarize", False) and any(i["name"] not in edits for i in inbox["items"]):
        client = make_client()
        if client is None:
            print("没有可用的 Claude 凭据，改用关键词规则编排", file=sys.stderr)
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
        if raw["name"] in edits and not raw["name"].startswith("_"):
            stories = [dict(s) for s in edits[raw["name"]]]
            for s in stories:
                s.setdefault("highlight", ""), s.setdefault("blurb", ""), s.setdefault("weight", "normal")
                s["refs"] = [r for r in s.get("refs", []) if 0 < r <= len(entries)]
            stories = [s for s in stories if s["refs"]]
            # 编排写好之后当天又来的消息（编号大于 _covered）：先用关键词规则补上，
            # 要紧的放最前面做“重大”，其余接在后面；下次 AI 编排时会重写
            covered = edits.get("_covered", {}).get(raw["name"], len(entries))
            late = [(n, e) for n, e in enumerate(entries, 1) if n > covered]
            if late:
                extra = fallback_stories([e for _, e in late], item)
                for x in extra:
                    x["refs"] = [late[x["refs"][0] - 1][0]]
                    if x["weight"] == "lead":
                        x["weight"] = "normal"
                stories = [x for x in extra if x["weight"] == "hero"] + stories + \
                          [x for x in extra if x["weight"] != "hero"]
        elif entries:
            stories = (edit_stories(client, model, item, entries) if client else None) or fallback_stories(entries, item)
        else:
            stories = []
        if item.get("max_stories"):  # 篇幅上限：要紧的排在最前，截掉的是后面次要的
            stories = stories[:item["max_stories"]]
        if not stories and not any(f["changed"] for f in raw["facts"]):
            continue
        stories = attach_media(stories, entries, raw.get("cover"), raw["name"], stats, used)  # 原文已删的报道会被去掉
        # 出刊时补到的配图写回 inbox，下次出刊直接用，不必再找（Reddit 限流、网站偶尔打不开时也不会丢图）
        for d, e in zip(raw["entries"], entries):
            if e.image and not d.get("image"):
                d["image"], d["image_via"], inbox_changed = e.image, e.image_via, True
            if e.link and not d.get("link"):
                d["link"], inbox_changed = e.link, True
        if not stories and not any(f["changed"] for f in raw["facts"]):
            continue
        blocks.append({
            "name": raw["name"],
            "section": section_of(item),
            "subtitle": item.get("subtitle", ""),
            "cover": raw.get("cover"),
            "theme": theme.resolve(item, raw.get("cover"), themes),
            "facts": raw["facts"],
            "stories": stories,
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
    issue = {"no": no, "date": date, "items": blocks}
    save_json(REPORTS_DIR / f"{date}.json", issue)
    recommend()
    write_page()
    write_issue_markdown(issue, settings)
    print(f"第 {no} 期：reports/{date}.json → docs/index.html", file=sys.stderr)


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
    PICK_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for raw in inbox["items"]:
        entries = [entry_from_dict(d) for d in raw["entries"]]
        for k, story in enumerate(edits.get(raw["name"], []) or []):
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
                im.thumbnail((360, 240))
                thumbs.append((u, im))
                if len(thumbs) >= 12:
                    break
            key = f"{raw['name']}#{k}"
            out[key] = {"headline": story.get("headline", ""), "current": story.get("image"),
                        "candidates": [u for u, _ in thumbs]}
            if not thumbs:
                continue
            cols = 4
            rows = (len(thumbs) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * 370, rows * 250), "white")
            draw = ImageDraw.Draw(sheet)
            for i, (_, im) in enumerate(thumbs):
                x, y = (i % cols) * 370 + 5, (i // cols) * 250 + 5
                sheet.paste(im, (x, y))
                draw.rectangle([x, y, x + 34, y + 26], fill="black")
                draw.text((x + 8, y + 6), str(i + 1), fill="white")
            name = f"{len(out):02d}.jpg"
            sheet.save(PICK_DIR / name, quality=85)
            out[key]["sheet"] = str(PICK_DIR / name)
            print(f"{key}  {story.get('headline', '')}  → {PICK_DIR / name}（{len(thumbs)} 张）")
    (PICK_DIR / "candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"候选链接：{PICK_DIR / 'candidates.json'}")


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
                       or not images.check(img)[0]  # 图后来被删、或者不合格（太小、打不开）
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
                                  or "验证不了" in (st.get("image_via") or "") or not images.check(img)[0]):
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
    write_page()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", nargs="?", default="all",
                        choices=["all", "ingest", "publish", "render", "notify-urgent", "notify-weekly", "notify-new-items", "notify-changes", "notify-wishlist", "recommend", "pick-images", "unedited", "new-items", "repair-images", "sync-db", "take-wishes"])
    parser.add_argument("date", nargs="?", help="pick-images 用：指定日期，默认最新一期")
    parser.add_argument("--only", help="unedited 用：只看这些关注项（用「、」分隔）")
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印，不写文件")
    args = parser.parse_args()
    if args.dry_run:
        ingest(dry_run=True)
    elif args.step == "repair-images":
        repair_images()
    elif args.step == "pick-images":
        pick_images(args.date)
    elif args.step == "new-items":
        print("、".join(new_item_names()))
    elif args.step == "unedited":
        print("、".join(unedited(args.only.split("、") if args.only is not None else None)))
    elif args.step == "render":
        write_page()
    elif args.step == "ingest":
        ingest()
        sync_db()
    elif args.step == "sync-db":
        sync_db()
    elif args.step == "publish":
        publish()
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
        notify.weekly(pages_url(load_config()[0]))
    elif args.step == "take-wishes":
        take_wish_requests()
    else:
        take_wish_requests()  # 先把新闻里点了「加入心愿单」的加进愿望清单，这次出刊就能看到
        path = ingest()
        if path:
            publish(path)
        sync_db()


if __name__ == "__main__":
    main()
