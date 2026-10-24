"""お客さまの分の記事集め（2026-10-22，用户定的：お客さまも店長と同じ流れを自分の分で。AI は使わない・規則だけ）。

お客さまが選んだもの（Supabase app_users.prefs.picks = [{name, sec}]）のうち、店長のページに版面がないもの
（docs/home/index.html の section.sec[data-k] と、網页の AUTH_JS の shopHit と同じ規則で比べる）だけを、店長と同じ収集
（digest.collect → filter_entries：match・exclude・垃圾・exclude_sources・exclude_hosts・重複）とキーワード編集（fallback_stories）・
言語違いの重複（lang.dedupe）で集め、Supabase の user_boards（db/user_boards.sql）に本人の account（'u_' + md5(メール) の先頭 16 字）で書く。
本人は網页から my_boards() で自分の行だけを読む。リポジトリ・公開の網页には入れない（LOGIN.md 第 2 步「本人のページは本人だけ」）。

だれのために集めるか：userfeed_users()（db/user_boards.sql，secret key だけ）= Supabase Auth のユーザーがいて、一度はログインした人だけ
（だれでも呼べる登録の関数で作っただけの行・他人のメールで書き換えた好みでは、検索を使わせない）。
1 回の中では、まず全員の 1 つ目 → 全員の 2 つ目 … の順（1 人で全部を使わない）・まだ 1 つも集めていない人は 1 回 MAX_NEW_USERS_PER_RUN 人まで
（登録の古い順。大量の登録が先にいる人を押し出さない）。1 人の中では、まだ探していないもの（新しく足したものから）→ 前に探したのが古いもの。

    python scripts/userfeed.py            # Actions（SUPABASE_SERVICE_KEY があるとき）。digest.yml の収集のあと
    python scripts/userfeed.py --dry-run  # 何を集めるかだけ出す（ネットに出ない・書かない）
"""
import datetime as dt
import gzip
import hashlib
import html
import os
import re
import sys
import time
import urllib.parse

import digest
import lang
import sitedir
import sources
import taxonomy

MAX_BOARDS_PER_USER = 100  # 1 人が持てる「店長にない版面」。これを超えた分は state = limit の行（網页で「上限」と出す）。選んだ順の先頭から
PER_USER_PER_RUN = 10      # 1 人・1 回で集める版面（残りは次の回。全員の 1 つ目から順に）
MAX_NEW_USERS_PER_RUN = 15  # まだ 1 つも集めていない人を 1 回で何人まで（登録の古い順）
MAX_STORIES = 12           # 1 版面に残す記事（新しい順）
KEEP_DAYS = 14             # これより古い記事は版面から落とす（日付のない記事は最初に見つけた日 seen で数える）
MAX_BOARDS_PER_RUN = 80    # 1 回で集める版面（同じ名前・同じ言語は 1 回にまとめた数）
FAIL_SHOW = 5              # 続けてこの回数取れなかった 0 件の版面は「まだ見つかっていません」（それまでは「集めています」。db/user_boards.sql の my_boards と同じ数）
DEADLINE_MIN = 8           # 1 回の時間の上限
JOB_LIMIT_MIN = 40         # digest.yml の timeout-minutes（JOB_T0 から数えて、これの JOB_MARGIN_MIN 前には終える）
JOB_MARGIN_MIN = 3
WORKERS = 4                # 並列（同じサイトの間隔は店長の収集と同じく sources._pace でスレッド間で共有）
MIN_GAP_MIN = 90           # 前に探してからこれより短ければ今回は飛ばす（収集は 2 時間ごと。push のたびに走っても同じ版面を叩かない）
SUMMARY_CHARS = 160
PAGE = 1000                # Supabase（PostgREST）の 1 回の上限（max-rows）。これずつ読む
UPSERT_BATCH = 200
# 写真と原文の網址（2026-10-24，店長と同じ規則：sources.resolve_url で Google の跳转を原文に、images.pick で写真）
MEDIA_S = 150              # 1 回のうち写真・原文の網址に取っておく秒（記事集めはその残り。足りなければ次の回に続き）
MEDIA_STORIES = 4          # 1 版面で写真を探す記事（新しい順の頭から。頭条・ほかの注目ニュースに上がるのはこのあたり）
PICK_S = 20                # 1 本の写真探しの上限（秒）
RETRY_IMG_H = 24           # 写真が見つからなかった記事は、この時間あけてもう一度だけ探す（毎回同じ記事で時間を使わない）
RESOLVE_FAILS = 4          # Google の跳转が続けてこの回数戻せなかったら、この回は戻すのをやめる（断られているときに 1 本 6 秒待たない）

# 入口の「新しく始める」で選ぶ言語（welcome.LANG_GROUPS の code）→ 収集の言語（digest.NEWS_LANGS）・lang.py の言語
NEWS_LANG = {"ja": "ja-JP", "en": "en-US", "zh-Hans": "zh-CN", "zh-Hant": "zh-TW", "ko": "ko-KR"}
LANG_CODE = {"ja-JP": "ja", "en-US": "en", "zh-CN": "zh", "zh-TW": "zh", "ko-KR": "ko"}
DEFAULT_LANGS = ["ja-JP"]   # 集めていない言語だけを選んだ人は、サイトの主言語（日本語）で

