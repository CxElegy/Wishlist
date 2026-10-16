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
import urllib.parse
import urllib.error
import urllib.request
import unicodedata
import zoneinfo

import yaml

import heat
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
HEAT_FILE = STATE_DIR / "heat_signals.json"  # 話題度用的外部数据（维基浏览量、Steam 在线、AniList / TMDB 人气），见 heat.py
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
- headline：原文标题，不翻译：用依据条目里最权威那条的标题，去掉媒体名和宣传噪音，太长就在原来的语言里删减。
- highlight：headline 里最关键的几个字（日期、数字、结论），必须原样出现在 headline 中；没有就留空。
- blurb：一句话补充，用原文的语言（照摘要精简），只给头条和 hero 写，其余留空。
- refs：这条报道依据的条目编号。
- Reddit 帖子是玩家讨论（摘要里有赞数、评论数），热度高时可以归纳成一条“社区热议”报道。
- 来源优先用国外媒体（含港台、日韩、欧美）：同一件事国外媒体也报了，refs 第一个放国外媒体；
  标了（大陆网站）的条目只在这件事只有大陆网站报道时才用。
- 不翻译：标题和摘要都保持原文的语言。"""

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


def match_hit(item, e):
    """这条消息靠哪个匹配词算进这个关注项（返回那个词）；不算就返回 None。
    新闻搜索会混入不相关结果：标题或摘要里必须出现某个匹配词（忽略大小写和空格）。
    「re:」开头的是正则，区分大小写、照原文匹配：名字是常用词（FROM、MCU）或泛词要和主题词同时出现时用它。
    写法规则见 CLAUDE.md「匹配词（match）的写法」；python scripts/digest.py audit-match 可以检查。"""
    if e.source in TRUSTED_SOURCES or e.source in {f"r/{s}" for s in item.get("subreddits") or []}:
        return "(可信来源)"
    # Reddit 全站搜索来的帖子：正文是闲聊，「from Season 5」这种说法到处都是，匹配词必须出现在标题里
    text = e.title if e.source == "Reddit" else e.title + e.summary
    for w in item.get("match") or item.get("keywords") or [item["name"]]:
        if w.startswith("re:") and re.search(w[3:], text) or not w.startswith("re:") and _norm(w) in _norm(text):
            return w
    return None


def audit_match(days=4, only=None):
    """检查误收：最近几天 inbox 里每个关注项的条目按「靠哪个匹配词进来的」分组列出来，
    并标出按现在的 match / exclude 已经不会再收的（✗）。加关注项、改匹配词之后跑一次，看有没有不相关的混进来。"""
    _, items = load_config()
    paths = sorted(p for p in INBOX_DIR.glob("????-??-??.json"))[-days:]
    for item in items:
        if only and item["name"] not in only:
            continue
        exclude = [w.lower() for w in item.get("exclude") or []]
        groups = {}
        for path in paths:
            for raw in load_json(path).get("items", []):
                if raw["name"] != item["name"]:
                    continue
                for d in raw["entries"]:
                    e = entry_from_dict(d)
                    hit = match_hit(item, e)
                    gone = hit is None or any(w in e.title.lower() for w in exclude)
                    groups.setdefault(hit or "(不再匹配)", []).append(("✗ " if gone else "  ") + e.title[:90])
        print(f"===== {item['name']}（{sum(len(v) for v in groups.values())} 条）")
        for w, titles in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(f"  [{w}] {len(titles)}")
            for t in titles[:8]:
                print(f"     {t}")


def filter_entries(entries, item, settings, seen, now, known=()):
    names = [item["name"], *(item.get("keywords") or []), *(item.get("match") or [])]
    since = now - dt.timedelta(days=settings.get("lookback_days", 7))
    exclude = [w.lower() for w in item.get("exclude") or []]
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
        if match_hit(item, e) is None:
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
            if e.source == "YouTube" or any(re.search(p, e.title) for p in JUNK_PATTERNS):
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
    "type": "type", "section": "str:20", "size": "size", "subtitle": "str:80",
    "keywords": "list:12:100", "match": "list:30:100", "exclude": "list:30:100", "news_langs": "langs",
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
            if len(out) > most or any(len(v) > longest for v in out):
                raise ValueError(f"{key} 太多或太长")
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
        while stop - 1 > at and not block[stop - 1].strip():
            stop -= 1
        block[at:stop] = new
    return "\n".join(lines[:start] + block + lines[end:])


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
    done, skipped = [], {}
    for r in rows:
        name = (r.get("name") or "").strip()
        names = {i["name"] for i in items}
        try:
            fields = clean_item_config(r.get("config") or {})
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
        print(f"关注项：从设置页{'修改' if r.get('action') == 'edit' else '加入'}「{r['name']}」", file=sys.stderr)


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
    images = old.get("images", {})
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
        elif work and day in recent and not sources.is_reddit(entry_from_dict(d)):  # 网友的帖子（提问、闲聊）不当推荐
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
    save_json(RECOMMEND_FILE, {"picks": picks, "images": {u: i for u, i in images.items() if u in keep},
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
    版面の見た目は最新の一期で決まるので、最新の一期の版面だけを上書きする。reports/ には書き戻さない。"""
    manual = {i["name"]: i["theme"] for i in items if isinstance(i.get("theme"), dict)}
    if not manual or not issues:
        return issues
    blocks = [{**b, "theme": {**(b.get("theme") or {}), **manual[b["name"]]}} if b.get("name") in manual else b
              for b in issues[0].get("items", [])]
    return [{**issues[0], "items": blocks}] + issues[1:]


