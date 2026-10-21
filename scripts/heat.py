"""話題度（热度指数）：每个关注项 0〜100 分，由 6 个维度合成。

维度（权重）                      用什么算
  ① 報道量       volume   20    最近 7 天收集到的媒体条目数（越新越重）
  ② 広がり       breadth  15    最近 7 天有几家媒体、跨了几个语言地区（日 / 中 / 韩 / 英）
  ③ 出来事       event    20    要紧消息（urgent_patterns）、AniList / TMDB 状态变化、14 天内的预定、头条
  ④ 勢い         momentum 15    最近 2 天的速度 ÷ 之前 5 天的速度（报道和维基浏览量）
  ⑤ 一般の関心   public   20    维基百科浏览量（items.yaml 的 wiki）
  ⑥ ファンの反応 fandom   10    AniList trending、TMDB popularity、Steam 同时在线、Reddit 帖子数

每个维度（③ ④ 以外）= 60% 「跟自己平常比」+ 40% 「跟别的关注项用同一把尺子比」：
  - 跟自己比 rel：本周 ÷ 过去 4 周的周平均。平常 = 50 分，4 倍 = 100 分，四分之一 = 0 分；本周什么都没有 = 0 分。
    过去没有数据（刚开始收集）时，有动静就当平常（50 分）
  - 同一把尺子 abs：对数刻度，到 REF（「很热」的量）就是满分。不随关注项的增减变化，每天可以直接比
③ 是绝对分（事件本身的分量），④ 只看自己（升温还是降温）。
拿不到的维度（没有维基词条、没有 AniList 等）不算 0 分：从分母里去掉，权重按比例分给其他维度，
网页上写明用了哪几个维度。我的 👍 / 👎 不算进来：话题度只反映外界的热度。

收集（fetch_signals，每 2 小时随收集任务跑）把维基 / Steam / AniList / TMDB 的数存进 state/heat_signals.json；
计算（compute）不联网，只读收集箱、各期简报和这个文件，生成网页时算。
"""

import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

USER_AGENT = "WatchlistDigest/1.0 (https://github.com/CxElegy/Wishlist; heat index)"
TIMEOUT = 20

DIMS = (  # (键, 网页上的名字, 权重)
    ("volume", "報道量", 20),
    ("breadth", "広がり", 15),
    ("event", "出来事", 20),
    ("momentum", "勢い", 15),
    ("public", "一般の関心", 20),
    ("fandom", "ファンの反応", 10),
)
REL_SHARE = 0.6  # 跟自己比的占比；其余跟别的关注项比
LEVELS = ((85, "沸騰"), (60, "盛り上がり"), (30, "話題"), (1, "静か"))
WEEK = 7
BASE_WEEKS = 4     # 「平常」= 过去几周的周平均
EVENT_SOON = 14    # 几天内的预定算进「出来事」
RISING = 75        # 勢い到这个分数以上（且总分 ≥ 30）标「急上昇」
KEEP_DAYS = 70     # heat_signals.json 里留几天

# 同一把尺子：到这个量就是满分（对数刻度）。按现在的关注项里「很热」的水平定
REF = {
    "volume": 400,      # 一周的媒体条目
    "breadth": 300,     # 媒体数 × 地区系数
    "wiki": 20000,      # 维基一天的浏览量
    "reddit": 150,      # 一周的 Reddit 帖子
    "steam": 100000,    # 同时在线
    "anilist": 150,     # AniList trending（最近几天的活跃度）
    "tmdb": 300,        # TMDB popularity
}


# ---------- 小工具 ----------

def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def rel_score(cur, base):
    """跟自己平常比：平常 50 分，2 倍 75，4 倍 100，一半 25。base 为 None = 没有过去的数据。"""
    if cur <= 0:
        return 0.0
    if base is None:
        return 50.0
    return _clamp(50 + 25 * math.log2((cur + 1) / (base + 1)))


def abs_score(x, ref):
    """同一把尺子：对数刻度，x = ref 时满分。"""
    if x <= 0:
        return 0.0
    return _clamp(100 * math.log10(1 + x) / math.log10(1 + ref))


def mix(cur, base, ref):
    return REL_SHARE * rel_score(cur, base) + (1 - REL_SHARE) * abs_score(cur, ref)


