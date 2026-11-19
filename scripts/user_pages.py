"""お客さま一人ひとりのページを、店長のページと同じ部品（render.render）で作る（2026-10-24，用户定的：
「框架（頭条・黄色の帯・版面の設計・主題・配色・小元素）は店長と同じ、中身は本人のもの」）。

- 版面 = 本人が追いかけているもの（ライブラリの follows：置く板块・小分類・篇幅・並び）。
  follows にまだないもの（足したばかりで library.py --users の回の前）は app_users.prefs.picks から（板块だけ）。
  どれを出すかは picks が決める（picks から外したものは follows に行が残っていても出さない）。
  - 店長と同じ名前の版面：店長の設定（主題・配色・小元素・アイコン）と店長の記事（AI 編集済みの最新号）をそのまま使う。
  - 店長にないもの：本人の分として集めた記事（user_boards）で、種類から主題（render.template_for）、写真から配色（theme.resolve）。
    写真は images.pick（店長と同じ規則）で記事から探す（1 版面の頭の数本だけ・全体の時間に上限）。
- 頭条・ほかの注目ニュース・目次は render がそのまま作る（本人の版面の記事から）。
- できたページは Supabase Storage の非公開の箱 pages/<account>/index.html（本人と店長だけが読める、db/user_pages.sql）。
  網页（render.AUTH_JS）は /home/ でログインした本人の分を読み込んで替える。

    python scripts/user_pages.py            # Actions（SUPABASE_SERVICE_KEY）：全員分を作って置く
    python scripts/user_pages.py --local D  # 手元：ネットの Supabase なし、D/<account>.html に書く（テスト用のデータを渡す）
    python scripts/user_pages.py --boards-file F --emblem-only   # 新しい版面の速い道（library_emblem.pages_runner）：小元素が足されただけの作り直し

--emblem-only（2026-11-19 店長「新しい版面を足したら小元素が出るまで 5 分未満」。前は 1 人分 92 秒）：記事は前の作り直しと同じなので、
網に聞く物は前の回の結果（pages/_fp/all.json の _og・_bands・_up_pick・_res・_open）を使う：記事の代表の写真（og_image）・記事の写真探し
（find_images：images.pick）・「気になるかも？」の Google の跳转の戻し（resolve_url）は前の結果だけ（網に出ない。前の結果に無い写真なしの記事が
1 本でもあれば、その人はふつうに作る）、写真の余白と主役（photo_bands）は無い分だけ 1 束まで（ONLY_NEW_PHOTOS）、頭の写真が開くか（photo_opens）は
無い網址だけ聞く。前の結果は前のページを作った回が残したものなので、
ページは前と同じ写真・記事に小元素が足されたもの（手元の測り：同じ入力で HTML が一致・1 人分 56 秒 → 10 秒）。無い分は次のふつうの作り直しが測る。
置く前に指紋を読み直し、作っている間にほかの回がこの人のページを置いていたら置かない（その回のほうが新しい記事・測りを持ち、小元素も design_moved で入っている）。
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zoneinfo

import digest
import heat
import og_image
import photo_bands
import photo_store
import render
import sbstate
import sources
import taxonomy
import theme

ROOT = pathlib.Path(__file__).resolve().parent.parent
TYPE_OF_SEC = {"游戏": "game", "影视": "anime", "演出": "event", "运动": "category", "好物": "product",
               "生活": "category", "出行": "category", "其他": "category"}
IMG_PER_BOARD = 3        # 1 版面で写真を探す記事の数（頭から）
IMG_BUDGET_S = 240       # 1 回の写真探しの合計時間（秒）
OG_BUDGET_S = 180        # 1 回の og_image.fill（記事のページを新しく読む）の合計時間（秒）。全員で分ける・残りは次の回（読み直しは覚えで減る）
STORIES_PER_BOARD = 8
BOARD_DESIGN = ("emblem", "theme", "motif", "like_fx")   # ライブラリの版面の共有のデザイン（boards.config、library_emblem.py が規則で作る）
FIRST_BOARD = render.SETTINGS_JA["first_board"]   # 版面が 0 個の人のページに置く静かな版面の名前（文字は表）
ADD_URL = "../?add"       # 追いかけるものを足す流れ（入口と同じ、render.AUTH_JS の ADD）


def account_of(email):
    """Supabase の private.user_account と同じ式（'u_' + md5(小文字のメール) 16 字）。"""
    return "u_" + hashlib.md5(str(email or "").strip().lower().encode()).hexdigest()[:16]


def norm(s):
    return digest.re.sub(r"\s+", "", str(s or "")).lower()


def own_picks(follows, picks, sizes=None):
    """いま追いかけているもの = picks（本物。設定の「外す」・カードで足すはここを書き換える）。
    follows（[{pos, section, subs, size, boards: {name}}]）は置き方だけ：picks にある名前の行を並び順に、そのあとに follows にまだない picks。
    picks から外した名前の follows は残っていても使わない（follows を消す仕組みはないので、外したらすぐ消えるように）。
    返す形は picks と同じ [{name, sec, subs, size}]（subs は follows にあるときだけ）。
    size（篇幅）= follows.size、なければ設定ページで選んだ prefs.sizes（follows にまだない版面の分、db/my_layout.sql）。"""
    sizes = {norm(k): v for k, v in (sizes or {}).items() if v in ("S", "M", "L")}
    want = {norm(p.get("name")) for p in picks or [] if str(p.get("name") or "").strip()}
    added = {norm(p.get("name")): p["added_at"] for p in picks or [] if isinstance(p, dict) and p.get("added_at")}   # 足した時刻（記事 5 本まで待つ held）
    out, seen = [], set()
    for f in sorted(follows or [], key=lambda f: f.get("pos") or 0):
        name = str(((f.get("boards") or {}).get("name")) or "").strip()
        if name and norm(name) in want and norm(name) not in seen:
            seen.add(norm(name))
            cfg = (f.get("boards") or {}).get("config") or {}
            out.append({"name": name, "sec": f.get("section") or "", "subs": f.get("subs") or {},
                        "size": f.get("size") or sizes.get(norm(name)),
                        "design": {k: cfg[k] for k in BOARD_DESIGN if cfg.get(k)}})
            if added.get(norm(name)):
                out[-1]["added_at"] = added[norm(name)]
    for p in picks or []:
        if norm(p.get("name")) not in seen:
            out.append({**p, "size": sizes.get(norm(p.get("name")))} if sizes.get(norm(p.get("name"))) else p)
    return out


def own_schemes(chosen):
    """板块ごとの分け方 {板块: id}：本人が設定ページで選んだもの（nav_schemes の本人の行）、候補にない・選んでいない板块は 1 つ目。
    店長の digest.load_nav_schemes と同じ決め方。"""
    out = {}
    for sec, schemes in taxonomy.sub_schemes().items():
        ids = [x.get("id") for x in schemes or [] if isinstance(x, dict) and x.get("id")]
        if ids:
            out[sec] = (chosen or {}).get(sec) if (chosen or {}).get(sec) in ids else ids[0]
    return out


def own_sub(item, schemes=None):
    """目次の小分類：その板块で本人が選んだ分け方（選んでいなければ 1 つ目。店長の既定と同じ）。"""
    return digest.sub_of(item, (schemes or own_schemes({})).get(item.get("section")))


def settings_page(prefs, items, schemes, settings, updated):
    """本人の設定ページ（店長と同じ render.render_settings、own の形：日本語・本人の分だけ書く）。"""
    rows = [{"name": i["name"], "section": i.get("section") or "其他", "subtitle": i.get("subtitle", ""), "size": i.get("size") or "M",
             "fields": {"section": i.get("section") or "其他"}} for i in items]
    srows = []
    for sec, opts in taxonomy.sub_schemes().items():
        ins = [i for i in items if i.get("section") == sec]
        good = [x for x in opts or [] if isinstance(x, dict) and x.get("id")]
        if not ins or not good:
            continue
        o = []
        for x in good:
            groups = {}
            for i in ins:
                g = digest.sub_of(i, x["id"]) or render.SETTINGS_JA["other"]
                groups[g] = groups.get(g, 0) + 1
            o.append({"id": x["id"], "label": x.get("label") or x["id"], "groups": list(groups.items())})
        srows.append({"section": sec, "chosen": schemes.get(sec, o[0]["id"]), "options": o})
    picks = [{"name": p["name"], "sec": p.get("sec") or "其他"} for p in (prefs or {}).get("picks") or [] if p.get("name")]
    return render.render_settings(rows, {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}, updated, srows,
                                  {"picks": picks, "add": ADD_URL})


def user_items(picks, shop_items):
    """本人の版面（items.yaml と同じ形）。店長と同じ名前なら店長の設定を写す（板块は本人の選んだもの）。"""
    shop = {norm(i["name"]): i for i in shop_items}
    out, seen = [], set()
    for p in picks or []:
        name = str(p.get("name") or "").strip()
        if not name or norm(name) in seen:
            continue
        seen.add(norm(name))
        sec = taxonomy.canonical(p.get("sec") or "") if p.get("sec") else ""
        if norm(name) in shop:
            it = {k: v for k, v in shop[norm(name)].items() if k not in ("parent",)}
            if sec:
                it["section"] = sec
            if p.get("subs"):   # 本人の置き方（follows）が店長の小分類より先
                it["subs"] = dict(p["subs"])
            it["_shop"] = True
        else:
            it = {"name": name, "type": TYPE_OF_SEC.get(sec, "category"), "section": sec or taxonomy.classify(name),
                  "keywords": [name], "match": [name], "subs": dict(p.get("subs") or {}),
                  "notes": render.WEB_ITEM_MARK,   # motif がまだない版面も、種類からの仮の主題を使う（render.template_for）。素の箱にしない
                  **(p.get("design") or {})}
        if p.get("size") in ("S", "M", "L"):
            it["size"] = p["size"]
        if p.get("added_at") and not it.get("_shop"):
            it["_added"] = p["added_at"]
        out.append(it)
    return out


def _story(row, weight):
    return {"headline": row.get("title") or "", "url": row.get("url") or "", "image": row.get("image") or None,
            "date": str(row.get("date") or "")[:10], "blurb": row.get("summary") or "", "highlight": "", "weight": weight,
            "source": row.get("source") or "", **({"img_ref": row["img_ref"]} if row.get("img_ref") else {}),
            **({"_wait": True} if row.get("_wait") else {})}


FIND = {"tried": 0, "found": 0, "saved": 0}   # find_images の数（1 回分。main が 1 行に出す：数だけ）
FIND_MEMO = None   # main が og_image の覚え（_fp/all.json の _og）を渡す：取れた写真を覚え、次の回の og_image.fill が記事に書き戻す


PICK_RETRY_S = og_image.FIRST_RETRY_H * 3600   # 見つからなかった記事の 1 回目の試し直しまで（2 回目からは理由ごと：og_image.RETRY_H。決めは og_image.retry_due の 1 か所）


def find_images(stories, deadline, cache=None, new=True, now=None, need=None):
    """写真のない記事に、店長と同じ規則（images.pick）で写真を探す。時間の上限を超えたらやめる。
    og_image.demote のあとなので、ここに来るのは写真が 1 枚も無い版面の頭だけ（最後の手）。SAVED（本站に保存しないと開けない）は使わない。
    防盗链の写真の置き場待ち（_wait）は探し直さない。
    cache = {記事の網址: {"img": 写真の網址 か ""（見つからなかった）, "at": 探した時刻（UNIX 秒）, "why"・"n"（見つからなかった理由と回数）}}：
    前の回に探した結果（pages/_fp/all.json の _up_pick）。見つかった写真はいつも使う。見つからなかった記事は、ふつうの回（new=True）は
    og の覚えと同じ間（og_image.retry_due：1 回目のあと 3 時間・断られた／時間切れ 1 日・写真が無い 3 日・消えた 7 日）をあけて探し直す
    （images.pick は断られても 20 秒で止まっても None を返すので、「無い」を永久に信じない）。new=False（--emblem-only）は前の結果だけ（網に出ない）。
    need（list）：new=False で前の結果に無く探さなかった記事の網址を足す（呼び側がその人だけふつうに作り直す）。"""
    import images
    now = now or time.time()
    now_dt = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    # 本物のブラウザ（images._browser_html）は開いた記事の網址を公開の Actions ログに書く。library_emblem.yml は小元素のために
    # SCRAPLING_BROWSER=1 を立てたまま user_pages を回すので、お客さまの記事ではここで切る（userfeed と同じ）
    os.environ.pop("SCRAPLING_BROWSER", None)
    used = set()
    for s in stories[:IMG_PER_BOARD]:
        if s.get("image") or s.get("_wait"):   # _wait：防盗链の写真の置き場待ち（探し直しても SAVED を捨てるだけ）
            continue
        got = (cache or {}).get(s.get("url"))
        got = got if isinstance(got, dict) else None
        if got and (got.get("img") or not new or not og_image.retry_due(got.get("at"), got.get("why") or "none", got.get("n") or 1, now_dt)):
            img = got.get("img") or None   # 見つかった写真・見つからなかったばかりの記事（ふつうの回は間をあけてから探し直す）
        elif not new or time.time() > deadline:
            if not new and need is not None and not got:
                need.append(s.get("url"))
            continue
        else:
            e = sources.Entry(title=s["headline"], url=s["url"], published=None, source=s.get("source", ""))
            FIND["tried"] += 1
            try:
                res = images.pick(None, [e], s["url"])
                img, why = res.image, None if res.image else og_image.why_of(res.reason)
                if img and images.SAVED in (res.source or ""):
                    FIND["saved"] += 1
                    img, why = None, "saved"
                if cache is not None and s.get("url"):
                    cache[s["url"]] = {"img": img or "", "at": int(now)} if img else \
                        {"img": "", "at": int(now), "why": why, "n": int((got or {}).get("n") or 0) + 1}
            except Exception:  # noqa: BLE001  写真がなくても版面は出す（読めなかったものは覚えない：次の回にまた探す）
                img = None
            if img:
                FIND["found"] += 1
                if FIND_MEMO is not None and s.get("url"):   # og の覚えにも：次のふつうの回の og_image.fill → write_back が記事に書き戻す
                    FIND_MEMO[s["url"]] = {"img": img, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if img and img not in used:
            s["image"] = img
            used.add(img)
    return stories


MIN_NEW_STORIES = 5      # 足したばかりの版面は記事がこの本数そろってから載せる（2026-11-19：3 本だけのページで頭条と版面が同じ記事になった）
NEW_HOLD_S = 6 * 3600    # 待つのは足してからこの間だけ。過ぎたら今ある分で載せる（記事の少ない題材がずっと「集めています」にならない）


def _ts(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def held(it, row, now=None):
    """本人だけの版面（店長の版面でない）で、足して NEW_HOLD_S 以内なのに集めた記事（AI 編集の記事＋整理待ち）が MIN_NEW_STORIES 本未満か。
    added_at（db/board_added.sql が picks に付ける）が無い前からの版面は待たない。"""
    at = _ts(it.get("_added"))
    if it.get("_shop") or at is None or (now or time.time()) - at >= NEW_HOLD_S:
        return False
    n = len(row.get("stories") or []) + (len(row.get("pending") or []) if row.get("edited") else 0)
    return n < MIN_NEW_STORIES


def user_issue(items, shop_issue, rows, deadline, themes, picks=None, new=True, need=None):
    """本人の 1 号分（render が読む形）。店長と同じ版面は店長の最新号の版面をそのまま、ほかは本人の記事から。"""
    shop_blocks = {b["name"]: b for b in (shop_issue or {}).get("items", [])}
    blocks = []
    for it in items:
        cap = digest.SIZE_STORIES.get(it.get("size") or "M", STORIES_PER_BOARD)   # 本人の篇幅（S 3・M 5・L 8、設定ページの約束）
        if it.get("_shop") and it["name"] in shop_blocks:
            sb = shop_blocks[it["name"]]
            blocks.append({**sb, "stories": (sb.get("stories") or [])[:cap], "section": it.get("section") or sb.get("section")})
            continue
        row = rows.get(norm(it["name"])) or {}
        if held(it, row):   # 足したばかりで記事がまだ MIN_NEW_STORIES 本未満：版面の場所だけ「集めています」で置き、記事は載せない
            blocks.append({"name": it["name"], "section": it.get("section"), "subtitle": "", "stories": [], "facts": [], "pending": [],
                           "cover": None, "theme": theme.resolve(it, None, themes), "quiet": True, "collecting": True,
                           "status": render.SETTINGS_JA["collecting"]})
            continue
        if row.get("edited"):   # AI 編集の記事（library.edited_stories：見出し・重さ・要約は AI のまま）
            st = [{k: v for k, v in s.items() if (not k.startswith("_") or k == "_wait") and k != "refs"} for s in (row.get("stories") or [])[:cap]]
        else:
            st = [_story(r, "hero" if i == 0 else "normal") for i, r in enumerate((row.get("stories") or [])[:cap])]
        st = find_images(st, deadline, picks, new, need=need)
        cover = next((s["image"] for s in st if s.get("image")), None)
        blocks.append({"name": it["name"], "section": it.get("section"), "subtitle": "", "stories": st, "facts": [],
                       "pending": row.get("pending") or [], "cover": cover, "theme": theme.resolve(it, cover, themes),
                       **({"edited": True} if row.get("edited") else {}),
                       **({} if st else {"quiet": True, "collecting": True,
                                         "status": render.SETTINGS_JA["collecting"]})})
    if not blocks:   # 版面が 0 個の人も同じ枠組み：静かな版面（主題・配色つき）で最初の 1 つを選ぶ道を出す（素の箱にしない）
        first = {"name": FIRST_BOARD, "type": "category", "section": "其他"}
        blocks.append({"name": FIRST_BOARD, "section": "其他", "subtitle": "", "stories": [], "facts": [], "pending": [], "cover": None,
                       "theme": theme.resolve(first, None, themes), "quiet": True, "start": ADD_URL,
                       "status": render.SETTINGS_JA["none_status"]})   # 道は主役のボタン 1 つだけ（ここに 2 つ目のリンクを置かない）
    date = (shop_issue or {}).get("date") or dt.date.today().isoformat()
    return {"date": date, "no": (shop_issue or {}).get("no", 0), "items": blocks}


def prev_issue(items, shop_issue):
    """前の号（店長の号）の、本人が追いかけている店長と同じ版面の分。店長のページが何号分を render に渡すのと同じに、本人のページも
    過去の号を渡す（「もっと見る」の過去のニュース・これからの予定は過去の号の記事から出る）。本人だけの版面は最新の号の分しかない。"""
    sb = {b["name"]: b for b in (shop_issue or {}).get("items", [])}
    blocks = [{**sb[i["name"]], "stories": (sb[i["name"]].get("stories") or [])[:digest.SIZE_STORIES.get(i.get("size") or "M", STORIES_PER_BOARD)],
               "section": i.get("section") or sb[i["name"]].get("section")} for i in items if i.get("_shop") and i["name"] in sb]
    return {"date": shop_issue["date"], "no": shop_issue.get("no", 0), "items": blocks} if blocks else None


def spare_entries(items, rows):
    """本人だけの版面（店長の収集にないもの）で、集めたのに版面に載らなかった記事（篇幅の分を超えた後ろ）。
    店長の「版面に載らなかった他のニュース」と同じ出どころ（digest.recommend の board）。"""
    out = []
    for it in items:
        if it.get("_shop"):
            continue
        cap = digest.SIZE_STORIES.get(it.get("size") or "M", STORIES_PER_BOARD)
        for r in ((rows.get(norm(it["name"])) or {}).get("stories") or [])[cap:]:
            day = str(r.get("date") or "")[:10] or dt.date.today().isoformat()
            if r.get("title") and r.get("url"):
                out.append(({"title": r["title"], "url": r["url"], "source": r.get("source") or "", "date": day,
                             "image": r.get("image") or "", "summary": r.get("summary") or ""}, day, it["name"]))
    return out


def own_recommend(votes, items, issue, rows=None, resolve=None):
    """「気になるかも？」と好みの言葉：店長と同じ digest.recommend を本人の票で回す（本人の版面に出ている記事は除く）。
    欲しい物はまだ本人の分がないので空。失敗してもページは出す（おすすめなしで）。"""
    try:
        stories = [s for b in issue["items"] for s in b.get("stories") or []]
        return digest.recommend(user={"votes": votes or [], "wishes": [], "works": {i["name"] for i in items if i.get("_shop")},
                                      "entries": spare_entries(items, rows or {}), "resolve": resolve,
                                      "on_page": ({s["url"] for s in stories}, [s["headline"] for s in stories])})
    except Exception as ex:  # noqa: BLE001
        print(f"::warning::own recommend failed ({type(ex).__name__})")
        return {"picks": [], "taste": []}


def photo_count(brows):
    """版面に載せる記事（AI 編集の記事・まだなら集めた記事。整理待ちは数えない）の数・写真あり・包みのまま（Google の網址）・置き場に入った。"""
    t = {"n": 0, "img": 0, "wrapped": 0, "stored": 0, "wait": 0}
    for r in (brows or {}).values():
        for s in r.get("stories") or []:
            u = s.get("image")
            t["n"] += 1
            t["wait"] += bool(s.get("_wait"))
            t["wrapped"] += "news.google.com" in str(s.get("url") or "")
            if u:
                t["img"] += 1
                t["stored"] += bool(photo_store.stored(u))
    return t


TALLY_KEYS = ("n", "img", "feed", "page", "demoted", "wrapped", "stored", "wait")


def photo_tally(brows, og, tally=None, fill=None, now=None, deadline=None, **kw):
    """写真を取る段の数（2026-11-19 店長「点検は、本物の写真が取れるかどうかを含めること」）。og_image.fill（残りの最後の手）と
    og_image.demote（それでも写真の無い記事は整理待ちへ）を、前と後で数えて tally に足す：
    n 版面の記事・img 写真あり（feed＝記事集めで付いていた／page＝ページ作りで付けた）・demoted 整理待ちへ回した・wrapped 包みのまま・
    wait 防盗链の写真の置き場待ち（mask_saved が写真を外した＝写真なしとして整理待ちへ回る）・
    stored 置き場に入った（n・img・wrapped は demote の前＝実際より良く見せない。stored は demote の後＝カードに残ったもの）。
    → og_image.fill の数（touched：写真を入れた記事）"""
    t = tally if tally is not None else {}
    for k in TALLY_KEYS:
        t.setdefault(k, 0)
    pre = photo_count(brows)
    got = (fill or og_image.fill)(brows, og, now=now, log=lambda _m: None, **({"deadline": deadline} if deadline is not None else {}), **kw)
    if not isinstance(got, dict):   # 差し替えた fill（試験）
        got = {"read": 0, "new": 0, "memo": 0, "wrapped": 0, "saved": 0, "why": {}, "touched": []}
    mid = photo_count(brows)
    k = og_image.demote(brows)
    post = photo_count(brows)
    t["n"] += mid["n"]
    t["img"] += mid["img"]
    t["feed"] += pre["img"]
    t["page"] += mid["img"] - pre["img"]
    t["demoted"] += k
    t["wrapped"] += mid["wrapped"]
    t["wait"] += mid["wait"]
    t["stored"] += post["stored"]
    return got


def tally_line(t):
    """photo_tally の 1 行（数だけ：名前・題・網址は出さない。Actions のログは公開）。"""
    return (f"お客さまの写真：記事 {t['n']} 本・写真あり {t['img']} 本（記事集めで {t['feed']}／ページ作りで {t['page']}）"
            f"・整理待ちへ回した {t['demoted']} 本・包みのまま {t['wrapped']} 本・防盗链の写真の置き場待ち {t.get('wait', 0)} 本・置き場に入った {t['stored']} 本")


def _eq(col, v):
    return f"{col}=is.null" if v in (None, "") else f"{col}=eq.{urllib.parse.quote(str(v), safe='')}"


def write_back(brows, latest, rows, og, touched, acct, put):
    """ページ作りで付けた写真（og_image の覚え）を記事に書き戻す（2026-11-19：前は表に出すだけで、次の回もまた探していた）。
    - ライブラリの版面（_src = bs）：board_stories のその日の行の pending（全員が同じもの）。stories（AI 編集）は書かない＝refs で引き継ぐ（inherit）。
    - 本人の user_boards の行：記事集め（userfeed.merge）は前の行の写真を残すので、ここに書けば次の記事集めでも消えない。
    どちらも読んだときの時刻（updated_at・checked_at）が変わっていない行だけ書く（記事集めが書いた後なら書かない＝新しい記事を消さない。次の回にまた付ける）。
    → [書いた版面, 書いた行, 書けなかった数]"""
    ids = {id(s) for s in touched or []}
    done = [0, 0, 0]

    def send(path, body):
        try:
            put(path, json.dumps(body, ensure_ascii=False).encode("utf-8"), "PATCH")
            return True
        except Exception:  # noqa: BLE001  書けなくても次の回に覚えからまた付ける
            done[2] += 1
            return False
    for bid in sorted({r["_src"][1] for r in (brows or {}).values() if isinstance(r, dict) and (r.get("_src") or ("",))[0] == "bs"}):
        bs = latest.get(bid) or {}
        pend = bs.get("pending") or []
        if og_image.apply(pend, og) or any(id(p) in ids for p in pend):
            if send(f"/rest/v1/board_stories?board_id=eq.{int(bid)}&day=eq.{bs.get('day')}&{_eq('updated_at', bs.get('updated_at'))}", {"pending": pend}):
                done[0] += 1
    for r in (rows or {}).values():
        st = r.get("stories") or []
        if not (r.get("item") and (og_image.apply(st, og) or any(id(s) in ids for s in st))):
            continue
        # 書く直前にその行を読み直し、覚えの写真だけを当てて書く（見直し 1：記事集めが今回探さなかった行の写真・原文の網址だけを直して書くときは
        # checked_at が前の値のままなので、読んだ時の写しで書くと記事集めの付けた写真・gurl・img_ref を古い写しで戻してしまう。隙は数秒に）
        path = f"/rest/v1/user_boards?account=eq.{urllib.parse.quote(acct, safe='')}&item=eq.{urllib.parse.quote(r['item'], safe='')}"
        try:
            fresh = put(path + "&select=stories,checked_at")
        except Exception:  # noqa: BLE001  読めなければ書かない（次の回に覚えからまた付ける）
            done[2] += 1
            continue
        fresh = fresh[0] if isinstance(fresh, list) and fresh and isinstance(fresh[0], dict) else None
        if not fresh or not og_image.apply(fresh.get("stories") or [], og):
            continue
        if send(path + f"&{_eq('checked_at', fresh.get('checked_at'))}", {"stories": fresh["stories"]}):
            done[1] += 1
    return done


def mask_saved(brows, want, pub=None):
    """防盗链の写真（記事に img_ref＝Referer の印がある：userfeed.Media が SAVED を取った。2026-11-19 店長の決定 1A）を画面に出す形にする。
    置き場（photo_store）に入ったものは置き場の網址（Pages の /p/<指紋>）に替える＝どの描き方でも元のサイトへ直に読みに行かない。
    まだのものは写真を外して _wait の印を付ける（読む人のブラウザでは 403 になる。写真なしとして og_image.demote が整理待ちへ回し、
    og_image.fill・find_images は探し直さない）。入った後の作り直しで本物に替わる。fill・demote の前に呼ぶ（見直し 2）。
    どちらも want（{指紋: [網址, Referer]}）に入れ、imgs.json で photo_store へ渡す（入ったものも：使っている印＝14 日で消さない）。
    → 写しの brows（記事集めの行・全員で共有の行は書き換えない。書き戻し write_back の後に呼ぶ）"""
    def fix(s):
        if not (isinstance(s, dict) and s.get("img_ref") and s.get("image")):
            return s
        u = s["image"]
        want[photo_store.key(u)] = [u, s["img_ref"]]
        got = photo_store.stored(u)
        if got and photo_store.pages_on() and photo_store.name(photo_store.key(u)) not in (pub or ()):
            got = None   # 見直し 6：置き場に入っても Pages に写るまでは /p/…-800.webp が 404（pub＝Pages の manifest に載った名前）
        return {k: v for k, v in s.items() if k != "img_ref"} | ({"image": got} if got else {"image": None, "_wait": True})
    out = {}
    for k, r in (brows or {}).items():
        if not isinstance(r, dict):
            out[k] = r
            continue
        out[k] = {**r, **{f: [fix(s) for s in r.get(f) or []] for f in ("stories", "pending") if f in r}}
    return out


def split_shop(brows, shop_items):
    """(店長と同じ名前でない版面, 店長と同じ名前の版面)。店長と同じ名前の版面は店長の号の版面をそのまま出す（user_issue）ので、
    写真の最後の手（og_image.fill の 180 秒）・書き戻し（店長の版面の board_stories.pending）・置き場待ちの印は外す（見直し 10）。"""
    shop = {norm(i.get("name")) for i in shop_items or []}
    own = {k: v for k, v in (brows or {}).items() if k not in shop}
    return own, {k: v for k, v in (brows or {}).items() if k in shop}


def merge_imgs(old, new, today=None, keep=None):
    """imgs.json（写真の置き場の列）を合わせる。1 つずつに最後に見た日 d を持つ {"u": 網址, "r": Referer（防盗链だけ）, "d": 日}。
    前の列（old）の分は、最後に見てから keep 日（photo_store.KEEP_DAYS）を過ぎたら外す（見直し 5：毎回失敗する人がいても列が縮み、
    photo_store が使わなくなった写真を消せる）。今回の分（new = {指紋: 網址 or [網址, Referer]}）は今日の日で入れる。
    前の形（文字列・[網址, Referer]）は日が無いので今日として扱う（そこから keep 日で外れる）。→ 指紋の順の list"""
    today = photo_store.day() if today is None else today
    keep = photo_store.KEEP_DAYS if keep is None else keep
    out = {}
    for x in old or []:
        e = photo_store.user_entry(x)
        if not e:
            continue
        d = x.get("d") if isinstance(x, dict) and isinstance(x.get("d"), int) else today
        if today - d <= keep:
            out[photo_store.key(e[0])] = {"u": e[0], **({"r": e[1]} if e[1] else {}), "d": d}
    for k, v in (new or {}).items():
        u, r = (v[0], v[1]) if isinstance(v, list) else (v, None)
        out[k] = {"u": u, **({"r": r} if r else {}), "d": today}
    return [out[k] for k in sorted(out)]


def _pics(*lists):
    """記事の網址（包みの網址 gurl も）→ (写真, 防盗链の Referer)。整理待ち・本人の user_boards の行から（AI 編集の記事へ引き継ぐ）。"""
    out = {}
    for st in lists:
        for p in st or []:
            if isinstance(p, dict) and p.get("image"):
                for u in (p.get("url"), p.get("gurl")):
                    if u:
                        out.setdefault(u, (p["image"], p.get("img_ref")))
    return out


def inherit(ed, *lists):
    """AI 編集の記事のうち写真の無いものに、refs の網址で整理待ち（記事集めが後から付けた写真）・本人の前の行の写真を引く（2026-11-19）。
    AI 編集は編んだ時点の refs の写真で固まる（library.edited_stories）ので、後から付いた写真が表に出なかった。編み直さない（token 0）。
    同じ版面で同じ写真は 2 回使わない。→ 写しの list（全員で共有の行は書き換えない）"""
    pics = _pics(*lists)
    used = {s.get("image") for s in ed if s.get("image")}
    out = []
    for s in ed:
        if not s.get("image"):
            hit = next((pics[u] for u in s.get("refs") or [s.get("url")] if pics.get(u) and pics[u][0] not in used), None)
            if hit:
                s = {**s, "image": hit[0], **({"img_ref": hit[1]} if hit[1] else {})}
                used.add(hit[0])
        out.append(s)
    return out


def board_rows(follows, latest, rows):
    """本人の版面の記事 {そろえた名前: {stories}}：ライブラリの board_stories（版面ごとに 1 回・全員が同じもの、library.md）が先。
    stories（AI 編集のあと）があればそれ、なければ pending（規則で集めたまま）。board_stories にまだ無い版面だけ古い user_boards の行（rows）。
    latest = {版面 id: board_stories のいちばん新しい日の行}。AI 編集の記事に写真が無ければ整理待ち・本人の行から引き継ぐ（inherit）。
    _src＝どの行から来たか（og_image が取った写真を書き戻す先：write_back）。"""
    out = {k: {**v, "_src": ("ub", k)} if isinstance(v, dict) else v for k, v in (rows or {}).items()}
    for f in follows or []:
        b = f.get("boards") or {}
        bs = latest.get(b.get("id")) or {}
        ed = [s for s in bs.get("stories") or [] if s.get("headline")]   # 題のない行＝AI 編集が全部見送った印（_fp だけ）
        if b.get("name") and (bs.get("stories") or bs.get("pending")):
            src = ("bs", b.get("id"))
            if bs.get("stories"):   # AI 編集のあと：記事は AI の、使わなかった新着は店長と同じ「整理待ち」へ（原文に戻した記事は前の網址 gurl でも当てる）
                used = {u for s in ed for u in s.get("refs") or [s.get("url")]}
                own = (rows or {}).get(norm(b["name"])) or {}
                out[norm(b["name"])] = {"stories": inherit(ed, bs.get("pending"), own.get("stories")), "edited": True, "_src": src,
                                        "pending": [p for p in bs.get("pending") or [] if p.get("url") not in used and p.get("gurl") not in used]}
            else:
                out[norm(b["name"])] = {"stories": bs["pending"], "edited": False, "_src": src}
    return out


def latest_stories(get):
    """board_stories の各版面のいちばん新しい日の行。収集は毎日その日の行を書く（library.put_stories）ので直近 READ_DAYS 日だけ読む
    （無料枠：14 日分を毎回読まない）。get = _supa と同じ形。"""
    since = (dt.date.today() - dt.timedelta(days=READ_DAYS)).isoformat()
    out = {}
    for r in get(f"/rest/v1/board_stories?day=gte.{since}&select=board_id,day,stories,pending,updated_at&order=day.desc") or []:
        cur = out.setdefault(r["board_id"], dict(r))
        if not cur.get("stories") and r.get("stories"):   # 今日まだ編んでいない版面は、前の日の AI 編集の記事（持ち越し。library.edit_todo と同じ）
            cur["stories"] = r["stories"]
    return out


READ_DAYS = 2
ONLY_NEW_PHOTOS = 16   # --emblem-only：前の結果に無い写真の余白と主役は 1 束（photo_bands の 16 本並び）まで。手元の測りで 1 枚 0.5 秒（400 枚 200 秒）＝ 16 枚 ≈ 8 秒
IMGS_PATH = "/storage/v1/object/pages/_fp/imgs.json"   # 写真の網址の一覧（非公開の箱・アカウントは持たない）


def build(email, prefs, rows, shop_items, shop_issue, settings, deadline, themes, follows=None, chosen=None, pages=None, heat_in=None, votes=None,
          shop_prev=(), pub=None, wishes=(), picks=None, new=True, resolve=None, need=None):
    """本人のページの HTML。follows = ライブラリの本人の行（あれば置き方はこちら）、chosen = 本人の nav_schemes {板块: id}。
    pages（dict）を渡すと、設定ページ（settings.html）もそこに入れる。picks・new は find_images の前の結果と「新しく探すか」、
    resolve は「気になるかも？」の Google の跳转を戻す関数（Memo。無ければ digest の既定）。"""
    items = user_items(own_picks(follows, (prefs or {}).get("picks"), (prefs or {}).get("sizes")), shop_items)
    issue = user_issue(items, shop_issue, rows, deadline, themes, picks, new, need)
    issues = [issue] + [p for p in (prev_issue(items, s) for s in shop_prev or ()) if p]   # 新しい順（店長のページと同じ並べ方）
    schemes = own_schemes(chosen)
    subs = {i["name"]: own_sub(i, schemes) for i in items}
    secs = list(render.SECTIONS)
    first = {}
    for n, i in enumerate(items):   # 板块 → 小分類（出てきた順）→ 本人の並び。店長の目次・本文と同じ並べ方
        first.setdefault((i.get("section"), subs[i["name"]]), n)
    items_o = sorted(enumerate(items), key=lambda x: (secs.index(x[1].get("section")) if x[1].get("section") in secs else len(secs),
                                                      first[(x[1].get("section"), subs[x[1]["name"]])], x[0]))
    order = [i["name"] for _, i in items_o] or [FIRST_BOARD]
    tz = digest.display_tz(settings)
    updated = dt.datetime.now(tz).strftime("%m.%d %H:%M")
    # 話題度（目次の「今日の最高」・版面の数字）も店長と同じ heat.compute：本人の版面の名前で、店長と同じ受信箱・出刊・外の信号から測る
    # （本人だけの版面は記事が薄く低く出る。同じ規則で測るだけ）。heat_in = (受信箱の files, 新しい順の出刊, 信号, 今日)
    heat_scores = {}
    if heat_in:
        heat_scores = heat.compute(items, heat_in[0], [issue] + heat_in[1], *heat_in[2:])   # 本人の号を先に：本人だけの版面の記事も数える（同じ記事は 1 回）
    rec = own_recommend(votes, items, issue, rows, resolve)
    render.PICKS_FLAG = render.SETTINGS_JA["picks_flag"]
    render.AUTH_DB = {"url": settings.get("supabase_url") or "", "key": settings.get("supabase_key") or ""}
    render.AUTH_ITEMS = [[i["name"], digest.section_of(i)] for i in shop_items if not i.get("parent")]
    motifs = {i["name"]: render.template_for(i) for i in items}
    if not items:   # 版面 0 個の「はじめに」も種類（category）から主題を持つ：お客さまも店長と同じ P5 の枠組み（素の版面にしない）
        motifs[FIRST_BOARD] = render.template_for({"type": "category", "notes": render.WEB_ITEM_MARK})
    wishes = [dict(w, added=str(w.get("added") or "")) for w in wishes or ()]   # 本人の欲しい物（db/wishes.sql）。トップの箱・目次の数・欲しい物のページが同じ行を読む
    html_ = render.render(issues, settings.get("nav_style", "line"), order, updated, wishes, digest.pack_batches(rec["picks"]),
                          {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")},
                          {i["name"]: i["size"] for i in items if i.get("size")},
                          motifs, themes, rec["taste"], heat_scores,
                          {i["name"]: (render.mark_own_emblems(i), i.get("emblem_ring", "accent")) for i in items if isinstance(i.get("emblem"), list)},
                          {i["name"]: i["like_fx"] for i in items if i.get("like_fx")}, {n: v for n, v in subs.items() if v},
                          settings.get("nav_hide", render.NAV_HIDE),
                          {i["name"]: i["icon"].get("image") for i in items if isinstance(i.get("icon"), dict)},
                          None, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), {}, {},
                          digest.lang.order(settings), {}, {})
    # 本人のページの印（AUTH_JS が「自分のページの中」と分かるように。もう一度読み替えない）
    mark = f'<head><meta name="wl-own" content="{render.e(email)}">'
    if pages is not None:
        pages["wishlist.html"] = render.render_wishlist(wishes, [], updated, (), {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}, own=True).replace("<head>", mark, 1)
        pages["settings.html"] = photo_store.emblems_to_pages(settings_page(prefs, items, schemes, settings, updated).replace("<head>", mark, 1), pub)
        if heat_in:   # 話題度のページも店長と同じ render_heat を本人の版面で（F5 2026-11-05、L13：「トップにまとまっています」の札で行き止まりにしない）
            analysis = heat.analyze(items, heat_in[0], [issue] + heat_in[1], *heat_in[2:])
            pages["heat.html"] = render.render_heat(analysis, render.collect(issues, order, digest.lang.order(settings)), updated).replace("<head>", mark, 1)
    return photo_store.emblems_to_pages(html_.replace("<head>", mark, 1), pub)


def _supa(path, data=None, method="GET", ctype="application/json"):
    settings, _ = digest.load_config()
    base, key = (settings.get("supabase_url") or "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not (base and key):
        raise SystemExit("SUPABASE_SERVICE_KEY がありません")
    h = {"apikey": key, "Content-Type": ctype}
    if key.startswith("eyJ"):
        h["Authorization"] = f"Bearer {key}"
    if method != "GET" and "/storage/" in path:
        h["Authorization"] = f"Bearer {key}"
        h["x-upsert"] = "true"
    if sbstate.LIMITED:
        raise sbstate.Limited(path)
    req = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        if err.code == 402:   # 無料枠超過：飛ばして終わる（落とさない。次の回が作り直す）
            sbstate.mark_limited(path.split("?")[0])
            raise sbstate.Limited(path) from None
        raise
    sbstate.mark_ok()
    return json.loads(body) if body.strip().startswith(("[", "{")) else body


def recent_adder(u, since):
    """picks に since（UNIX 秒）より後に足した名前（added_at）がある人か。"""
    return any(isinstance(p, dict) and (_ts(p.get("added_at")) or 0) >= since for p in ((u.get("prefs") or {}).get("picks") or []))


def pick_users(users, argv, get):
    """作り直す人を絞る（2026-11-19 新しい版面の速い道：全員分 4 分は待てない）。→ (人, 一部だけか)。
    --boards-file F：F の版面 id（JSON の list。library_emblem.py --fresh が書く）を追いかけている人だけ。
    --recent S：S 秒以内に版面を足した人だけ（board_added.yml の記事集めのあと）。どちらもなければ全員。"""
    users = list(users or [])
    if "--boards-file" in argv:
        try:
            ids = [int(x) for x in json.loads(pathlib.Path(argv[argv.index("--boards-file") + 1]).read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            ids = []
        accts = {r["account"] for r in (get(f"/rest/v1/follows?board_id=in.({','.join(map(str, ids))})&select=account") or [])} if ids else set()
        return [u for u in users if account_of(u.get("email")) in accts], True
    if "--recent" in argv:
        since = time.time() - float(argv[argv.index("--recent") + 1])
        return [u for u in users if recent_adder(u, since)], True
    return users, False


def _stamp(c):
    return json.dumps((c or {}).get("emblem_state"), sort_keys=True, default=str)


def emblem_stamps(follows):
    """follows の版面ごとの小元素の状態の印 {版面 id（字）: emblem_state}。置いたページの指紋と一緒に pages/_fp/all.json の <account>/_emb に残す。"""
    return {str((f.get("boards") or {}).get("id")): _stamp((f.get("boards") or {}).get("config")) for f in follows or [] if (f.get("boards") or {}).get("id")}


def design_moved(follows, get):
    """作り始めに読んだ follows の版面の小元素の状態（config.emblem_state：枚数 have・時刻 at）が、いまの DB と違うか。読めなければ False（そのまま置く）。
    小元素を書く回は必ず emblem_state も書く（library_emblem.fill_board）ので、これだけを読む（emblem の中身は読まない：読む量を増やさない）。"""
    stamp = _stamp
    old = {(f.get("boards") or {}).get("id"): stamp((f.get("boards") or {}).get("config")) for f in follows or [] if (f.get("boards") or {}).get("id")}
    if not old:
        return False
    try:
        now = get(f"/rest/v1/boards?id=in.({','.join(map(str, sorted(old)))})&select=id,emblem_state:config->emblem_state") or []
    except Exception:  # noqa: BLE001
        return False
    return any(stamp(r) != old.get(r.get("id")) for r in now if r.get("id") in old)


def _lap(marks, name, t0):
    """段の秒を覚える（ログ：名前は出さない。小元素だけの作り直しの内訳を本番で照らす。2026-11-19 の 92 秒は内訳が無かった）。"""
    marks.append(f"{name} {time.time() - t0:.1f}s")
    return time.time()


class Memo:
    """網に聞く答え（網址 → 答え）を前の回の分から使う。pages/_fp/all.json の 1 つの箱（_res：Google の跳转の戻し先・_open：頭の写真が開くか）。
    2026-11-19 手元の測り：1 人分の作り直しで「気になるかも？」の跳转を 38 本・頭の写真を 190 本、1 本ずつ網に聞いていた（断られると 1 本 6 秒）。
    new=False（--emblem-only）は前の答えだけ（無ければ ask の既定 miss を返し、網に出ない）。keep(答え) が真のものだけ覚える（戻せなかった跳转は覚えない）。
    続けて fails_max 回 keep に外れたら、この回は聞くのをやめる（userfeed の RESOLVE_FAILS と同じ考え）。used = この回に使った分（全員の回はこれだけ残す）。
    reuse=False は前の答えを使わず聞き直す（変わりうる答え＝写真が開くか。ふつうの作り直しは聞き直し、小元素だけの回が前の答えを使う）。"""

    def __init__(self, old, ask, new=True, keep=lambda u, v: True, miss=lambda u: u, fails_max=None, reuse=True):
        self.old, self.ask, self.new, self.keep, self.miss, self.fails_max = dict(old or {}), ask, new, keep, miss, fails_max
        self.used, self.fails, self.reuse, self.missed = {}, 0, reuse, 0   # missed：new=False で前の答えが無く聞かなかった数

    def __call__(self, u):
        if u in self.used:
            return self.used[u]
        if self.reuse and u in self.old:
            self.used[u] = self.old[u]
            return self.old[u]
        if not self.new:
            self.missed += 1
            return self.miss(u)
        if self.fails_max is not None and self.fails >= self.fails_max:
            return self.miss(u)
        v = self.ask(u)
        if self.keep(u, v):
            self.used[u] = v
            self.fails = 0
        else:
            self.fails += 1
        return v

    def box(self, partial):
        return {**self.old, **self.used} if partial else dict(self.used)


def _fresh_fps(fp_path):
    """置いたページの指紋を読み直す（読めなければ None）。"""
    try:
        got = _supa(fp_path)
        return got if isinstance(got, dict) else None
    except Exception:  # noqa: BLE001
        return None


def newer_page(fps, fp_path, acct):
    """この回が読んだあとに、ほかの回がこの人のページ（index.html）を置いたか（指紋が変わった）。読めなければ False（置く）。"""
    cur = _fresh_fps(fp_path)
    return cur is not None and cur.get(f"{acct}/index.html") != fps.get(f"{acct}/index.html")


def merge_fps(cur, old, mine, exact=()):
    """指紋の書き込み：いまの指紋（cur：ほかの回が書いたもの）に、この回が変えた分（old との差）だけを足す。
    _og・_bands・_up_pick などの測りは両方の和で、この回が変えた網址はこの回のもの（探し直して見つかった写真を前の「無い」で消さない）。
    exact の箱はこの回のまま（全員の回の _open・_res：使った分だけにして増え続けない）。cur が読めなければ mine のまま。"""
    if cur is None:
        return mine
    out = dict(cur)
    for k, v in mine.items():
        if k in exact:
            out[k] = v
        elif k.startswith("_") and isinstance(v, dict):
            o = old.get(k) or {}
            out[k] = {**v, **(cur.get(k) or {}), **{kk: vv for kk, vv in v.items() if o.get(kk) != vv}}
        elif v != old.get(k):
            out[k] = v
    return out


def main(argv):
    t_start = time.time()
    if argv[:1] != ["--local"]:
        render.OPENS = render.photo_opens   # 頭に選ぶ写真が開くか焼く時に見る（店長と同じ規則）
    settings, shop_items = digest.load_config()
    reports = sorted(digest.REPORTS_DIR.glob("????-??-??.json"))
    shop_issue = digest.load_json(reports[-1]) if reports else None
    themes = digest.load_json(digest.THEMES_FILE) or {}
    deadline = time.time() + IMG_BUDGET_S
    prev = [digest.load_json(p) for p in reversed(reports[-digest.ISSUES_ON_PAGE:-1])]   # 最新の号の前の号（新しい順）
    heat_in = (sorted(digest.INBOX_DIR.glob("????-??-??.json")), [digest.load_json(p) for p in reversed(reports[-14:])],
               digest.load_json(digest.HEAT_FILE) or {}, (shop_issue or {}).get("date") or dt.date.today().isoformat())
    if argv[:1] == ["--local"]:
        out = pathlib.Path(argv[1])
        data = json.loads(pathlib.Path(argv[2]).read_text(encoding="utf-8"))   # [{email, account, prefs, rows: [...]}]
        out.mkdir(parents=True, exist_ok=True)
        for u in data:
            rows = {norm(r["item"]): r for r in u.get("rows", [])}
            pages = {}
            (out / f"{u['account']}.html").write_text(build(u["email"], u["prefs"], rows, shop_items, shop_issue, settings, deadline, themes,
                                                            u.get("follows"), u.get("schemes"), pages, heat_in, u.get("votes"), prev), encoding="utf-8")
            for name, h in pages.items():
                (out / f"{u['account']}.{name}").write_text(h, encoding="utf-8")
        return
    try:
        users = _supa("/rest/v1/rpc/userfeed_users", json.dumps({"p_limit": 1000}).encode(), "POST")
    except sbstate.Limited:
        print("::warning::Supabase が 402（制限中）：お客さまのページ作りを飛ばす。制限が外れたら次の回が作る")
        return
    users, partial = pick_users(users, argv, _supa)
    only = "--emblem-only" in argv   # 小元素が足されただけ：前の測った結果だけで作る（網に出ない・模型を読まない・記事に書き戻さない・imgs.json を書かない）
    made = failed = skipped = kept = 0
    photos = {}   # 写真を取る段の数（photo_tally）
    ogt = {"read": 0, "new": 0, "memo": 0, "wrapped": 0, "saved": 0, "why": {}}   # og_image.fill の数（1 人ずつ足す）
    back = [0, 0, 0]   # 書き戻した 版面・行・書けなかった数
    # 本物のブラウザ（images._browser_html）は開いた記事の網址を公開のログに書く・state/browser_skip.json に網址を残す：お客さまの記事では使わない
    os.environ.pop("SCRAPLING_BROWSER", None)
    force = "--force" in argv
    fp_path = "/storage/v1/object/pages/_fp/all.json"   # 置いたページの指紋（全員で 1 つ。本人のページと同じ非公開の箱）
    try:
        fps = _supa(fp_path)
        fps = fps if isinstance(fps, dict) else {}
    except sbstate.Limited:
        return
    except Exception:  # noqa: BLE001  まだ無い・読めない → 全部置く
        fps = {}
    now_dt = dt.datetime.now(dt.timezone.utc)
    # 写真のない記事の代表の写真（og:image。og_image.py：取れた写真と、取れなかった理由・時刻）。指紋と同じ 1 本に入れる。
    # 外すのは書く直前に（merge_fps のあと）：ここで外しても、ほかの回の分と合わせると戻ってくる
    og = dict(fps.get("_og") or {})
    global FIND_MEMO
    FIND_MEMO = og if not only else None
    og_deadline = time.monotonic() + OG_BUDGET_S
    bands = dict(fps.get("_bands") or {})   # 写真に焼き込まれた余白の割合（網址ごと。photo_bands.py）。指紋と同じ 1 本に入れる（storage の読みを増やさない）
    # 記事の写真探し（find_images）の結果と時刻 {img, at, why?, n?}（og の覚えと鍵は分けるが、試し直しの間は同じ og_image.retry_due）。
    # 同じ 1 本に（--emblem-only が前の結果で同じ写真を付ける）
    picks = dict(fps.get("_up_pick") or {})
    # 網に聞く答えの前の回の分（Memo）。頭の写真が開くか：小元素だけの回も、前に無い網址は聞く（開かない写真を頭にしない）
    opens = Memo(fps.get("_open"), render.photo_opens, reuse=only) if render.OPENS else None
    if opens:
        render.OPENS = opens
    # 「気になるかも？」の Google の跳转の戻し先。ふつうの回は前の試し方のまま（sources.resolve_url の既定：3 回・失敗の数は持たない。
    # 1 回だけ・全員で失敗を数えると、4 本続けて断られた後の人は全員 Google の網址のままで票と合わなかった）。戻せた答えだけ覚え、小元素だけの回が使う
    res_memo = Memo(fps.get("_res"), lambda u: sources.resolve_url(u), new=not only, keep=lambda u, v: v != u)

    def res(u):   # 跳转でない網址はそのまま（覚えない・失敗に数えない）
        return res_memo(u) if "news.google.com" in str(u or "") else u
    try:
        latest = latest_stories(_supa)
    except sbstate.Limited:
        return
    except Exception as ex:  # noqa: BLE001  読めなければ前の user_boards だけで作る
        print(f"::warning::board_stories が読めなかった（{type(ex).__name__}）")
        latest = {}
    new_fps = dict(fps)
    pub = photo_store.published()   # Pages に載った写しの名前（外の小元素を /p/ に替えるのは載ったものだけ）
    imgs = {}   # 作ったページの原寸の写真の網址（置き場に未収のもの）。photo_store が読んでお客さまの写真も置き場に入れる
    saved = {}  # 防盗链の写真 {指紋: [網址, Referer]}（mask_saved。photo_store が Referer 付きで置き場へ）
    if partial:
        print(f"お客さまのページ：始めて {time.time() - t_start:.1f}s で {len(users or [])} 人分を作り始める{'（小元素だけ：前の測りで）' if only else ''}", flush=True)
    for u in users or []:
        acct = account_of(u["email"])
        lap, t0 = [], time.time()
        try:
            rows = _supa(f"/rest/v1/user_boards?account=eq.{acct}&select=item,sec,state,stories,checked_at")
            follows = _supa(f"/rest/v1/follows?account=eq.{acct}&select=pos,section,subs,size,boards(id,name,config)&order=pos")
            chosen = {r["section"]: r["scheme"] for r in _supa(f"/rest/v1/nav_schemes?account=eq.{acct}&select=section,scheme") or []}
            wishes = _supa(f"/rest/v1/wishes?account=eq.{acct}&select=id,name,status,price,currency,url,shop,note,specs,image,photo,added&order=id.desc") or []
            votes = digest.latest_votes(_supa(f"/rest/v1/feedback?account=eq.{acct}&select=url,vote,kind,title,work,because,hits,words,created_at&order=id.asc"))
            own = {norm(r["item"]): r for r in rows or []}
            t1 = _lap(lap, "読む", t0)
            # 小元素だけの回（--emblem-only）で前の結果が足りない人（一度もページを作っていない・前の回のあとに og の覚えに無い写真なしの記事が 1 本でもある）は、
            # 前のページより写真の少ないページを置かない：この人だけふつうの作り直し（5 分は割れても、ページを悪くしない方が先。秒はログに）。
            # 小元素だけの回の og は網に出ない（limit=0）＝その回の秒は前の結果だけで決まる（2026-11-19 見直し 2 回目：1 束読むと 1 人分が数十秒〜3 分）
            full = not only or not fps.get(f"{acct}/index.html") or \
                bool(og_image.missing(split_shop(board_rows(follows, latest, own), shop_items)[0], og))
            why = "" if not only or not full else "前の結果が足りない"

            def make(follows, full):
                """この人の 1 枚（と設定・欲しい物・話題度）を組んで測る。→ (html, pages, brows, 前の結果に無く探さなかった数, og_image.fill の数, 写真の数, 防盗链の写真)
                写真の段（2026-11-19 お客さまの写真）：AI 編集の記事は整理待ちの写真を引き継ぐ（board_rows）→ 店長と同じ名前の版面は外す（split_shop）→
                防盗链の写真は置き場に入ったものだけ出し、まだのものは写真なしに（mask_saved）→ 記事のページの代表の写真（og_image.fill：残りの最後の手）→
                それでも写真の無い記事は整理待ちへ（demote）。小元素だけの回は og を前の結果だけ（網に出ない・取れなかった記事の試し直しもしない）"""
                brows, shopb = split_shop(board_rows(follows, latest, own), shop_items)
                sv = {}
                brows = mask_saved(brows, sv, pub)
                tally = {}
                got = photo_tally(brows, og, tally, deadline=og_deadline, limit=None if full else 0, retry=full)
                brows = {**shopb, **brows}
                need = []
                res_memo.new, res_memo.missed = full, 0
                pg = {}
                h = build(u["email"], u.get("prefs") or {}, brows, shop_items, shop_issue,
                          settings, deadline, themes, follows, chosen, pg, heat_in, votes, prev, pub, wishes, picks, full, res, need)
                # 写真に焼き込まれた余白を測って data-t に書く（ブラウザは別のサイトの写真を読めないので、ここで測る。2026-11-08）。
                # 小元素だけの回は前の結果＋無い分を 1 束だけ。1 束より多ければ全部測る（前のページより悪くしない）
                urls = [x for t in [h, *pg.values()] for x in photo_bands.urls_in(t)]
                lack = sum(1 for x in dict.fromkeys(urls) if not isinstance(bands.get(x), dict))
                photo_bands.measure(urls, bands, photo_store.fetch, limit=ONLY_NEW_PHOTOS if not full and lack <= ONLY_NEW_PHOTOS else None)
                return (photo_bands.inject(h, bands), {k: photo_bands.inject(v, bands) for k, v in pg.items()}, brows,
                        len(need) + res_memo.missed, got, tally, sv)
            html_, pages, brows, miss, got, tally, sv = make(follows, full)
            if not full and miss:   # 前の回に無い記事の写真探し・跳转の戻しがある：この人だけふつうに作り直す
                full, why = True, "前の結果が足りない"
                html_, pages, brows, _, got, tally, sv = make(follows, True)
            t1 = _lap(lap, "組む・測る", t1)
            # 置く直前に、作っている間に小元素の回（board_added.yml の速い道）が config を書いていないか見る（2026-11-19 見直し：組んだ直後に見ると、
            # 写真の測りの間に書かれた小元素が抜けたページを置いていた）。書かれていれば今の config で作り直す（測りは前の結果で済む）
            if design_moved(follows, _supa):
                follows = _supa(f"/rest/v1/follows?account=eq.{acct}&select=pos,section,subs,size,boards(id,name,config)&order=pos")
                html_, pages, brows, _, got2, tally, sv = make(follows, full)
                og_image.add(ogt, got2)
                got["touched"] = got["touched"] + got2["touched"]
                t1 = _lap(lap, "小元素が書かれたので組み直し", t1)
            og_image.add(ogt, got)
            for k, v in tally.items():
                photos[k] = photos.get(k, 0) + v
            saved.update(sv)
            if not only:   # 取れた写真は記事に書き戻す（小元素だけの回は書かない：記事は前の回と同じ・DB に書かない）
                w = write_back(split_shop(brows, shop_items)[0], latest, split_shop(own, shop_items)[0], og, got["touched"], acct, _supa)
                back = [a + b for a, b in zip(back, w)]
            stamps = emblem_stamps(follows)   # このページに入った小元素の状態（版面ごと）。小元素だけの回が「先に置かれたページに入っているか」を見る
            photo_store.scan_text([html_, *pages.values()], set(), imgs)
            if only:
                cur = _fresh_fps(fp_path)
                if cur is not None and cur.get(f"{acct}/index.html") != fps.get(f"{acct}/index.html") and cur.get(f"{acct}/_emb") == stamps:
                    kept += 1   # 作っている間にほかの回がこの人のページを置き、そのページに同じ小元素が入っている：そちらが新しい
                    print(f"お客さまのページ：1 人分はほかの回が先に置いた（小元素も入っている・置かない）・{'・'.join(lap)}", flush=True)
                    continue
            if why:
                print(f"お客さまのページ：1 人分は{why}のでふつうに作った", flush=True)
            for name, h in {"index.html": html_, **pages}.items():
                fp = hashlib.sha1(h.encode("utf-8")).hexdigest()
                if not force and fps.get(f"{acct}/{name}") == fp:   # 変わっていないページは落とし直さない（無料枠・置き場の写しも守る）
                    skipped += 1
                    continue
                _supa(f"/storage/v1/object/pages/{urllib.parse.quote(acct)}/{name}", h.encode("utf-8"), "POST", "text/html; charset=utf-8")
                new_fps[f"{acct}/{name}"] = fp
            new_fps[f"{acct}/_emb"] = stamps
            made += 1
            _lap(lap, "置く", t1)
            if partial:
                print(f"お客さまのページ：1 人分 {time.time() - t0:.1f}s（{'・'.join(lap)}）", flush=True)
        except sbstate.Limited:
            print("::warning::Supabase が 402（制限中）：残りのお客さまのページ作りを飛ばす")
            return
        except Exception as ex:  # noqa: BLE001  1 人の失敗でほかの人を止めない。ログは数と種類だけ（名前・メールは出さない：Actions のログは公開）
            failed += 1
            print(f"::warning::1 人分のページを作れなかった（{type(ex).__name__}）")
    new_fps["_bands"] = bands
    new_fps["_og"] = og
    new_fps["_up_pick"] = picks
    if opens:
        new_fps["_open"] = opens.box(partial)   # 全員の回はこの回に使った分だけ（増え続けない）
    new_fps["_res"] = res_memo.box(partial)
    if new_fps != fps:
        # 作っている間にほかの回（小元素だけの回など）が書いた指紋・測りを消さない：読み直して、この回が変えた分だけ差し替える（全員の回も。
        # 前は全員の回が上書きして、置かれたページと記録の指紋が食い違い、次の回が「変わっていない」と置き直さなかった）。
        # 全員の回の _open・_res はこの回に使った分だけ（増え続けない）
        new_fps = merge_fps(_fresh_fps(fp_path), fps, new_fps, exact=() if partial else ("_open", "_res"))
        for box in ("_og", "_up_pick"):   # 覚えの古いもの（KEEP_DAYS より前）は合わせた後に外す（前に外すと、ほかの回の分と合わせて戻ってくる）
            if isinstance(new_fps.get(box), dict):
                og_image.prune(new_fps[box], now_dt)
        try:
            _supa(fp_path, json.dumps(new_fps, sort_keys=True).encode(), "POST", "application/json")
        except Exception:  # noqa: BLE001  指紋が書けなくても次の回が全部置き直すだけ
            pass
    # 写真の置き場の列（pages/_fp/imgs.json・非公開の箱。pages/ は読まず、この 1 本だけを photo_store が読む）：
    # 全員作れた回は今回の分で置き換える（使わなくなった写真を外す）。一部の人だけの回（--boards-file／--recent）・一部が失敗した回は、
    # 前の列を読んで今回の分を足すだけ（ほかの人の網址を消さない。2026-11-19：足したばかりの人の写真が次の全員の回まで置き場に入らなかった）。
    # 1 つずつに最後に見た日を持ち、一部の回は前の列の 14 日を過ぎた分を外す（merge_imgs）。全員作れた回は空でも [] を書く（古い列を残さない）。
    # 小元素だけの回（--emblem-only）は書かない（写真は前の回と同じ）
    cur = {photo_store.key(u): u for u in imgs.values()} | saved
    if made and not only and (cur or not (partial or failed)):
        try:
            if partial or failed:
                old = _supa(IMGS_PATH)
                body = merge_imgs(old if isinstance(old, list) else [], cur)
            else:
                body = merge_imgs([], cur)
            _supa(IMGS_PATH, json.dumps(body).encode("utf-8"), "POST", "application/json")
        except sbstate.Limited:
            pass
        except Exception:  # noqa: BLE001  書けなくても次の回が書く（前の列が読めない回は書かない＝消さない）
            pass
    print(f"お客さまのページ：{made} 人分を作って置いた（変わらず飛ばしたファイル {skipped}・ほかの回が先に置いた {kept}）・失敗 {failed}・{time.time() - t_start:.1f}s")
    # 数だけ（名前・網址は出さない：公開のログ）
    print(og_image.log_line(ogt, back))
    print(f"版面の頭の写真探し（写真が 1 枚も無い版面・images.pick）：{FIND['tried']} 本を探し、{FIND['found']} 本に付けた" + (f"・SAVED で捨てた {FIND['saved']}" if FIND["saved"] else ""))
    if photos:
        print(tally_line(photos))
    if failed and not made:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
