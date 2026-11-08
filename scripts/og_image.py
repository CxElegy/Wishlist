"""写真のない記事に、記事のページの代表の写真（og:image）を付ける（2026-11-08，店長：「只有文字的新闻也不好 我一定要图」）。

お客さまのページを作るとき（user_pages.py）、写真の網址を持たない記事だけ、記事のページを 1 回読んで
<meta property="og:image">（なければ twitter:image）を取る。結果は網址ごとに残し（cache）、同じ記事は二度読まない。
"""
import concurrent.futures as cf
import html as htmllib
import re
import urllib.parse
import urllib.request

import nostorage  # noqa: F401  公開の箱を落とさない止め（全部の網の道）

MAX_NEW = 150
MAX_BYTES = 400_000
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
META = re.compile(r'<meta\b[^>]*>', re.I)
ATTR = re.compile(r'([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')


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


def fetch_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "ja,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=10) as r:
        if "html" not in (r.headers.get("Content-Type") or ""):
            return ""
        return r.read(MAX_BYTES).decode(r.headers.get_content_charset() or "utf-8", "replace")


def fill(rows, cache, fetch=fetch_page, log=print):
    """rows = {版面: {"stories": [...], "pending": [...]}}。写真のない記事に image を入れる。→ 新しく読んだ数"""
    lack = [s for r in (rows or {}).values() for k in ("stories", "pending") for s in r.get(k) or []
            if isinstance(s, dict) and not s.get("image") and str(s.get("url") or "").startswith("http")]
    todo = [u for u in dict.fromkeys(s["url"] for s in lack) if u not in cache][:MAX_NEW]

    def one(u):
        try:
            return u, find(fetch(u), u) or ""
        except Exception:  # noqa: BLE001  読めないページは「写真なし」として次から読まない
            return u, ""
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for u, v in ex.map(one, todo):
            cache[u] = v
    n = 0
    for s in lack:
        if cache.get(s["url"]):
            s["image"] = cache[s["url"]]
            n += 1
    if todo or n:
        log(f"記事の代表の写真：{len(todo)} 件を読み、{n} 件に写真を付けた")
    return len(todo)


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