def ratio_text(cur, base):
    if base is None or cur <= 0:
        return ""
    r = (cur + 1) / (base + 1)
    return f"平常の {r:.1f} 倍" if r >= 1.15 or r <= 0.87 else "平常並み"


def _with_ratio(text, cur, base):
    """「7 日で 42 件（平常の 2.1 倍）」。还没有平常可比时写明在攒数据。"""
    if cur <= 0:
        return text
    r = ratio_text(cur, base) if base is not None else "平常のデータを集め中"
    return f"{text}（{r}）"


def _day(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def region(text):
    """标题的语言地区：假名 → 日，谚文 → 韩，汉字 → 中，其他 → 英。"""
    if re.search(r"[぀-ヿ]", text or ""):
        return "ja"
    if re.search(r"[가-힯]", text or ""):
        return "ko"
    if re.search(r"[一-鿿]", text or ""):
        return "zh"
    return "en"


def is_reddit(e):
    """ファンの投稿（Reddit・Bluesky・Mastodon）。報道ではなく「ファンの反応」に数える（2026-10-22 に Bluesky・Mastodon を足した）。"""
    src = e.get("source") or ""
    return src.startswith("r/") or src in ("Reddit", "Bluesky", "Mastodon") or "reddit.com/r/" in (e.get("url") or "")


def _num(n):
    return f"{n / 10000:.1f} 万" if n >= 10000 else f"{n:,.0f}"


# ---------- 收集（联网，随收集任务跑） ----------

def _get_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                                                           **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def wiki_views(titles, days=60, log=sys.stderr):
    """维基百科每天的浏览量（真人），一种语言一次请求（MediaWiki action API 的 pageviews，自动跟随重定向）。
    titles 形如 ["en:Chainsaw Man", "ja:チェンソーマン"] → ({"en:Chainsaw Man": {"2026-10-15": 1799, ...}, ...}, 没取到的语言)。
    找不到的词条打一行日志（items.yaml 的 wiki 写错了），不放进结果。"""
    import wikihttp  # 収集のときだけ使う（ページ生成は通信しない）
    by_lang = {}
    for t in titles:
        lang, _, title = str(t).partition(":")
        if title.strip() and re.fullmatch(r"[a-z\-]{2,12}", lang):
            by_lang.setdefault(lang, []).append(title.strip())
    out, failed = {}, set()
    for lang, names in by_lang.items():
        for i in range(0, len(names), 50):  # API 一次最多 50 个
            chunk = names[i:i + 50]
            q = urllib.parse.urlencode({"action": "query", "prop": "pageviews", "pvipdays": days, "redirects": 1,
                                        "format": "json", "formatversion": 2, "titles": "|".join(chunk)})
            try:
                # wikihttp：名乗った UA・Retry-After・WIKIMEDIA_TOKEN（共有 IP の 429 を避ける）。閲覧数は毎日変わるのでキャッシュは 12 時間
                d = json.loads(wikihttp.get(f"https://{lang}.wikipedia.org/w/api.php?{q}", 2_000_000,
                                            ttl=dt.timedelta(hours=12))).get("query") or {}
            except Exception as err:  # 一种语言取不到（限流等）不影响别的语言，下次再取
                print(f"  [話題度] 维基 {lang}：{err}", file=log)
                failed.add(lang)
                continue
            final = {t: t for t in chunk}  # 请求的名字 → 最终的词条名（大小写规范化、重定向）
            for step in ("normalized", "redirects"):
                hop = {x["from"]: x["to"] for x in d.get(step) or []}
                final = {t: hop.get(f, f) for t, f in final.items()}
            pages = {p["title"]: p for p in d.get("pages") or []}
            for t, f in final.items():
                page = pages.get(f) or {}
                if page.get("missing") or "pageviews" not in page:
                    print(f"  [話題度] 维基没有词条 {lang}:{t}（检查 items.yaml 的 wiki）", file=log)
                    continue
                out[f"{lang}:{t}"] = {k: v for k, v in page["pageviews"].items() if isinstance(v, int)}
            time.sleep(1)  # Wikimedia 要求慢一点
    return out, failed


def steam_players(appid):
    return _get_json(f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={int(appid)}"
                     )["response"].get("player_count")


ANILIST_HEAT = "query($id:Int,$search:String,$type:MediaType){Media(id:$id,search:$search,type:$type){trending popularity favourites}}"


def anilist_heat(anilist_id, search, media_type="ANIME"):
    variables = {k: v for k, v in {"id": anilist_id, "search": None if anilist_id else search, "type": media_type}.items() if v}
    d = _get_json("https://graphql.anilist.co", json.dumps({"query": ANILIST_HEAT, "variables": variables}).encode(),
                  {"Content-Type": "application/json"})
    return d["data"]["Media"]


def tmdb_popularity(ref, key):
    kind, _, tid = ref.partition("/")
    url, headers = f"https://api.themoviedb.org/3/{kind}/{tid}", {}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    else:
        url += f"?api_key={key}"
    return _get_json(url, headers=headers).get("popularity")


def fetch_signals(items, signals, today, log=sys.stderr):
    """把外部的热度数据存进 signals（就地修改并返回）。维基一天取一次（数据本来就按天），其他每次都取、一天留最大值。
    取不到的（限流、断网、没设 key）跳过，下次再取；已经存的不动。"""
    today = _day(today)
    for key in ("wiki", "steam", "anilist", "tmdb"):
        signals.setdefault(key, {})
    tmdb_key = os.environ.get("TMDB_API_KEY")
    # 维基：一天取一次（数据本来就按天出），所有关注项同一语言的词条合成一次请求
    due = [i for i in items if i.get("wiki") and (signals["wiki"].get(i["name"]) or {}).get("_at") != today.isoformat()]
    if due:
        try:
            views, failed = wiki_views([t for i in due for t in i["wiki"]], log=log)
            for i in due:
                got = [views[t] for t in i["wiki"] if t in views]
                partial = any(str(t).partition(":")[0] in failed for t in i["wiki"])
                old = signals["wiki"].get(i["name"])
                if not got or (partial and old):
                    continue  # 有语言没取到：有旧数据就先留着旧的（几种语言的和，前后才一致），下次再取
                days = {}
                for per in got:
                    for d, v in per.items():
                        days[d] = days.get(d, 0) + v
                # 不完整的（只取到一部分语言）不记 _at，下次收集再试
                signals["wiki"][i["name"]] = {**({} if partial else {"_at": today.isoformat()}), **days}
        except Exception as err:
            print(f"  [話題度] 维基：{err}", file=log)
    for item in items:
        name = item["name"]

        def keep(kind, value):
            if value is None:
                return
            box = signals[kind].setdefault(name, {})
            old = box.get(today.isoformat())
            box[today.isoformat()] = value if not isinstance(old, (int, float)) else max(old, value)

        try:
            if item.get("steam_appid"):
                keep("steam", steam_players(item["steam_appid"]))
        except Exception as err:
            print(f"  [話題度] Steam {name}：{err}", file=log)
        try:
            if item.get("type") == "anime" and (item.get("anilist_id") or item.get("keywords")):
                m = anilist_heat(item.get("anilist_id"), (item.get("keywords") or [""])[0], item.get("anilist_type", "ANIME"))
                box = signals["anilist"].setdefault(name, {})
                old = box.get(today.isoformat()) or {}
                box[today.isoformat()] = {"trending": max(m.get("trending") or 0, old.get("trending") or 0),
                                          "popularity": m.get("popularity") or old.get("popularity") or 0}
        except Exception as err:
            print(f"  [話題度] AniList {name}：{err}", file=log)
        try:
            if item.get("tmdb") and tmdb_key:
                keep("tmdb", tmdb_popularity(item["tmdb"], tmdb_key))
        except Exception as err:
            print(f"  [話題度] TMDB {name}：{err}", file=log)
    cutoff = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    names = {i["name"] for i in items}
    for kind, per in signals.items():
        if not isinstance(per, dict):
            continue
        for name in list(per):
            if name not in names:
                del per[name]
                continue
            per[name] = {d: v for d, v in per[name].items() if d.startswith("_") or d >= cutoff}
    return signals


# ---------- 读本地数据 ----------

def is_spam(title, url=""):
    import digest   # digest が heat を import しているので、使うときに読む
    return digest.is_spam(title, url)


def load_entries(inbox_files):
    """收集箱 → ({关注项: [条目]}, {关注项: [状态变了的日期]}, {关注项: 从哪天起连续收集})。同一链接只算一次。
    条目按消息本身的日期（date）算。「平常」只从连续收集开始的那天算：第一次收集（含新关注项往前补抓的几周）
    每次最多 30 条，比实际少得多，拿来当平常会让什么都像「平常的好几倍」。"""
    entries, changed, seen, since = {}, {}, set(), {}
    for path in inbox_files:
        try:
            data = json.loads(open(path, encoding="utf-8").read())
        except (OSError, ValueError):
            continue
        day = _day(data.get("date"))
        for it in data.get("items") or []:
            name = it.get("name")
            if day and (name not in since or day < since[name]):
                since[name] = day
            if any(f.get("changed") for f in it.get("facts") or []) and day:
                changed.setdefault(name, []).append(day)
            # reddit_cold：不火、没上版面的 Reddit 帖子（digest.ingest），帖子数照样算进「ファンの反応」
            for e in (it.get("entries") or []) + (it.get("reddit_cold") or []):
                if is_spam(e.get("title") or "", e.get("link") or ""):
                    continue   # 垃圾页（被黑的网站批量生成）不算「報道量」，不然话题度被灌水
                key = (name, e.get("url"))
                if not e.get("url") or key in seen:
                    continue
                seen.add(key)
                d = _day(e.get("date")) or day
                if d is None:
                    continue
                entries.setdefault(name, []).append({**e, "_d": d})
    return entries, changed, since


def load_stories(issues):
    """各期简报 → {关注项: [报道]}（weight、event 用）。"""
    out, seen = {}, set()
    for issue in issues:
        for b in issue.get("items") or []:
            for s in b.get("stories") or []:
                key = (b["name"], s.get("url"))
                if key in seen:
                    continue
                seen.add(key)
                out.setdefault(b["name"], []).append({**s, "_d": _day(s.get("date")) or _day(issue.get("date"))})
    return out


# ---------- 计算（不联网） ----------

def _window(xs, today, start, length):
    """xs 里日期在 [today-start-length+1, today-start] 的。"""
    hi = today - dt.timedelta(days=start)
    lo = hi - dt.timedelta(days=length - 1)
    return [x for x in xs if x["_d"] and lo <= x["_d"] <= hi]


MIN_COVER = 4  # 一周里至少有几天在连续收集的范围内，才拿来当「平常」（不满 7 天的按比例放大）


def _baseline(xs, today, since, measure):
    """过去 BASE_WEEKS 周（不含本周）的周平均。一周都凑不够 → None（网页上写「平常のデータを集め中」）。
    measure(那一周的条目, 那一周的最后一天)。"""
    vals = []
    for k in range(1, BASE_WEEKS + 1):
        hi = today - dt.timedelta(days=WEEK * k)
        cover = (hi - since).days + 1 if since else 0
        if cover < MIN_COVER:
            break
        vals.append(measure(_window(xs, today, WEEK * k, WEEK), hi) * WEEK / min(WEEK, cover))
    return sum(vals) / len(vals) if vals else None


def _decayed(xs, end):
    """越新越重：窗口最后一天 1，6 天前 1/7。"""
    return sum(1 - min(WEEK - 1, max(0, (end - x["_d"]).days)) / WEEK for x in xs)


def _breadth(xs):
    outlets = {x.get("source") or urllib.parse.urlparse(x.get("url") or "").netloc for x in xs} - {""}
    regions = {region(x.get("title") or "") for x in xs}
    return len(outlets) * (1 + 0.25 * max(0, len(regions) - 1)), len(outlets), len(regions)


def _series(per_day, today, start, length):
    """{日期: 数} 里某个窗口的平均（没有数据的日子不算）。全没有 → None。"""
    vals = [per_day.get((today - dt.timedelta(days=start + i)).isoformat()) for i in range(length)]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None


def _wiki_last(per_day, today):
    """维基的数据晚一天出：从最近有数的那天往回算。"""
    for lag in range(0, 4):
        if (today - dt.timedelta(days=lag)).isoformat() in per_day:
            return lag
    return None


def score_item(name, item, today, entries, changed, stories, signals, since):
    """一个关注项的话题度。返回 {score, label, dims: [{key, name, score, note}], used, rising}。"""
    media = [x for x in entries if not is_reddit(x)]
    posts = [x for x in entries if is_reddit(x)]
    week = _window(media, today, 0, WEEK)
    dims = {}

    # ① 報道量：越新越重的条目数，跟自己的周平均、跟尺子比
    cur = _decayed(week, today)
    base = _baseline(media, today, since, _decayed)
    dims["volume"] = (mix(cur, base, REF["volume"]), _with_ratio(f"7 日で {len(week)} 件", cur, base))

    # ② 広がり：媒体数 × 地区系数（每多一个语言地区 +25%）
    raw, outlets, regions = _breadth(week)
    base = _baseline(media, today, since, lambda xs, _: _breadth(xs)[0])
    dims["breadth"] = (mix(raw, base, REF["breadth"]), f"{outlets} 媒体・{regions} 地域" if outlets else "報道なし")

    # ③ 出来事：事件本身的分量（绝对分）
    pts, notes = 0.0, []
    urgent = sum(1 for x in week if x.get("urgent"))
    if urgent:
        pts += min(60, 40 + 10 * (urgent - 1))  # 1 件 40，之后每件 +10，最多 60
        notes.append(f"重要ニュース {urgent} 件")
    recent_changes = [d for d in changed if 0 <= (today - d).days < WEEK]
    if recent_changes:
        pts += 30
        notes.append("状態に変化")
    soon = []
    for s in stories:
        ev = s.get("event") if isinstance(s.get("event"), dict) else None
        d = _day((ev or {}).get("date"))
        if d and 0 <= (d - today).days <= EVENT_SOON:
            soon.append((d - today).days)
    if soon:
        pts += 30 * (1 - min(soon) / EVENT_SOON)
        notes.append("今日が予定日" if min(soon) == 0 else f"あと {min(soon)} 日で予定")
    heroes = sum(1 for s in stories if s.get("weight") == "hero" and s["_d"] and 0 <= (today - s["_d"]).days < WEEK)
    if heroes:
        pts += min(20, 10 * heroes)  # 头条多半就是要紧消息，少给一点，免得同一件事算两次
        notes.append(f"大きな記事 {heroes} 本")
    dims["event"] = (_clamp(pts), "・".join(notes) or "目立った出来事なし")

    # ④ 勢い：昨天和前天的速度 ÷ 再之前 5 天的速度（报道；有维基的话一起平均）。
    # 今天不算：今天还没过完，拿半天跟整天比总是像在降温
    parts, mnotes = [], []
    n2, n5 = len(_window(media, today, 1, 2)), len(_window(media, today, 3, 5))
    if n2 or n5:
        parts.append(rel_score(n2 / 2, n5 / 5) if n2 else 0.0)
        if n2:
            mnotes.append(f"記事 {(n2 / 2 + 1) / (n5 / 5 + 1):.1f} 倍")
    wiki = (signals.get("wiki") or {}).get(name) or {}
    lag = _wiki_last(wiki, today)
    if lag is not None:
        w2, w5 = _series(wiki, today, lag, 2), _series(wiki, today, lag + 2, 5)
        if w2 is not None and w5:
            parts.append(rel_score(w2, w5))
            mnotes.append(f"閲覧 {(w2 + 1) / (w5 + 1):.1f} 倍")
    dims["momentum"] = ((sum(parts) / len(parts)) if parts else 0.0,
                        ("昨日まで 2 日 ÷ その前 5 日：" + "・".join(mnotes)) if mnotes else "動きなし")

    # ⑤ 一般の関心：维基百科一天的浏览量（最近 7 天平均），跟自己的过去 4 周、跟尺子比
    if lag is not None:
        cur = _series(wiki, today, lag, WEEK) or 0
        olds = [v for v in (_series(wiki, today, lag + WEEK * k, WEEK) for k in range(1, BASE_WEEKS + 1)) if v is not None]
        base = sum(olds) / len(olds) if olds else None
        dims["public"] = (mix(cur, base, REF["wiki"]), _with_ratio(f"Wikipedia 1 日 {_num(cur)} 回", cur, base))

    # ⑥ ファンの反応：有哪个用哪个，平均
    fan, fnotes = [], []
    # Reddit：收集里有 Reddit、而且至少出现过一帖才算（日本的商品之类 Reddit 上本来就没人聊，不当成 0 分）
    uses_reddit = "reddit" in (item.get("use") or ["google", "bing", "reddit"]) or item.get("subreddits")
    if uses_reddit and posts:
        n = len(_window(posts, today, 0, WEEK))
        base = _baseline(posts, today, since, lambda xs, _: len(xs))
        fan.append(mix(n, base, REF["reddit"]))
        fnotes.append(f"Reddit {n} 件")
    steam = (signals.get("steam") or {}).get(name) or {}
    if steam:
        cur = _series(steam, today, 0, 1) or _series(steam, today, 0, 2)
        if cur is not None:
            base = _series(steam, today, 1, 14)
            fan.append(mix(cur, base, REF["steam"]))
            fnotes.append(f"Steam 同接 {_num(cur)}")
    ani = (signals.get("anilist") or {}).get(name) or {}
    if ani:
        trend = {d: v.get("trending") or 0 for d, v in ani.items() if isinstance(v, dict)}
        cur = _series(trend, today, 0, 2)
        if cur is not None:
            fan.append(mix(cur, _series(trend, today, 2, 14), REF["anilist"]))
            fnotes.append(f"AniList トレンド {cur:.0f}")
    tm = (signals.get("tmdb") or {}).get(name) or {}
    if tm:
        cur = _series(tm, today, 0, 2)
        if cur is not None:
            fan.append(mix(cur, _series(tm, today, 2, 14), REF["tmdb"]))
            fnotes.append(f"TMDB 人気 {cur:.0f}")
    if fan:
        dims["fandom"] = (sum(fan) / len(fan), "・".join(fnotes))

    used = [(k, label, w) for k, label, w in DIMS if k in dims]
    total = sum(dims[k][0] * w for k, _, w in used) / sum(w for _, _, w in used)
    score = round(total)
    return {
        "score": score,
        "label": next((lab for low, lab in LEVELS if score >= low), ""),
        "dims": [{"key": k, "name": label, "weight": w, "score": round(dims[k][0]), "note": dims[k][1]} for k, label, w in used],
        "missing": [label for k, label, _ in DIMS if k not in dims],
        "rising": dims["momentum"][0] >= RISING and score >= 30,
    }


def compute(items, inbox_files, issues, signals, today):
    """{关注项: 结果}，结果见 score_item，另加 delta（比 7 天前的分数，比不了是 None）和 top（贡献最大的维度）。"""
    today = _day(today)
    entries, changed, since = load_entries(inbox_files)
    stories = load_stories(issues)
    out = {}
    for item in items:
        name = item["name"]
        data = (entries.get(name, []), changed.get(name, []), stories.get(name, []), signals or {}, since.get(name))
        now = score_item(name, item, today, *data)
        # 前週比：用同样的数据算 7 天前的分数，不用另存历史。7 天前还没有满一周的连续收集时不比（只有补抓的旧闻，比了不准）
        then = today - dt.timedelta(days=WEEK)
        if since.get(name) and (then - since[name]).days >= WEEK - 1:
            now["delta"] = now["score"] - score_item(name, item, then, *data)["score"]
        else:
            now["delta"] = None
        top = max(now["dims"], key=lambda d: d["score"] * d["weight"]) if now["dims"] else None
        now["top"] = top["key"] if top else ""
        out[name] = now
    return out


def group_scores(items, inbox_files, issues, signals, today, groups):
    """小分類（板块の中のまとまり）の話題度。groups：{まとまりの名前: [関注項の名前]}。
    中の作品の点数を足すのではなく、中の作品の材料（記事・維基の閲覧・Steam…）を 1 つにまとめて、作品と同じ物差しで 0〜100 点を出す。
    同じ記事は 1 回だけ。維基・Steam は日ごとに合計、AniList / TMDB は日ごとに大きいほう。返り値：{まとまりの名前: score_item の結果}。"""
    today = _day(today)
    entries, changed, since = load_entries(inbox_files)
    stories = load_stories(issues)
    by = {i["name"]: i for i in items}
    out = {}
    for g, names in groups.items():
        names = [n for n in names if n in by]
        if not names:
            continue
        seen, ents, sts = set(), [], []
        for n in names:
            for x in entries.get(n, []):
                if x.get("url") not in seen:
                    seen.add(x.get("url")); ents.append(x)
            for x in stories.get(n, []):
                if ("s", x.get("url")) not in seen:
                    seen.add(("s", x.get("url"))); sts.append(x)
        chg = [d for n in names for d in changed.get(n, [])]
        starts = [since[n] for n in names if since.get(n)]
        key = "\x00group:" + "/".join(map(str, g if isinstance(g, tuple) else (g,)))
        sig = {}
        for kind, how in (("wiki", sum), ("steam", sum), ("anilist", None), ("tmdb", max)):
            merged = {}
            for n in names:
                for d, v in ((signals or {}).get(kind, {}).get(n) or {}).items():
                    if kind == "anilist":   # {trending: n}：大きいほう
                        if isinstance(v, dict) and (v.get("trending") or 0) >= ((merged.get(d) or {}).get("trending") or 0):
                            merged[d] = v
                    elif isinstance(v, (int, float)):
                        merged[d] = how([merged[d], v]) if d in merged else v
            if merged:
                sig[kind] = {key: merged}
        item = {"name": key, "use": sorted({u for n in names for u in (by[n].get("use") or ["google", "bing", "reddit"])}),
                "subreddits": [r for n in names for r in (by[n].get("subreddits") or [])]}
        out[g] = score_item(key, item, today, ents, chg, sts, sig, min(starts) if starts else None)
    return out


def heat_order(items, scores, sub_scores, sections):
    """板块の中の並び：小分類の話題度が高い順 → 小分類の中は作品の話題度が高い順（同点は items.yaml の順）。
    下級（parent）は上級のすぐ後ろ（下級どうしは話題度順）。板块の並び（sections の順）は変えない。
    items の各項目には section（表示用）と sub が入っていること。返り値：関注項の名前の並び。"""
    pos = {i["name"]: k for k, i in enumerate(items)}
    sc = lambda n: (scores.get(n) or {}).get("score", -1)
    names = {i["name"] for i in items}
    kids = {}
    for i in items:
        p = i.get("parent")
        if p in names and p != i["name"]:
            kids.setdefault(p, []).append(i)
    top = [i for i in items if not (i.get("parent") in names and i.get("parent") != i["name"])]
    rank_sec = {s: k for k, s in enumerate(sections)}
    out = []
    for sec in sorted({i["section"] for i in top}, key=lambda s: (rank_sec.get(s, len(sections)), s)):
        ins = [i for i in top if i["section"] == sec]
        subs = list(dict.fromkeys(i.get("sub") or "" for i in ins))
        subs.sort(key=lambda g: (-(sub_scores.get((sec, g)) or {}).get("score", -1),
                                 min(pos[i["name"]] for i in ins if (i.get("sub") or "") == g)))
        for g in subs:
            for i in sorted((i for i in ins if (i.get("sub") or "") == g), key=lambda i: (-sc(i["name"]), pos[i["name"]])):
                out.append(i["name"])
                out += [k["name"] for k in sorted(kids.get(i["name"], []), key=lambda k: (-sc(k["name"]), pos[k["name"]]))]
    return out


TREND_DAYS = 28  # 分析页的走势看几天


def analyze(items, inbox_files, issues, signals, today, days=TREND_DAYS):
    """分析页用：compute 的结果，再加每个关注项每天的分数（trend）、每天的报道数（articles）、维基浏览量（wiki）。
    走势只从连续收集开始的那天画起（之前只有补抓的旧闻，分数偏低，画出来像在猛涨）。
    返回 {"today", "baseline_from": 什么时候起有「平常」可比, "items": {关注项: 结果}}。"""
    day0 = _day(today)
    entries, changed, since = load_entries(inbox_files)
    stories = load_stories(issues)
    scores = compute(items, inbox_files, issues, signals, today)
    first = min(since.values()) if since else None
    out = {"today": day0.isoformat(),
           "baseline_from": (first + dt.timedelta(days=WEEK + MIN_COVER - 1)).isoformat() if first else None,
           "items": {}}
    dates = [day0 - dt.timedelta(days=i) for i in range(days - 1, -1, -1)]
    for item in items:
        name = item["name"]
        data = (entries.get(name, []), changed.get(name, []), stories.get(name, []), signals or {}, since.get(name))
        start = since.get(name)
        trend = [(d.isoformat(), score_item(name, item, d, *data)["score"]) for d in dates if start and d >= start]
        media = [x for x in entries.get(name, []) if not is_reddit(x)]
        per_day = {}
        for x in media:
            per_day[x["_d"].isoformat()] = per_day.get(x["_d"].isoformat(), 0) + 1
        articles = [(d.isoformat(), per_day.get(d.isoformat(), 0)) for d in dates]
        wiki = (signals or {}).get("wiki", {}).get(name) or {}
        views = [(d.isoformat(), wiki[d.isoformat()]) for d in dates if isinstance(wiki.get(d.isoformat()), int)]
        out["items"][name] = {**scores[name], "trend": trend, "articles": articles, "wiki": views,
                              "since": start.isoformat() if start else None}
    return out
