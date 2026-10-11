"""关注清单定期整理。

流程（参考 agents-radar）：
1. 按 items.yaml 从免费 RSS / API 抓取消息（不消耗 LLM token）
2. 按时间窗口过滤，并去掉以前报告里出现过的链接
3. 只把新消息的标题和摘要交给 LLM 归纳成短评（可关闭）
4. 输出 reports/YYYY-MM-DD.md 和 reports/LATEST.md

用法：
    python scripts/digest.py            # 生成报告
    python scripts/digest.py --dry-run  # 只抓取并打印，不调用 LLM、不写文件
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys

import yaml

import sources

ROOT = pathlib.Path(__file__).resolve().parent.parent
ITEMS_FILE = ROOT / "items.yaml"
REPORTS_DIR = ROOT / "reports"
STATE_DIR = ROOT / "state"
SEEN_FILE = STATE_DIR / "seen.json"
PRICES_FILE = STATE_DIR / "prices.json"

SEEN_KEEP_DAYS = 90
NEWS_LANGS = {
    "zh-CN": ("zh-CN", "CN", "CN:zh-Hans"),
    "zh-TW": ("zh-TW", "TW", "TW:zh-Hant"),
    "en-US": ("en-US", "US", "US:en"),
    "ja-JP": ("ja", "JP", "JP:ja"),
}

# 不同类型关注项交给 LLM 的整理要求
ITEM_TYPES = {
    "product": "这是一个具体商品。重点：价格与促销、库存、评测、新版本/固件。",
    "category": "这是一整类产品，不要只盯一个型号。盘点新品、热门型号和明显降价，按重要性排序。",
    "game": "这是一款游戏。重点：版本更新/补丁、活动（写明起止时间）、DLC/发售日、折扣、官方公告。",
}

SYSTEM_PROMPT = """你负责把抓取到的新闻条目整理成简报。只依据提供的条目，不要编造或补充条目之外的信息。

规则：
- 合并重复报道，忽略和关注项无关的条目、广告和纯水贴。
- 每条要点末尾用方括号标注引用的条目编号，例如 [3] 或 [3][7]，不要写 URL。
- 传闻要标注“传闻”；价格写明渠道和币种。
- 条目全部无关时，只输出：本期无重要更新