# 英語の名前（Steam のカードの The Wrong Way・MEAT TRAIN）は普通の語のことが多い：数字のない短い名前は、その板块の下の語が
# 同じ記事に出てくるときだけ（CLAUDE.md「匹配词」：泛词・普通の語は主題の語と一緒に）。
# 語は前後が英字でないときだけ（「upcoming」の PC・「opened」の open に当てない）。普通の文にも出る語（update・open・live・PC・game・match・season・
# release・store・tour…）は入れない。数字だけの名前（「2027」）は、板块がなくても下の語のどれかと一緒のときだけ
SHORT_ASCII = 14
COMMON_FILE = __import__("pathlib").Path(__file__).resolve().parent / "data" / "en_common.txt.gz"
_COMMON = None
CJK = r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]"   # かな・漢字・ハングル
CONTEXT_EXTRA = {
    "游戏": r"Steam|PS5|PS4|PlayStation|Nintendo|Xbox|trailer|gameplay|DLC|early access|indie game|video ?game|発売|配信|体験版|アップデート|インディー|ゲーム|游戏|遊戲|게임",
    "影视": r"episode|trailer|anime|manga|Netflix|放送|予告|映画|アニメ|漫画|ドラマ",
    "演出": r"album|concert|MV|music video|ライブ|ツアー|新曲|アルバム|コンサート",
    "运动": r"league|tournament|championship|試合|大会|リーグ",
    "好物": r"collab|limited edition|コラボ|発売|限定|新作|グッズ",
    "生活": r"recipe|cafe|オープン|新メニュー|レシピ",
    "出行": r"travel|hotel|museum|exhibition|旅行|観光|展示|開催",
}
TM = re.compile(r"[®™©℠]")
SEASON = re.compile(r"\s*(?:第\s*\d+\s*(?:期|シーズン|部|章)|第[一二三四五六七八九十]+(?:期|部)|(?:the\s+)?\d+(?:st|nd|rd|th)\s+season|season\s*\d+"
                    r"|[(（][^()（）]*[)）])\s*$", re.I)
SPLIT = re.compile(r"[\s:：・\-–—/!！?？.,、。'’\"“”]+")
SEP = r"[\W_]*"
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def norm(s):
    return re.sub(r"\s+", "", str(s or "").lower())


def shop_hit(a, b):
    """店長の版面と同じものか（render.AUTH_JS の shopHit と同じ規則）：空白・大小を無視して同じ。
    または短いほうが長いほうに含まれ、短いほうがかな・漢字を含む 2 字以上（ちいかわ ⊂ ちいかわグッズ）か、
    英数字だけなら前後が英数字でない（ILLIT ⊂ ILLITライブ。From Software は FROM にしない）。"""
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b:
        return True
    s, l = (a, b) if len(a) <= len(b) else (b, a)
    if len(s) < 2:
        return False
    if not s.isascii():
        return s in l
    for m in re.finditer(re.escape(s), l):
        i, j = m.start(), m.end()
        if (i == 0 or not (l[i - 1].isascii() and l[i - 1].isalnum())) and (j == len(l) or not (l[j].isascii() and l[j].isalnum())):
            return True
    return False


loose_hit = shop_hit   # 前の名前


def account_of(email):
    """お客さまの account（db/user_boards.sql の private.user_account と同じ）。"""
    return "u_" + hashlib.md5(str(email or "").strip().lower().encode("utf-8")).hexdigest()[:16]


TRIM = " \t\n\r\f\v\u3000\u00a0"   # db/user_boards.sql の my_boards() の btrim と同じ文字（全角の空白も）


def pick_name(name):
    """prefs.picks の name → 行の item（db/user_boards.sql の my_boards() と同じ：前後の空白 TRIM を取って 80 字まで）。"""
    return str(name or "").strip(TRIM)[:80]


def news_langs(prefs):
    """prefs.lang = {primary, also: [...]}（入口で選んだもの）→ 集める言語（2 つまで、集めている言語だけ）。"""
    conf = (prefs or {}).get("lang") or {}
    if isinstance(conf, str):
        conf = {"primary": conf}
    codes = [conf.get("primary"), *(conf.get("also") or [])] if isinstance(conf, dict) else []
    out = []
    for c in codes:
        n = NEWS_LANG.get(c)
        if n and n not in out:
            out.append(n)
    return out[:2] or list(DEFAULT_LANGS)


def base_names(name):
    """検索・匹配に使う名前：® ™ を取り、末尾の「第2期」「Season 2」「（2025）」を外したものも。"""
    clean = re.sub(r"\s+", " ", TM.sub("", str(name))).strip()
    out = [clean] if clean else []
    b = SEASON.sub("", clean).strip(" :：-–—")
    if b and b != clean and len(norm(b)) >= 2:
        out.append(b)
    return out


def _ascii_token(t):
    return f"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])"


def _context(sec):
    """板块の語（前後が英字でないときだけ当たる形）。板块がなければ空。sections.yaml の words（板块を決めるための語：character・food・toy…）は
    普通の記事にも出るので使わない（CONTEXT_EXTRA だけ）。"""
    w = CONTEXT_EXTRA.get(sec, "")
    return f"(?<![A-Za-z])(?:{w})(?![A-Za-z])" if w else ""


