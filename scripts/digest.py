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
import json
import os
import pathlib
import re
import sys
import urllib.request
import zoneinfo

import yaml

import render
import sources
import theme

ROOT = pathlib.Path(__file__).resolve().parent.parent
ITEMS_FILE = ROOT / "items.yaml"
WISHLIST_FILE = ROOT / "wishlist.yaml"
REPORTS_DIR = ROOT / "reports"
STATE_DIR = ROOT / "state"
FACTS_FILE = STATE_DIR / "facts.json"
THEMES_FILE = STATE_DIR / "themes.json"
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
    langs = item.get("news_langs") or settings.get("news_langs") or ["zh-CN"]
    keywords = item.get("keywords") or [item["name"]]
    use = item.get("use") or ["google", "bing", "reddit"]

    entries = []
    for kw in keywords:
        if "google" in use:
            for lang in langs:
                entries += sources.google_news(kw, lookback, NEWS_LANGS[lang])
        if "bing" in use:
            entries += sources.bing_news(kw)
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
    # 同一篇文章常同时出现在 Google 和 Bing：每个标题只留一条，优先能直接打开原文的
    # （Google 是跳转页，拿不到配图）
    best = {}
    for e in entries:
        key = title_key(e.title)
        if key not in best or ("news.google.com" in best[key].url and "news.google.com" not in e.url):
            best[key] = e
    out, grams = [], [_title_grams(t, names) for t in known]
    skip_sources = set(settings.get("exclude_sources", ["YouTube"]))
    for e in sorted(best.values(), key=lambda e: e.published or now, reverse=True):
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
        if not trusted and not any(w in _norm(e.title + e.summary) for w in match):
            continue
        grams.append(g)
        out.append(e)
    # Reddit 帖子多且杂（同人图、闲聊），单独限额，不和媒体报道抢名额
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
        facts[key] = {"text": text, "stable": stable}
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
        return sources.og_image(item["site"])
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
        line = f"[{i}] {date} | {e.source} | {e.title}"
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


HEAT_MIN_OUTLETS = 4  # 设了 hot_only 时，头条以外的报道至少要有几家媒体在报


def fallback_stories(entries, item, limit=7):
    """不用 AI 时的编排：
    - 标题含 priority_keywords（你最关心的事）的排前面，第一条做头条
    - 设了 hot_only 的关注项只要“最火的事”：改按有多少家媒体在报同一件事排序，同一件事合成一条；
      头条以外只留至少 HEAT_MIN_OUTLETS 家在报的，没那么多事就少写
    - 同一新闻被多家转载时只留一条（标题字符重合度高的视为同一条）
    - 媒体报道优先于 Reddit；Reddit 帖子没命中关键词的不收（多半是同人图、闲聊）
    - 本作只是被顺带提到的（打头的是别的作品）不收
    - 同等条件下有图的、较新的优先"""
    words = [w.lower() for w in item.get("priority_keywords") or []]
    urgent = {i for i, e in enumerate(entries, 1) if is_urgent(e, item)}
    by_heat = bool(item.get("hot_only"))
    names = sorted({item["name"], *(item.get("keywords") or []), *(item.get("match") or [])}, key=len, reverse=True)
    topics = {i: _topic_tokens(e.title, names) for i, e in enumerate(entries, 1)} if by_heat else {}
    media = [i for i, e in enumerate(entries, 1) if not e.source.startswith("r/")]

    def hits(e):
        return sum(w in e.title.lower() for w in words)

    def heat(i):
        return sum(1 for j in media if j != i and _same_topic(topics[i], topics[j]))

    def score(pair):
        i, e = pair
        if by_heat:
            return (i in urgent, heat(i), not e.source.startswith("r/"), hits(e),
                    bool(e.image) or "news.google.com" not in e.url, -i)
        return (i in urgent, hits(e) > 0, not e.source.startswith("r/"), hits(e),
                bool(e.image) or "news.google.com" not in e.url, -i)

    candidates = [(i, e) for i, e in enumerate(entries, 1)
                  if (hits(e) or not e.source.startswith("r/")) and not side_mention(e.title, item)]
    picked, grams = [], []
    for i, e in sorted(candidates, key=score, reverse=True):
        g = _bigrams(e.title)
        if any(len(g & h) / max(1, min(len(g), len(h))) > 0.5 for h in grams):
            continue
        if by_heat and any(i in p["refs"] or any(_same_topic(topics[i], topics[r]) for r in p["refs"]) for p in picked):
            continue  # 已经归进前面某条报道的同一件事
        grams.append(g)
        weight = "hero" if i in urgent else ("lead" if not picked or all(p["weight"] == "hero" for p in picked) else "normal")
        refs = [i] + ([j for j in media if j != i and _same_topic(topics[i], topics[j])] if by_heat else [])
        if by_heat and picked and i not in urgent and len(refs) < HEAT_MIN_OUTLETS:
            continue  # 只有一两家在报的不算“火”，事情少就少写
        picked.append({"headline": e.title, "highlight": "", "blurb": "", "weight": weight, "refs": refs})
        if len(picked) == limit:
            break
    return picked


