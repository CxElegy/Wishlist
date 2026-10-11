"""关注清单定期整理。

流程（参考 agents-radar）：
1. 按 items.yaml 从免费 RSS / API 抓取消息（不消耗 LLM token）
2. 按时间窗口、关键词过滤，并去掉以前报道过的
3. 只把新消息的标题和摘要交给 LLM，按你最关心的问题（priority）排序、归纳成几条报道
4. 配图：文章预览图 / Reddit 图 / 作品封面；配色：作品主视觉
5. 输出 reports/YYYY-MM-DD.json（本期数据）和 docs/index.html（简报网页，新一期在最上面）

用法：
    python scripts/digest.py            # 生成本期
    python scripts/digest.py --dry-run  # 只抓取并打印，不调用 LLM、不写文件
    python scripts/digest.py --render   # 只用已有数据重新生成网页（改了版式时用）
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
REPORTS_DIR = ROOT / "reports"
STATE_DIR = ROOT / "state"
SEEN_FILE = STATE_DIR / "seen.json"
FACTS_FILE = STATE_DIR / "facts.json"
THEMES_FILE = STATE_DIR / "themes.json"
DOCS_DIR = ROOT / "docs"
ISSUES_ON_PAGE = 20  # 网页上保留最近几期

SEEN_KEEP_DAYS = 90
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


def filter_entries(entries, item, settings, seen, now):
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
    out = []
    for e in sorted(best.values(), key=lambda e: e.published or now, reverse=True):
        key = title_key(e.title)
        if e.url in seen or key in seen:
            continue
        if e.published and e.published < since:
            continue
        if any(w in e.title.lower() for w in exclude):
            continue
        trusted = e.source in TRUSTED_SOURCES or e.source in {f"r/{s}" for s in item.get("subreddits") or []}
        if not trusted and not any(w in _norm(e.title + e.summary) for w in match):
            continue
        out.append(e)
    return out[: item.get("max_entries") or settings.get("max_entries_per_item", 30)]


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


def fallback_stories(entries):
    """不用 AI 时：直接取最新几条标题。"""
    return [{"headline": e.title, "highlight": "", "blurb": "", "weight": "normal", "refs": [i]}
            for i, e in enumerate(entries[:6], 1)]


def attach_media(stories, entries, cover):
    """给每条报道配链接和图：条目自带图 > 文章预览图 > （仅头条）作品封面。"""
    for n, s in enumerate(stories):
        refs = [entries[r - 1] for r in s.pop("refs")]
        s["url"] = refs[0].url
        s["image"] = next((e.image for e in refs if e.image), None)
        for e in refs:
            if s["image"]:
                break
            s["image"] = sources.og_image(e.url)
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


def write_page():
    issues = [load_json(p) for p in sorted(REPORTS_DIR.glob("????-??-??.json"), reverse=True)[:ISSUES_ON_PAGE]]
    issues = [i for i in issues if i]
    if not issues:
        return
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(render.render(issues), encoding="utf-8")
    (DOCS_DIR / ".nojekyll").touch()


def write_issue_markdown(issue, settings):
    """GitHub Issue 正文：标题列表 + 网页链接，用于邮件提醒。"""
    lines = [f"**[查看本期简报 →]({pages_url(settings)})**", ""]
    for block in issue["items"]:
        lines.append(f"### {block['name']}")
        lines += [f"- **{f['label']}**：{f['text']}" + ("（有变化）" if f["changed"] else "")
                  for f in block["facts"] if f["changed"]]
        lines += [f"- {'**[重大]** ' if s['weight'] == 'hero' else ''}[{s['headline']}]({s['url']})"
                  for s in block["stories"]]
        lines.append("")
    (ROOT / "issue.md").write_text("\n".join(lines), encoding="utf-8")


# ---------- 主流程 ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印，不调用 LLM、不写文件")
    parser.add_argument("--render", action="store_true", help="只用已有数据重新生成网页")
    args = parser.parse_args()
    if args.render:
        write_page()
        return

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

    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    seen, facts, themes = load_json(SEEN_FILE), load_json(FACTS_FILE), load_json(THEMES_FILE)

    client = None
    model = settings.get("model", "claude-haiku-5-5")
    if not args.dry_run and settings.get("summarize", True):
        client = make_client()
        if client is None:
            print("没有可用的 Claude 凭据，直接用原标题", file=sys.stderr)

    blocks = []
    for item in items:
        print(f"抓取：{item['name']}", file=sys.stderr)
        entries = filter_entries(collect(item, settings), item, settings, seen, now)
        print(f"  新条目 {len(entries)} 条", file=sys.stderr)
        if args.dry_run:
            print(f"===== {item['name']} =====\n{format_entries(entries)}\n")
            continue

        item_facts, status_cover = status_facts(item, settings, facts)
        stories = []
        if entries:
            stories = (edit_stories(client, model, item, entries) if client else None) or fallback_stories(entries)
        # 没有新报道、状态也没变化的关注项，本期不出现
        if not stories and not any(f["changed"] for f in item_facts):
            continue
        cover = find_cover(item, status_cover)
        blocks.append({
            "name": item["name"],
            "subtitle": item.get("subtitle", ""),
            "theme": theme.resolve(item, cover, themes),
            "facts": item_facts,
            "stories": attach_media(stories, entries, cover),
        })
        for e in entries:
            seen[e.url] = seen[title_key(e.title)] = today

    if args.dry_run:
        return

    cutoff = (now - dt.timedelta(days=SEEN_KEEP_DAYS)).date().isoformat()
    save_json(SEEN_FILE, {u: d for u, d in seen.items() if d >= cutoff})
    save_json(FACTS_FILE, facts)
    save_json(THEMES_FILE, themes)

    if not blocks:
        print("本期没有新消息，不出刊", file=sys.stderr)
        return
    existing = sorted(p.stem for p in REPORTS_DIR.glob("????-??-??.json"))
    no = existing.index(today) + 1 if today in existing else len(existing) + 1
    issue = {"no": no, "date": today, "items": blocks}
    save_json(REPORTS_DIR / f"{today}.json", issue)
    write_page()
    write_issue_markdown(issue, settings)
    print(f"第 {no} 期：reports/{today}.json → docs/index.html")


if __name__ == "__main__":
    main()