def _any_context():
    return f"(?<![A-Za-z])(?:{'|'.join(CONTEXT_EXTRA.values())})(?![A-Za-z])"


def common_en():
    """英語のよく使う語の集まり（scripts/data/en_common.txt.gz：wordfreq の zipf ≥ 3.0、英字 3 字以上）。"""
    global _COMMON
    if _COMMON is None:
        with gzip.open(COMMON_FILE, "rt", encoding="utf-8") as f:
            _COMMON = frozenset(w for w in (line.strip() for line in f) if w and not w.startswith("#"))
    return _COMMON


def ascii_kind(name):
    """英字の名前の種類（match_terms が使う。2026-10-22 に 10 月の inbox 7512 件で測って決めた：名前を含む記事のうち
    前の規則で拾えたのは ILLIT 59/208・Vaundy 8/48・Astrae Oratio 0/40 → この規則で 208/208・48/48・37/40）：
    'proper' = よく使う語ではない 4 字以上の語を含む（ILLIT・Vaundy・NewJeans・Astrae Oratio・Moka）→ 名前だけで当てる
    'phrase' = 2 語以上で、全部がよく使う語か 3 字以下（The Wrong Way・Hollow Knight・MEAT TRAIN）→ ジャンルの語と一緒か、
               かな・漢字・ハングルの記事（日本語・中国語・韓国語の記事に英字の句で出てくるのは名前のことがほとんど）
    'word'   = よく使う 1 語・3 字以下の 1 語（Apex・Switch・Tokyo・IVE）→ ジャンルの語と一緒のときだけ
               （日本語の記事でも「APEX-TOYS」「Numero TOKYO」のように別の名前の一部で出る）"""
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", name)]
    common = common_en()
    if any(len(w) >= 4 and w not in common for w in words):
        return "proper"
    return "phrase" if len(words) >= 2 else "word"


def has_word(name):
    """記号だけの名前（「...」「！？」）でないか：英数字・かな・漢字・ハングルが 1 字でもあるか。"""
    return any(c.isalnum() for c in str(name or ""))


SUFFIX_GENERIC = {"開催", "発売", "配信", "限定", "新作", "オープン", "大会", "試合", "予告", "放送"}   # どこにでも出る語：「広島」と一緒でも旅行の記事とは限らない


def _suffix(name):
    """かな・漢字 1 語の名前の末尾がジャンルの語（「広島旅行」の旅行）→ (前の部分, その板块の語)。なければ None。"""
    for sec, words in CONTEXT_EXTRA.items():
        for w in words.split("|"):
            if w.isascii() or len(w) < 2:
                continue
            if name.endswith(w) and len(name) - len(w) >= 2:
                stem = name[: -len(w)]
                cjk = "|".join(x for x in words.split("|") if not x.isascii() and (x == w or x not in SUFFIX_GENERIC))
                return stem, cjk
    return None


def match_terms(name, sec=None):
    """1 つの名前の匹配词（digest.match_hit が読む形）。記号だけの名前は []（集めない）。
    - 英数字だけ：語を空白・記号のゆれ（「:」「®」「’」）を許してつないだ 1 つの句（語の境あり）。数字があるか長い名前・よく使う語でない名前
      （ascii_kind = proper）はそれだけで。よく使う語の名前は板块の語と一緒のとき（2 語以上の句は、かな・漢字・ハングルの記事でも）
    - かな・漢字を含む 1 語：名前そのもの（空白・大小を無視）。末尾がジャンルの語（「広島旅行」）なら、前の部分と同じジャンルの語が両方ある記事も（広島 観光）
    - かな・漢字を含む数語（「広島 旅行」）：全部の語が出てくる記事（先読み）。数字・2 字以下の英字は前の語にくっつける（数字だけでは当てない）"""
    if not has_word(name):
        return []
    toks = [t for t in SPLIT.split(name) if t]
    if not toks:
        return []
    if name.isascii():
        phrase = r"(?<![A-Za-z0-9])" + SEP.join(re.escape(t) for t in toks) + r"(?![A-Za-z0-9])"
        ctx = _context(sec)
        kind = None
        if not any(c.isalpha() for c in name):   # 数字・記号だけ（「2027」）：年号などに当たるので、必ずジャンルの語と一緒に
            ctx = ctx or _any_context()
        elif any(c.isdigit() for c in name) or len(norm(name)) > SHORT_ASCII:
            ctx = ""
        else:
            kind = ascii_kind(name)
            if kind == "proper":
                ctx = ""
        if not ctx and kind in ("phrase", "word"):
            ctx = _any_context()   # 板块がわからない：どれかのジャンルの語と一緒に
        if ctx:
            out = [f"re:(?s)(?=.*(?i:{phrase}))(?=.*(?i:{ctx}))"]
            if kind == "phrase":
                out.append(f"re:(?s)(?=.*(?i:{phrase}))(?=.*{CJK})")
            return out
        return [f"re:(?i){phrase}"]
    if len(toks) == 1:
        suf = _suffix(name)
        if suf:
            return [name, f"re:(?s)(?=.*{re.escape(suf[0])})(?=.*(?:{suf[1]}))"]
        return [name]
    groups = []
    for t in toks:
        tail = t.isdigit() or t.isascii() and len(t) <= 2
        piece = _ascii_token(t) if t.isascii() else re.escape(t)
        if tail and groups:
            groups[-1] += SEP + piece
        else:
            groups.append(piece)
    if len(groups) == 1:
        return [name, f"re:(?i){groups[0]}"]
    return [name, "re:(?is)" + "".join(f"(?=.*{g})" for g in groups)]


