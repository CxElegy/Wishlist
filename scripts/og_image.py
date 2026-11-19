"""写真のない記事に、記事のページの代表の写真（og:image）を付ける（2026-11-08，店長：「只有文字的新闻也不好 我一定要图」）。

2026-11-19 作り直し（店長「点検は、本物の写真が取れるかどうかを含めること」）：写真を取るのは記事集め（userfeed.Media＝店長と同じ images.pick）。
ここはページを作るとき（user_pages.py）の**残りの最後の手**：
- 記事のページは店長と同じ道具（images.page・images.check）で読む（素の urllib の別の取り方はやめた）。Google ニュースの包みのままの網址は読まない（数だけ）。
- 結果は網址ごとに覚える（_fp/all.json の _og）。取れた写真は {"img", "at"}、取れなかったものは {"why", "at", "n"}＝理由と時刻と回数。
  失敗は永久に覚えない：理由ごとに間をあけて試し直す（retry_due。前の形の "" は時刻が無いので試し直しの対象）。
- 防盗链で、元のサイトを通さないと開けない写真（images._hard＝SAVED）は使わない（お客さまのページは hdimg を通らない。捨てた数をログに）。
- 試し直しの間隔の決め（RETRY_H）は userfeed.Media も同じものを使う（写真を探す段は 2 つでも、決めは 1 つ）。
"""
import concurrent.futures as cf
import datetime as dt
import html as htmllib
import re
import urllib.parse

import nostorage  # noqa: F401  公開の箱を落とさない止め（全部の網の道）

MAX_NEW = 150        # 1 回で新しく読む記事のページ
WORKERS = 8
MAX_BYTES = 400_000
KEEP_DAYS = 21       # 覚えの持ち日数（記事は 14 日で版面から落ちる：userfeed.KEEP_DAYS。少し長めに）
CANDS = 3            # 1 ページで確かめる代表の写真の候補（og:image → JSON-LD の順）
META = re.compile(r'<meta\b[^>]*>', re.I)
ATTR = re.compile(r'([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')

# 写真が取れなかった記事を、次に試すまでの時間（時間）。理由ごと。根拠：
# - 1 回目の失敗のあと（FIRST_RETRY_H）：同じ出来事の転載・Bing の縮小画像は数時間のうちに増える（前の RETRY_IMG_H と同じ 3 時間）。
# - 断られた（403・429・防機器人）／時間切れ／つながらない：そのサイトの壁・混み具合は数時間では変わらない。店長の本物のブラウザの
#   開き直し（images.BROWSER_SKIP_HOURS）・写真の置き場の取り直し（photo_store.RETRY_DAYS）と同じ 1 日。
# - 写真が無い（og:image も本文の図も無い・候補が小さい／ロゴ）：記事のページはまず変わらない。転載が増える分だけ 3 日に 1 回
#   （版面に残る 14 日で 4〜5 回）。防盗链（SAVED）で捨てたものも同じ（別の転載が見つかるかもしれない）。
# - 記事が消えた（404・410）：7 日（版面から落ちるまでに 1 回だけ確かめ直す）。
# - 包みのまま（原文に戻せず、ほかの手でも見つからない）：原文に戻せたらすぐ試し直す（userfeed.Media.link が印を消す）。戻せないままなら 1 日。
FIRST_RETRY_H = 3
RETRY_H = {"blocked": 24, "timeout": 24, "network": 24, "wrapped": 24, "none": 72, "saved": 72, "gone": 168}


def find(page, base=""):
    """記事のページの HTML → 代表の写真の網址（なければ None）。"""
    best = {}
    for m in META.finditer(page[:MAX_BYTES]):
        a = {k.lower(): (v3 or v4) for k, _, v3, v4 in ATTR.findall(m.group(0))}
        name = (a.get("property") or a.get("name") or "").lower()
        if name in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src") and a.get("content"):
            best.setdefault(name.split(":")[0], htmllib.unescape(a["content"].strip()))
    u = best.get("og") or best.get("twitter")
    if not u:
        return None
    u = urllib.parse.urljoin(base, u)
    return u if u.startswith(("http://", "https://")) else None


def why_of(reason, status=None):
    """写真が取れなかった理由の文（images.Result.reason・Page.reason・check の理由）→ 大分類（RETRY_H の鍵）。"""
    r = str(reason or "")
    if status in (404, 410) or re.search(r"原文 HTTP (?:404|410)\b", r):
        return "gone"
    if "防机器人" in r or re.search(r"HTTP (?:202|401|403|405|429|503)\b", r) or "限流" in r:
        return "blocked"
    if "找图超过" in r or "超时" in r:
        return "timeout"
    if "网络错误" in r:
        return "network"
    if "未还原" in r and not re.search(r"图片|太小|logo|空白|不是图片", r):
        return "wrapped"
    return "none"