def write_page():
    issues = [load_json(p) for p in sorted(REPORTS_DIR.glob("????-??-??.json"), reverse=True)[:ISSUES_ON_PAGE]]
    issues = [i for i in issues if i]
    if not issues:
        return
    DOCS_DIR.mkdir(exist_ok=True)
    settings, items = load_config()
    tz = zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))
    updated = dt.datetime.now(tz).strftime("%m.%d %H:%M")
    issues = with_manual_themes(with_new_items(issues, items), items)
    themes = load_json(THEMES_FILE) or {}
    analysis = heat.analyze(items, sorted(INBOX_DIR.glob("????-??-??.json")), issues, load_json(HEAT_FILE) or {},
                            issues[0]["date"])
    heat_scores = analysis["items"]
    html_ = render.render(issues, settings.get("nav_style", "line"), [i["name"] for i in items], updated,
                          load_wishlist(), (load_json(RECOMMEND_FILE) or {}).get("picks", []),
                          {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}, load_sizes(),
                          {i["name"]: render.template_for(i) for i in items}, themes,
                          (load_json(RECOMMEND_FILE) or {}).get("taste", []), heat_scores,
                          {i["name"]: (i["emblem"], i.get("emblem_ring", "accent")) for i in items if isinstance(i.get("emblem"), list)})
    save_json(THEMES_FILE, themes)  # トップのポスターの取色を書き足した分
    (DOCS_DIR / "index.html").write_text(html_, encoding="utf-8")
    (DOCS_DIR / "heat.html").write_text(render.render_heat(analysis, render.collect(issues, [i["name"] for i in items]), updated),
                                        encoding="utf-8")
    (DOCS_DIR / "themes.html").write_text(render.render_themes(  # テーマ見本（30 のテーマと 👍 の演出）
        [{"name": i["name"], "motif": render.template_for(i), "theme": i.get("theme")} for i in items], updated), encoding="utf-8")
    wishes = load_wishlist()
    if wishes:
        works = render.collect(issues, [i["name"] for i in items])
        finds = [x for x in (load_json(DISCOVER_FILE) or {}).get("entries", []) if x.get("wish")]
        (DOCS_DIR / "wishlist.html").write_text(render.render_wishlist(wishes, works, updated, finds,
                                                                      {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}), encoding="utf-8")
    (DOCS_DIR / "settings.html").write_text(render.render_settings(
        [{"name": i["name"], "section": section_of(i), "subtitle": i.get("subtitle", ""),
          "size": load_sizes().get(i["name"], "M"),
          "fields": {**{k: i[k] for k in ITEM_FIELDS if k in i and k != "size"}, "section": section_of(i)}} for i in items],
        {"url": settings.get("supabase_url"), "key": settings.get("supabase_key"), "langs": settings.get("news_langs") or []},
        updated), encoding="utf-8")
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


def update_heat():
    """話題度用的外部数据：维基浏览量（一天一次）、Steam 在线、AniList / TMDB 人气。取不到的下次再取。"""
    settings, items = load_config()
    today = dt.datetime.now(zoneinfo.ZoneInfo(settings.get("timezone", "Asia/Shanghai"))).date().isoformat()
    print("話題度：取外部数据", file=sys.stderr)
    save_json(HEAT_FILE, heat.fetch_signals(items, load_json(HEAT_FILE) or {}, today))


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
                        choices=["all", "ingest", "publish", "render", "notify-urgent", "notify-weekly", "notify-new-items", "notify-changes", "notify-wishlist", "recommend", "pick-images", "unedited", "new-items", "repair-images", "sync-db", "photos", "take-items", "heat", "audit-match"])
    parser.add_argument("date", nargs="?", help="pick-images 用：指定日期，默认最新一期")
    parser.add_argument("--only", help="unedited / audit-match 用：只看这些关注项（用「、」分隔）")
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
        update_heat()
        sync_db()
    elif args.step == "audit-match":
        audit_match(only=args.only.split("、") if args.only else None)
    elif args.step == "heat":
        update_heat()
        write_page()
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
    elif args.step == "photos":
        export_photos()
    elif args.step == "take-items":
        take_item_requests()
    else:
        take_item_requests()  # 设置页上新增的关注项先写进 items.yaml，这次就开始收集
        export_photos()  # 拍照加愿望：导出新照片给 Claude 定时任务处理
        path = ingest()
        update_heat()
        if path:
            publish(path)
        sync_db()


if __name__ == "__main__":
    main()