def board_item(name, sec, langs):
    """お客さまの 1 版面の、簡単な関注項（店長の items.yaml と同じ形）。匹配词は match_terms。
    名前が普通の言葉のこともあるので SNS（Reddit・Bluesky・Mastodon）の全体検索はしない・GDELT は店長の収集に残す。"""
    name = pick_name(name)
    sec = taxonomy.canonical(sec) if sec else None
    names = base_names(name) or [name]
    match = list(dict.fromkeys(w for n in names for w in match_terms(n, sec)))
    item = {"name": name, "keywords": names[:2], "match": match or [name], "news_langs": list(langs),
            "use": ["google", "bing"], "gdelt": False, "type": "product", "max_entries": 30}
    if sec in taxonomy.SECTIONS:
        item["section"] = sec
    return item


def clean_text(s):
    """外から来た文字（見出し・要約）：タグを取り、&amp; などを戻し、制御文字（jsonb が受け付けない \\u0000 など）を消す。
    網页は textContent / esc で描く（ここで安全にしたことにしない）。"""
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    s = CTRL.sub("", html.unescape(s))
    return re.sub(r"\s+", " ", s).strip()


def _strip_source(title, source):
    """Google ニュースの見出しの末尾「 - 媒体名」を取る（店長の版面と同じ見え方）。"""
    src = str(source or "").strip()
    if src and len(title) > len(src) + 8:
        for sep in (" - ", " | ", "｜", " – "):
            if title.endswith(sep + src):
                return title[: -len(sep + src)].rstrip()
    return title


def _http(u):
    u = str(u or "").strip()
    return u if u.startswith(("https://", "http://")) else ""


def story_of(e):
    title = _strip_source(clean_text(e.title), e.source)
    return {"title": title, "url": _http(e.link) or _http(e.url), "source": clean_text(e.source)[:60],
            "date": e.published.isoformat() if e.published else None,
            "image": e.image if str(e.image or "").startswith("https://") else "",
            "summary": clean_text(e.summary)[:SUMMARY_CHARS]}


def lang_order(langs):
    """lang.dedupe に渡す言語の順。日本語を選んだ人は zh を最後に足す：かなのない日本語の見出し（「広島市長選 告示」）は
    lang.detect が zh と見るので、それで落とさない（日本語の検索で来たものなので）。"""
    order = list(dict.fromkeys(LANG_CODE[l] for l in langs if l in LANG_CODE)) or ["ja"]
    if "ja" in order and "zh" not in order:
        order.append("zh")
    return order


def stories_for(item, settings):
    """1 版面の記事（新しい順、MAX_STORIES 件まで）。店長の収集と同じ絞り込み・キーワード編集・言語違いの重複。"""
    now = dt.datetime.now(dt.timezone.utc)
    before = sources.fetch_fails()
    raw = digest.collect(item, settings)
    if not raw and sources.fetch_fails() > before:
        # 検索に断られた（429）・時間切れで 1 件も来なかった：digest.collect は空を返して続けるので、ここで失敗にする
        # （fails を数える。「まだ見つかっていません」と言わず「集めています」のまま。my_boards）
        raise RuntimeError("検索が取れなかった")
    entries = digest.filter_entries(raw, item, settings, set(), now)
    picked = digest.fallback_stories(entries, item, limit=MAX_STORIES)
    out = [story_of(entries[p["refs"][0] - 1]) for p in picked]
    out = [{**s, "headline": s["title"]} for s in out if s["title"] and s["url"]]
    return [{k: v for k, v in s.items() if k != "headline"} for s in lang.dedupe(out, lang_order(item["news_langs"]))]