def _ts(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def wait_h(why, n):
    """n 回目の失敗（理由 why）のあと、次に試すまでの時間。"""
    if int(n or 0) <= 1 and why != "gone":
        return FIRST_RETRY_H
    return RETRY_H.get(why or "none", RETRY_H["none"])


def retry_due(at, why, n, now):
    """前に取れなかった記事を、いま試し直してよいか（時刻の無い前の形は試し直す）。"""
    t = _ts(at)
    return t is None or now - t >= dt.timedelta(hours=wait_h(why, n))


def _memo_img(v):
    """覚えの値 → 写真の網址（取れていなければ ""）。前の形（文字列）も読む。"""
    if isinstance(v, str):
        return v
    return (v or {}).get("img") or "" if isinstance(v, dict) else ""


def memo_due(v, now):
    """覚えの値で、この網址をもう一度読んでよいか。覚え無し・前の形の ""（理由も時刻も無い）は試す。"""
    if v is None or v == "":
        return True
    if _memo_img(v):
        return False
    return retry_due(v.get("at"), v.get("why"), v.get("n"), now)


def prune(cache, now):
    """覚えから KEEP_DAYS より古いものを外す（前の形の文字列は時刻が無いので残す）。→ 外した数"""
    old = [u for u, v in cache.items() if isinstance(v, dict) and (_ts(v.get("at")) or now) < now - dt.timedelta(days=KEEP_DAYS)]
    for u in old:
        del cache[u]
    return len(old)


def _google(u):
    return "news.google.com" in str(u or "")


def read_one(url, page=None, check=None, hard=None):
    """1 本の記事のページから代表の写真を取る（店長と同じ images.page・images.check）。→ (写真 or None, 理由の大分類 or None)"""
    import images
    page = page or images.page
    check = check or images.check
    hard = images._hard if hard is None else hard
    p = page(url)
    if not p.ok:
        return None, why_of(p.reason, getattr(p, "status", None))
    whys, saved = [], False
    for u in [*p.og, *p.jsonld][:CANDS]:
        if images.GENERIC.search(urllib.parse.urlparse(u).path):
            whys.append("logo")
            continue
        ok, w = check(u)
        if ok and u in hard:
            saved = True   # 元のサイトを通さないと開けない（読者のブラウザでは 403）：使わない
            continue
        if ok:
            return u, None
        whys.append(w)
    if saved:
        return None, "saved"
    return None, why_of("；".join(whys)) if whys else "none"


def fill(rows, cache, page=None, check=None, now=None, log=print, hard=None):
    """rows = {版面: {"stories": [...], "pending": [...]}}。写真のない記事に image を入れる（覚えから・新しく読んで）。
    cache = 網址 → 覚え（取れた {"img","at"}・取れなかった {"why","at","n"}・前の形の文字列）。
    → 数 {"read", "new", "memo", "wrapped", "saved", "why": {理由: 数}, "touched": [image を入れた記事の dict]}"""
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    lack = [s for r in (rows or {}).values() for k in ("stories", "pending") for s in r.get(k) or []
            if isinstance(s, dict) and not s.get("image") and str(s.get("url") or "").startswith("http")]
    out = {"read": 0, "new": 0, "memo": 0, "wrapped": 0, "saved": 0, "why": {}, "touched": []}
    wrapped = {s["url"] for s in lack if _google(s["url"])}
    out["wrapped"] = len(wrapped)
    todo = [u for u in dict.fromkeys(s["url"] for s in lack) if u not in wrapped and memo_due(cache.get(u), now)][:MAX_NEW]

    def one(u):
        try:
            return u, *read_one(u, page, check, hard)
        except Exception:  # noqa: BLE001  読めないページは「つながらない」として間をあけて試し直す
            return u, None, "network"
    got = {}
    if todo:
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for u, img, why in ex.map(one, todo):
                prev = cache.get(u)
                if img:
                    cache[u] = {"img": img, "at": stamp}
                    got[u] = img
                else:
                    n = (prev.get("n") or 0) if isinstance(prev, dict) else 0
                    cache[u] = {"why": why, "at": stamp, "n": n + 1}
                    out["why"][why] = out["why"].get(why, 0) + 1
                    out["saved"] += why == "saved"
    out["read"] = len(todo)
    for s in lack:
        img = _memo_img(cache.get(s["url"]))
        if img:
            s["image"] = img
            out["new" if s["url"] in got else "memo"] += 1
            out["touched"].append(s)
    return out


def apply(stories, cache):
    """覚えにある写真を、写真のない記事に入れる（ネットに出ない）。→ 入れた記事の dict"""
    out = []
    for s in stories or []:
        if isinstance(s, dict) and not s.get("image"):
            img = _memo_img(cache.get(s.get("url")))
            if img:
                s["image"] = img
                out.append(s)
    return out


def log_line(t, written=None):
    """fill の数（何回分か足したもの）→ ログの 1 行（数だけ・網址や題は出さない：Actions のログは公開）。"""
    why = "・".join(f"{k} {v}" for k, v in sorted(t["why"].items())) or "なし"
    w = f"・書き戻し 版面 {written[0]}・行 {written[1]}" + (f"（書けず {written[2]}）" if written[2] else "") if written else ""
    return (f"記事の代表の写真：読んだ {t['read']}・新しく取れた {t['new']}・前の覚えから {t['memo']}・包みのまま読まない {t['wrapped']}"
            f"・SAVED で捨てた {t['saved']}・取れず（理由ごと）{why}{w}")


def add(total, t):
    """fill の数を足し合わせる（user_pages が 1 人ずつ呼ぶ分を 1 行にまとめる）。"""
    for k in ("read", "new", "memo", "wrapped", "saved"):
        total[k] = total.get(k, 0) + t[k]
    for k, v in t["why"].items():
        total.setdefault("why", {})[k] = total.get("why", {}).get(k, 0) + v
    total.setdefault("why", {})
    return total


def demote(rows):
    """写真がどうしても無い記事はカードにせず「整理待ち」（題だけの一覧）へ回す。版面に写真のある記事が 1 本もなければ動かさない。→ 回した数"""
    n = 0
    for r in (rows or {}).values():
        st = r.get("stories") or []
        no = [s for s in st if isinstance(s, dict) and not s.get("image")]
        if no and len(no) < len(st):
            r["stories"] = [s for s in st if s not in no]
            r["pending"] = no + list(r.get("pending") or [])
            n += len(no)
    return n