输出格式（不要输出标题或其它多余内容）：
**一句话总结**：……
- 要点 [n]
- 要点 [n]"""


# ---------- 状态 ----------

def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(path, data):
    STATE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# ---------- 抓取 ----------

def collect(item, settings):
    lookback = settings.get("lookback_days", 7)
    langs = settings.get("news_langs") or ["zh-CN"]
    keywords = item.get("keywords") or [item["name"]]
    use = item.get("use") or ["google", "bing"]

    entries = []
    for kw in keywords:
        if "google" in use:
            for lang in langs:
                entries += sources.google_news(kw, lookback, NEWS_LANGS[lang])
        if "bing" in use:
            entries += sources.bing_news(kw)
        for sub in item.get("subreddits") or []:
            entries += sources.reddit(sub, kw)
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
    out, titles = [], set()
    for e in sorted(entries, key=lambda e: e.published or now, reverse=True):
        key = title_key(e.title)
        if e.url in seen or key in seen or key in titles:
            continue
        if e.published and e.published < since:
            continue
        if any(w in e.title.lower() for w in exclude):
            continue
        if e.source not in TRUSTED_SOURCES and not any(w in _norm(e.title + e.summary) for w in match):
            continue
        titles.add(key)
        out.append(e)
    return out[: settings.get("max_entries_per_item", 30)]


def price_line(item, settings, prices):
    appid = item.get("steam_appid")
    if not appid:
        return None
    price = sources.steam_price(appid, settings.get("steam_country", "cn"))
    if not price:
        return None
    old = prices.get(str(appid))
    prices[str(appid)] = price
    change = f"（上期 {old}）" if old and old != price else ""
    return f"**Steam 当前价格**：{price}{change}"


# ---------- LLM 归纳 ----------

def format_entries(entries):
    lines = []
    for i, e in enumerate(entries, 1):
        date = e.published.strftime("%m-%d") if e.published else "日期未知"
        line = f"[{i}] {date} | {e.source} | {e.title}"
        if e.summary:
            line += f" | {e.summary}"
        lines.append(line)
    return "\n".join(lines)


def summarize(client, model, item, entries):
    import anthropic

    prompt = (
        f"关注项：{item['name']}\n"
        f"整理要求：{ITEM_TYPES[item.get('type', 'product')]}\n"
        + (f"补充说明：{item['notes']}\n" if item.get("notes") else "")
        + f"\n条目：\n{format_entries(entries)}"
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4000,
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        print(f"  [警告] LLM 调用失败：{e}", file=sys.stderr)
        return None
    if response.stop_reason == "refusal":
        return None
    text = "\n".join(b.text for b in response.content if b.type == "text").strip()
    # 把 [n] 换成链接；让模型只写编号，可以省下大量输出 token
    return re.sub(
        r"\[(\d+)\]",
        lambda m: f"[[{m[1]}]]({entries[int(m[1]) - 1].url})" if 0 < int(m[1]) <= len(entries) else m[0],
        text,
    )


def plain_list(entries):
    return "\n".join(
        f"- {e.published.strftime('%m-%d') if e.published else ''} [{e.title}]({e.url}) — {e.source}"
        for e in entries
    )


# ---------- 主流程 ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印，不调用 LLM、不写文件")
    args = parser.parse_args()

    config = yaml.safe_load(ITEMS_FILE.read_text(encoding="utf-8")) or {}
    settings = config.get("settings") or {}
    items = config.get("items") or []
    for item in items:
        if item.get("type", "product") not in ITEM_TYPES:
            sys.exit(f"{item['name']} 的 type 必须是 {'/'.join(ITEM_TYPES)} 之一")
    for lang in settings.get("news_langs") or []:
        if lang not in NEWS_LANGS:
            sys.exit(f"news_langs 只支持 {'/'.join(NEWS_LANGS)}，不支持 {lang!r}")

    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    seen = load_json(SEEN_FILE)
    prices = load_json(PRICES_FILE)

    client = None
    model = settings.get("model", "claude-haiku-5-5")
    if not args.dry_run and settings.get("summarize", True) and os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        client = anthropic.Anthropic()
    elif not args.dry_run:
        print("未设置 ANTHROPIC_API_KEY 或已关闭 summarize，只输出链接列表", file=sys.stderr)

    sections, total = [], 0
    for item in items:
        print(f"抓取：{item['name']}", file=sys.stderr)
        entries = filter_entries(collect(item, settings), item, settings, seen, now)
        total += len(entries)
        print(f"  新条目 {len(entries)} 条", file=sys.stderr)
        if args.dry_run:
            print(f"===== {item['name']} =====\n{format_entries(entries)}\n")
            continue

        parts = [f"## {item['name']}"]
        price = price_line(item, settings, prices)
        if price:
            parts.append(price)
        if not entries:
            parts.append("本期无新消息。")
        else:
            body = summarize(client, model, item, entries) if client else None
            parts.append(body or plain_list(entries))
            if body:
                parts.append(f"<details><summary>全部 {len(entries)} 条原始链接</summary>\n\n{plain_list(entries)}\n\n</details>")
        sections.append("\n\n".join(parts))
        for e in entries:
            seen[e.url] = seen[title_key(e.title)] = today

    if args.dry_run:
        return

    cutoff = (now - dt.timedelta(days=SEEN_KEEP_DAYS)).date().isoformat()
    save_json(SEEN_FILE, {u: d for u, d in seen.items() if d >= cutoff})
    save_json(PRICES_FILE, prices)

    REPORTS_DIR.mkdir(exist_ok=True)
    report = (
        f"# 关注清单简报 · {today}\n\n"
        f"> 覆盖最近 {settings.get('lookback_days', 7)} 天 · {len(items)} 个关注项 · {total} 条新消息\n\n"
        + "\n\n".join(sections)
        + "\n"
    )
    (REPORTS_DIR / f"{today}.md").write_text(report, encoding="utf-8")
    (REPORTS_DIR / "LATEST.md").write_text(report, encoding="utf-8")
    print(f"reports/{today}.md")


if __name__ == "__main__":
    main()