def _when(s):
    for k in ("date", "seen"):
        try:
            d = dt.datetime.fromisoformat(str(s.get(k) or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    return None


def _google(u):
    return "news.google.com" in str(u or "")


def merge(old, new, now=None):
    """前の回の記事に今回の分を足す（同じ網址・同じ見出しは 1 本、KEEP_DAYS より古いものは落とす、新しい順に MAX_STORIES）。
    同じ記事が Google の跳转と原文の網址の両方で来たら原文のほうを残す。日付のない記事は最初に見つけた時刻（seen）を付けて数える。
    → (記事, 新しく増えた件数)"""
    now = now or dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=KEEP_DAYS)
    stamp = now.isoformat(timespec="seconds")
    index, out, fresh = {}, [], set()
    for s, is_new in [*((s, False) for s in old or []), *((s, True) for s in new or [])]:
        if not isinstance(s, dict) or not s.get("title") or not _http(s.get("url")):
            continue
        s = dict(s)
        if not s.get("date") and not s.get("seen"):
            s["seen"] = stamp
        keys = {s["url"], digest.title_key(s["title"])}
        hit = next((index[k] for k in keys if k in index), None)
        if hit is not None:
            prev = out[hit]
            if _google(prev["url"]) and not _google(s["url"]):   # 原文の網址・見出しに替える（新しく増えた数には入れない）
                out[hit] = {**prev, "url": s["url"], "title": s["title"], "image": prev.get("image") or s.get("image") or ""}
                for k in keys:
                    index[k] = hit
            continue
        when = _when(s)
        if when and when < since or digest.is_spam(s["title"], s["url"]):
            continue
        for k in keys:
            index[k] = len(out)
        out.append(s)
        if is_new:
            fresh.add(len(out) - 1)
    order = sorted(range(len(out)), key=lambda i: _when(out[i]) or since, reverse=True)[:MAX_STORIES]
    return [out[i] for i in order], sum(1 for i in order if i in fresh)


class Media:
    """記事に原文の網址と写真を付ける（店長の出刊 digest.attach_media と同じ部品：sources.resolve_url・images.pick）。
    同じ網址は 1 回の中で 1 度だけ調べる（同じ版面を何人が追いかけていても）。写真の見つからなかった記事は RETRY_IMG_H 時間あける。
    本站に保存しないと出せない写真（images.SAVED：読者のブラウザでは拒まれる）は使わない（お客さまのページは hdimg を通らない）。"""

    def __init__(self, deadline, now=None, resolve=None, pick=None):
        import threading
        self.deadline, self.now = deadline, now or dt.datetime.now(dt.timezone.utc)
        self.resolve = resolve or (lambda u: sources.resolve_url(u, tries=1))
        self.pick = pick or self._pick
        self.links, self.imgs, self.lock = {}, {}, threading.Lock()
        self.fails = 0
        self.stats = {"links": 0, "images": 0}

    @staticmethod
    def _pick(story, budget, avoid):
        import images
        e = sources.Entry(title=story["title"], url=story["url"], published=None, source=story.get("source") or "",
                          image=story.get("image") or None)
        res = images.pick(None, [e], story["url"], budget=budget, avoid=avoid)
        return res.image if res.image and images.SAVED not in (res.source or "") else None

    def _left(self):
        return self.deadline - time.monotonic()

    def link(self, s):
        u = s["url"]
        if not _google(u) or self.fails >= RESOLVE_FAILS or self._left() < 5:
            return False
        with self.lock:
            real = self.links.get(u)
        if real is None:
            try:
                real = self.resolve(u)
            except Exception:  # noqa: BLE001  戻せなくても記事は出す（Google の網址のまま）
                real = u
            real = real if _http(real) and not _google(real) else ""
            with self.lock:
                self.links[u] = real
                self.fails = 0 if real else self.fails + 1
        if not real:
            return False
        s["url"] = real
        self.stats["links"] += 1
        return True

    def image(self, s, avoid):
        if s.get("image") or _google(s["url"]) or self._left() < 5:
            return False
        tried = _when({"date": s.get("img_at")})
        if tried and self.now - tried < dt.timedelta(hours=RETRY_IMG_H):
            return False
        with self.lock:
            hit = self.imgs.get(s["url"], ())
        if hit == ():
            try:
                hit = self.pick(s, min(PICK_S, max(1, self._left() - 3)), set(avoid))
            except Exception:  # noqa: BLE001  写真がなくても記事は出す
                hit = None
            with self.lock:
                self.imgs[s["url"]] = hit
        if hit and hit not in avoid:
            s["image"] = hit
            s.pop("img_at", None)
            avoid.add(hit)
            self.stats["images"] += 1
        else:
            s["img_at"] = self.now.isoformat(timespec="seconds")
        return True

    def board(self, stories):
        """1 版面の記事（新しい順）を直す。→ 変わったか"""
        changed = False
        for s in stories or []:
            changed |= self.link(s)
        avoid = {s["image"] for s in stories or [] if s.get("image")}
        for s in (stories or [])[:MEDIA_STORIES]:
            changed |= self.image(s, avoid)
        return changed


def needs_media(stories, now):
    """まだ原文の網址・写真を付けられる記事があるか（Google の跳转、または頭の数本に写真がなく、前に探してから RETRY_IMG_H 時間たった）。"""
    for i, s in enumerate(stories or []):
        if _google(s.get("url")):
            return True
        if i < MEDIA_STORIES and not s.get("image"):
            tried = _when({"date": s.get("img_at")})
            if not tried or now - tried >= dt.timedelta(hours=RETRY_IMG_H):
                return True
    return False


def add_media(make, out, rows, keep, now, started, log):
    """書く行（out）と、今回は探さなかった行のうち原文の網址・写真がまだのものに、残りの時間で Media をかける（並列）。
    探さなかった行で変わったものは out に足して書く。時間が足りなければ次の回に続き（needs_media がまた拾う）。"""
    left = budget_sec() - (time.monotonic() - started) - 10
    written = {(r["account"], r["item"]) for r in out}
    cand = [r for r in out if r.get("state") == "ok" and needs_media(r.get("stories"), now)]
    extra = [r for r in rows if (r["account"], r["item"]) not in written and r.get("state") == "ok"
             and r["item"] in keep.get(r["account"], ()) and needs_media(r.get("stories"), now)]
    if left < 20 or not (cand or extra):
        if cand or extra:
            log(f"お客さまの記事の写真：時間が足りないので次の回へ（{len(cand) + len(extra)} 版面）")
        return
    m = make(time.monotonic() + left, now)

    def one(r):
        stories = [dict(s) for s in r.get("stories") or []]   # 時間切れのスレッドが書く行を書き換えないように写しで
        return stories if m.board(stories) else None
    key = lambda r: (r["account"], r["item"])   # noqa: E731
    got, cut = digest.run_parallel(one, cand + extra, WORKERS, left, key=key)
    fixed = 0
    for r in cand:
        if got.get(key(r)) is not None:
            r["stories"] = got[key(r)]
            fixed += 1
    for r in extra:
        if got.get(key(r)) is not None:
            out.append({k: r.get(k) for k in ("account", "item", "sec", "state", "checked_at", "updated_at")}
                       | {"found": int(r.get("found") or 0), "fails": int(r.get("fails") or 0), "stories": got[key(r)]})
            fixed += 1
    log(f"お客さまの記事の写真：{fixed} 版面を直した・原文の網址 {m.stats['links']} 本・写真 {m.stats['images']} 枚"
        + (f"・時間切れ {len(cut)}（次の回へ）" if cut else ""))


def _ts(at):
    try:
        return dt.datetime.fromisoformat(str(at).replace("Z", "+00:00")) if at else None
    except ValueError:
        return None


def plan(users, shop_names, rows, now=None):
    """集める版面を決める。→ (todo, keep, limits, blanks)
    todo = [{key, name, sec, langs, boards: [(account, item, sec)], rank, last}]（同じ名前・同じ言語・同じ匹配词は 1 回にまとめる。
    英字のよく使う語の名前は板块で匹配词が変わるので、別のジャンルで選んだ人とは分ける）
    keep = {account: {item, ...}}（いま選んでいる、店長にないもの。上限を超えた分も。これ以外の行は消す）
    limits = [(account, item, sec)]（上限を超えた分。state = limit の行を書く）
    blanks = [(account, item, sec)]（記号だけの名前「...」：何にでも当たるので集めない。0 件の行を 1 度だけ書く → 網页は「まだ見つかっていません」）"""
    now = now or dt.datetime.now(dt.timezone.utc)
    checked = {(r["account"], r["item"]): r.get("checked_at") for r in rows}
    state = {(r["account"], r["item"]): r.get("state") for r in rows}
    has_rows = {r["account"] for r in rows if r.get("state") != "limit"}
    keep, groups, limits, blanks, new_users = {}, {}, [], [], 0
    for u in users:
        email = u.get("email")
        prefs = u.get("prefs") or {}
        picks = prefs.get("picks") if isinstance(prefs, dict) else None
        if not email or not isinstance(picks, list):
            continue
        acct, langs = account_of(email), news_langs(prefs)
        mine, seen, cand = keep.setdefault(acct, set()), set(), []
        for pos, p in enumerate(picks):
            if not isinstance(p, dict):
                continue
            name = pick_name(p.get("name"))
            if not name or norm(name) in seen:
                continue
            seen.add(norm(name))
            if any(shop_hit(s, name) for s in shop_names):
                continue   # 店長の版面をそのまま見せる
            sec = p.get("sec") or None
            mine.add(name)
            if len(mine) > MAX_BOARDS_PER_USER:
                if state.get((acct, name)) != "limit":
                    limits.append((acct, name, sec))
                continue
            if not has_word(name):
                if (acct, name) not in checked or state.get((acct, name)) == "limit":
                    blanks.append((acct, name, sec))
                continue
            last = _ts(checked.get((acct, name))) if state.get((acct, name)) != "limit" else None
            if last and (now - last).total_seconds() < MIN_GAP_MIN * 60:
                continue
            cand.append((last, -pos, name, sec))
        if not cand:
            continue
        if acct not in has_rows:
            if new_users >= MAX_NEW_USERS_PER_RUN:
                continue   # 次の回に（行がないので「集めています」のまま）
            new_users += 1
        cand.sort(key=lambda c: (c[0] is not None, c[0] or now, c[1]))   # まだ探していない（新しく足したものから）→ 古いもの
        for rank, (last, _, name, sec) in enumerate(cand[:PER_USER_PER_RUN]):
            key = (norm(name), tuple(langs), tuple(board_item(name, sec, langs)["match"]))
            g = groups.setdefault(key, {"key": key, "name": name, "sec": sec, "langs": langs, "boards": [], "last": last, "rank": rank})
            g["boards"].append((acct, name, sec))
            g["rank"] = min(g["rank"], rank)
            if last is None or g["last"] and last < g["last"]:
                g["last"] = last
    todo = sorted(groups.values(), key=lambda g: (g["rank"], g["last"] is not None, g["last"] or now))
    return todo[:MAX_BOARDS_PER_RUN], keep, limits, blanks


def shop_boards(path=None):
    """店長のページに出ている版面の名前（網页の AUTH_JS が見るのと同じ section.sec[data-k]）。読めなければ None。"""
    path = path or sitedir.SITE_DIR / "index.html"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    out = []
    for tag in re.findall(r"<section\b[^>]*>", text):
        cls = re.search(r'\bclass="([^"]*)"', tag)
        k = re.search(r'\bdata-k="([^"]*)"', tag)
        if cls and k and "sec" in cls.group(1).split():
            out.append(html.unescape(k.group(1)))
    return out


DB_ERRORS = (RuntimeError, OSError)   # digest.supabase は HTTP の失敗を RuntimeError に。つながらない・時間切れ（URLError・TimeoutError）は OSError


def _q(v):
    return urllib.parse.quote(str(v), safe="")


def fetch_all(db, path, body=None):
    """PAGE 行ずつ全部読む。→ (行, 全部読めたか)。鍵がなければ (None, False)。"""
    out, offset = [], 0
    while True:
        try:
            if body is None:
                got = db(f"{path}&limit={PAGE}&offset={offset}")
            else:
                got = db(path, {**body, "p_limit": PAGE, "p_offset": offset})
        except DB_ERRORS:
            if offset == 0:
                raise
            return out, False
        if got is None:
            return (None, False) if offset == 0 else (out, False)
        out += got
        if len(got) < PAGE:
            return out, True
        offset += PAGE


def _clean_row(r):
    def fix(v):
        if isinstance(v, str):
            return CTRL.sub("", v)
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        return v
    return fix(r)


def _why(err):
    """ログに出す失敗の理由：種類と HTTP の番号だけ（Supabase・検索の返事には選んだものの名前が入ることがある。ログは公開の Actions と
    管理ページのライブログに出るので、お客さまの選んだものは書かない）。"""
    m = re.match(r"HTTP \d+", str(err))
    return f"{type(err).__name__}{' ' + m.group(0) if m else ''}"


def upsert(db, rows, log):
    """200 行ずつ書く。まとめて断られたら 1 行ずつ書き直す（壊れた 1 行で後ろの人の版面を止めない）。→ 書けなかった行の数。
    PostgREST はまとめて書く行の列がそろっていないと断るので、列の組ごとに分けて書く（失敗の行だけにある fails など）。"""
    bad = 0
    groups = {}
    for r in rows:
        groups.setdefault(tuple(sorted(r)), []).append(r)
    for same in groups.values():
        for i in range(0, len(same), UPSERT_BATCH):
            part = [_clean_row(r) for r in same[i:i + UPSERT_BATCH]]
            try:
                db("user_boards?on_conflict=account,item", part, "resolution=merge-duplicates,return=minimal")
                continue
            except DB_ERRORS:
                pass
            for r in part:
                try:
                    db("user_boards?on_conflict=account,item", [r], "resolution=merge-duplicates,return=minimal")
                except DB_ERRORS as err:
                    bad += 1
                    log(f"  1 行が書けなかった（{_why(err)}）")
    return bad


def budget_sec(now_mono=None):
    """この回に使える秒。digest.yml が JOB_T0（job を始めた時刻）を渡していれば、job の timeout の JOB_MARGIN_MIN 分前までに収める。"""
    left = DEADLINE_MIN * 60
    t0 = os.environ.get("JOB_T0")
    if t0 and t0.isdigit():
        job_left = (JOB_LIMIT_MIN - JOB_MARGIN_MIN) * 60 - (time.time() - int(t0))
        left = min(left, job_left)
    return left


def run(dry_run=False, db=None, collect=None, now=None, log=print, shop=None, media=None):
    """1 回分。db = supabase() と同じ形の関数（テストで差し替える）、collect = stories_for と同じ形、shop = 店長の版面の名前、
    media = Media と同じ形を作る関数（deadline → Media。既定は本物の収集のときだけ Media、collect を差し替えたテストでは付けない）。
    → {"boards": 書いた版面, "found": 新しい記事, "late": 時間切れ, "failed": 失敗, "deleted": 消した行, "limit": 上限の行, "bad": 書けなかった行}"""
    db = db or digest.supabase
    if media is None and collect is None:
        media = Media
    collect = collect or stories_for
    started = time.monotonic()
    now = now or dt.datetime.now(dt.timezone.utc)
    res = {"boards": 0, "found": 0, "late": 0, "failed": 0, "deleted": 0, "limit": 0, "bad": 0}
    settings, items = digest.load_config()
    shop_names = shop if shop is not None else shop_boards()
    if shop_names is None:
        shop_names = [i["name"] for i in items]
    users, users_all = fetch_all(db, "rpc/userfeed_users", {})
    if users is None:
        log("お客さまの記事集め：Supabase の鍵がないので飛ばす")
        return res
    rows, rows_all = fetch_all(db, "user_boards?select=*&order=account.asc,item.asc")   # * ：fails（後から足した列）がまだない DB でも読める
    rows = rows or []
    todo, keep, limits, blanks = plan(users, shop_names, rows, now)
    # ログは公開の Actions と管理ページのライブログに出る：数だけ（お客さまの選んだものの名前は書かない。LOGIN.md 第 2 步）
    log(f"お客さまの記事集め：{len(users)} 人・集める版面 {len(todo)}" + (f"・上限を超えた {len(limits)}" if limits else ""))
    if dry_run:
        return {**res, "boards": len(todo), "limit": len(limits)}
    left = budget_sec() - (time.monotonic() - started)
    if todo and left < 60:
        log(f"お客さまの記事集め：時間が足りないので次の回へ（残り {max(0, left):.0f} 秒）")
        todo, late = [], todo
    else:
        late = []

    def one(g):
        try:
            return collect(board_item(g["name"], g["sec"], g["langs"]), settings)
        except Exception as err:  # noqa: BLE001  1 版面の失敗で全体を止めない
            log(f"  版面 {todo.index(g) + 1}/{len(todo)}：取れなかった（{_why(err)}）")
            return None
    got, cut = digest.run_parallel(one, todo, WORKERS, max(30, left - (MEDIA_S if media else 0)), key=lambda g: g["key"]) if todo else ({}, [])
    late_n = len(late) + len(cut)
    old = {(r["account"], r["item"]): r for r in rows}
    stamp = now.isoformat(timespec="seconds")
    out = []
    for g in todo:
        if g["key"] in cut:
            continue   # 次の回に先に取る（checked_at を進めない）
        new = got.get(g["key"])
        if new is None:
            # 失敗：記事はそのまま・fails を 1 つ増やし、探した時刻を進める（次の回の列の後ろへ。毎回 1 人分の枠を取り続けない）。
            # 網页は 0 件で fails が FAIL_SHOW 未満なら「集めています」のまま（「見つかっていません」と言わない。my_boards）
            res["failed"] += 1
            for acct, name, sec in g["boards"]:
                prev = old.get((acct, name)) or {}
                out.append({"account": acct, "item": name, "sec": sec, "state": "ok", "stories": prev.get("stories") or [],
                            "found": 0, "fails": int(prev.get("fails") or 0) + 1, "checked_at": stamp, "updated_at": prev.get("updated_at")})
            continue
        for acct, name, sec in g["boards"]:
            prev = old.get((acct, name)) or {}
            stories, n = merge(prev.get("stories"), new, now)
            res["found"] += n
            row = {"account": acct, "item": name, "sec": sec, "state": "ok", "stories": stories, "found": n,
                   "checked_at": stamp, "updated_at": stamp if n else prev.get("updated_at")}
            if prev.get("fails"):
                row["fails"] = 0
            out.append(row)
    if media:
        add_media(media, out, rows, keep, now, started, log)
    for acct, name, sec in limits:
        out.append({"account": acct, "item": name, "sec": sec, "state": "limit", "stories": [], "found": 0,
                    "checked_at": stamp, "updated_at": None})
    for acct, name, sec in blanks:   # 記号だけの名前：探さない（fails 0・記事 0 → my_boards は none）
        out.append({"account": acct, "item": name, "sec": sec, "state": "ok", "stories": [], "found": 0, "fails": 0,
                    "checked_at": stamp, "updated_at": None})
    res["boards"], res["limit"], res["late"] = len(out) - len(limits) - len(blanks), len(limits), late_n
    res["bad"] = upsert(db, out, log) if out else 0
    if users_all and rows_all:   # 一部しか読めなかったときは消さない（読めなかった人の版面を消してしまう）
        for r in rows:   # 外したもの・店長の版面に入ったもの・退会した人の行は消す（本人の画面には出ない行）
            if r["item"] not in keep.get(r["account"], ()):
                try:
                    db(f"user_boards?account=eq.{_q(r['account'])}&item=eq.{_q(r['item'])}", method="DELETE")
                    res["deleted"] += 1
                except DB_ERRORS as err:
                    log(f"  1 行が消せなかった（{_why(err)}）")
    elif rows:
        log("お客さまの記事集め：一覧を全部は読めなかったので、今回は行を消さない")
    log(f"お客さまの記事集め：{res['boards']} 版面を書いた・新しい記事 {res['found']} 件"
        + (f"・時間切れ {late_n}（次の回へ）" if late_n else "") + (f"・失敗 {res['failed']}" if res["failed"] else "")
        + (f"・書けなかった行 {res['bad']}" if res["bad"] else "")
        + (f"・消した行 {res['deleted']}" if res["deleted"] else "") + f"・{time.monotonic() - started:.0f} 秒")
    return res


def main():
    import livestatus
    # 本物のブラウザ（images._browser_html）は使わない：1 頁 45 秒と重く、開いた記事の網址を Actions のログ（公開）に書くので
    # （お客さまの選んだものが分かる）。ふつうの取り直し（Fetcher）までで写真を探す
    os.environ.pop("SCRAPLING_BROWSER", None)
    lines = livestatus.Lines("userfeed")   # 管理ページの「ライブログ」にも同じ行を流す（店長が止まっているのに気づけるように）

    def log(msg):
        print(msg)
        lines.add(msg)
    try:
        run(dry_run="--dry-run" in sys.argv, log=log)
    except Exception as err:  # noqa: BLE001  店長の収集・出刊はもう終わっている。失敗しても止めない（次の回にもう一度）
        print(f"::warning::お客さまの記事集めに失敗：{_why(err)}", file=sys.stderr)
        lines.add(f"お客さまの記事集め [失敗]：{_why(err)}")
    finally:
        lines.close()


if __name__ == "__main__":
    main()