def find_image(chosen, refs, url):
    """一条报道的配图：AI 挑的 > 条目自带图 > 原文预览图 > 原文正文里的大图。每张都实际下载试一下，
    打不开（防盗链、付费墙）就换下一张；都没有返回 None（网页上会用作品封面代替）。"""
    seen = set()

    def candidates():
        yield chosen
        for e in refs:
            yield e.image
        for page in [url] + [sources.resolve_url(e.url) for e in refs[1:3]]:
            yield sources.og_image(page)
            yield from sources.article_images(page, limit=6)

    for img in candidates():
        if img and img not in seen:
            seen.add(img)
            if sources.image_ok(img):
                return img
        if len(seen) >= 10:
            break
    return None


def attach_media(stories, entries, cover):
    """给每条报道配链接和图：条目自带图 > 原文预览图 > （仅头条）作品封面。
    Google 新闻的跳转链接先还原成原文地址，链接和配图都用原文的。"""
    for n, s in enumerate(stories):
        refs = [entries[r - 1] for r in s.pop("refs")]
        s["url"] = s.get("url") or sources.resolve_url(refs[0].url)
        if refs[0].published:  # 消息本身的日期，卡片上显示、按它排序
            s["date"] = refs[0].published.date().isoformat()
        s["image"] = find_image(s.get("image"), refs, s["url"])
        if not s["image"] and n == 0:
            s["image"] = cover
    return stories


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
                          load_wishlist())
    (DOCS_DIR / "index.html").write_text(html_, encoding="utf-8")
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
    return {"n": n, "date": e.published.isoformat() if e.published else None, "source": e.source,
            "title": e.title, "summary": e.summary, "url": e.url, "image": e.image}


def entry_from_dict(d):
    return sources.Entry(title=d["title"], url=d["url"], source=d["source"], summary=d.get("summary", ""),
                         image=d.get("image", ""),
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
        entries = filter_entries(collect(item, conf), item, conf, seen, now, known.get(item["name"], []))
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

    client = None
    if settings.get("summarize", False) and any(i["name"] not in edits for i in inbox["items"]):
        client = make_client()
        if client is None:
            print("没有可用的 Claude 凭据，改用关键词规则编排", file=sys.stderr)
    model = settings.get("model", "claude-haiku-5-5")

    blocks = []
    for raw in inbox["items"]:
        item = by_name.get(raw["name"], {"name": raw["name"], "type": "product"})
        if raw.get("backfill"):  # 补抓的旧闻不做“重大”
            item = {**item, "urgent_patterns": []}
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
        blocks.append({
            "name": raw["name"],
            "section": section_of(item),
            "subtitle": item.get("subtitle", ""),
            "cover": raw.get("cover"),
            "theme": theme.resolve(item, raw.get("cover"), themes),
            "facts": raw["facts"],
            "stories": attach_media(stories, entries, raw.get("cover")),
        })
    # 没有新消息的关注项也留一个小栏，排在有消息的后面
    shown = {b["name"] for b in blocks}
    blocks += [quiet_block(i, themes, date) for i in items if i["name"] not in shown]
    save_json(THEMES_FILE, themes)

    if not blocks:
        print("本期没有可出刊的内容", file=sys.stderr)
        return
    existing = sorted(p.stem for p in REPORTS_DIR.glob("????-??-??.json"))
    no = existing.index(date) + 1 if date in existing else len(existing) + 1
    issue = {"no": no, "date": date, "items": blocks}
    save_json(REPORTS_DIR / f"{date}.json", issue)
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
                for u in sources.article_images(sources.resolve_url(e.url)):
                    if u not in urls:
                        urls.append(u)
            thumbs = []
            for u in urls:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", nargs="?", default="all",
                        choices=["all", "ingest", "publish", "render", "notify-urgent", "notify-weekly", "notify-new-items", "notify-changes", "notify-wishlist", "pick-images", "unedited", "new-items"])
    parser.add_argument("date", nargs="?", help="pick-images 用：指定日期，默认最新一期")
    parser.add_argument("--only", help="unedited 用：只看这些关注项（用「、」分隔）")
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印，不写文件")
    args = parser.parse_args()
    if args.dry_run:
        ingest(dry_run=True)
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
    elif args.step == "publish":
        publish()
    elif args.step == "notify-urgent":
        import notify
        notify.urgent(pages_url(load_config()[0]))
    elif args.step == "notify-wishlist":
        import notify
        notify.wishlist(pages_url(load_config()[0]))
    elif args.step == "notify-changes":
        import notify
        notify.changes(pages_url(load_config()[0]))
    elif args.step == "notify-new-items":
        import notify
        notify.new_items(pages_url(load_config()[0]))
    elif args.step == "notify-weekly":
        import notify
        notify.weekly(pages_url(load_config()[0]))
    else:
        path = ingest()
        if path:
            publish(path)


if __name__ == "__main__":
    main()
