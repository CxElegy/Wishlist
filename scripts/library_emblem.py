"""ライブラリの版面の小元素（2026-10-24，用户定的：お客さまの版面にもエンブレム）。

店長と同じ規則（emblem_fill.fill_one：集める → 確かめる → 選ぶ → 切り抜く）を、ライブラリの版面ごとに 1 回。
- 対象：だれかが追いかけていて、店長の版面ではないもの（店長の版面は items.yaml の小元素をそのまま使う）。
- 種類（emblem_kind）は板块・小分類・Wikidata の「人」（P31 = Q5）から規則で（kind_for）。記事の名前は Wikidata の各言語の記事。
- emblem_fill は items.yaml と docs/emblems を前提に作ってあるので、版面 1 つだけの items.yaml を一時の場所に作って走らせる（sandbox）。
- 切り抜いた画像は Supabase Storage の公開の箱 emblems/<Wikidata の番号か b+版面の id>-<中身の指紋>.webp（名前は出さない。db/emblems.sql）。
  同じ版面は全員で 1 枚を共有。結果は boards.config の emblem・theme・emblem_*（手がかり）、進み具合は config.emblem_state。
- Actions のログは公開：版面の名前は出さず、数だけ。

    python scripts/library_emblem.py --minutes 25     # library_emblem.yml（SUPABASE_SERVICE_KEY）
"""
import contextlib
import hashlib
import io
import json
import pathlib
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

BUCKET = "emblems"
RETRY_HOURS = 24      # 届かなかった版面をもう一度試すまで（店長の版面と違い、材料の指紋がないので 1 日おき）
RULES = 8             # 取り方の規則の版。上げると、全部の版面（済みも）を RETRY_HOURS を待たずに作り直す（2：Wikidata から AniList・Fandom の名簿、3：題材の記号、
                      # 4：分類の続き・参照 500 超え・Playable Characters・字だけ／図／古い写真を外す、5：Commons のロゴはロゴのファイルで名前だけのもの、6：作り直しでキャラも前の小元素を残さない・名簿にまとめ／Player／別の作品の姿を入れない・同じ画像は 1 枚。ロゴのない製品の P18 は版を上げない：届かなかった版面だけの話で 24 時間後に取り直す、
                      # 7：頭のてっぺんが上の端で切れた絵〔上 3px に 20%〕・小さい顔〔80px 未満〕・ぼやけた写真を使わない＝emblem.check_whole），
                      # 8：グループの版面は Wikidata のメンバーを emblem_who に〔#428。7 で届かなかった YOASOBI・Mrs. GREEN APPLE・BTS は 24 時間待たず作り直す〕
REDO = ("emblem", "emblem_who", "emblem_pool", "emblem_category")   # 前の版の規則で作ったもの：版が上がったら捨てて規則から作り直す（emblem_reject・emblem_fandom は残す）
PER_BOARD_S = 300     # 1 版面の目安（これより残りが少なければ次を始めない）
KEEP = ("name", "wikidata", "type", "keywords", "emblem_kind", "wiki")   # 毎回 規則と Wikidata から作るので config に書かない


def kind_for(section, subs, human=False):
    """版面の種類 → 小元素の種類（emblem_fill.RULES）。店長の items.yaml の emblem_kind と同じ考え方を規則で。"""
    subs = subs or {}
    if subs.get("form") == "グループ":
        return "group"
    if human or (section == "演出" and subs.get("form") == "ソロ"):
        return "person"
    if section in ("游戏", "影视"):
        return "character"
    if section == "好物":
        return "brand"
    return "topic"


# 題材の版面の記号（Twemoji）：名前・小分類の言葉 → 記号。店長の題材が手で持つ emblem_icon（滑雪 26f7 1f3c2 1f3bf）を規則で。
# 当たらなければ板块の記号（sections.yaml の icon）。0 枚の版面を作らない最後の砦（代表作・ロゴ・Wikidata の画像が先）
ICONS = [(r"日本代表", "1f1ef-1f1f5"), (r"サッカー|soccer|football", "26bd"), (r"野球|baseball", "26be"), (r"バスケ|NBA|basketball", "1f3c0"),
         (r"テニス|tennis", "1f3be"), (r"モータースポーツ|F1|レース", "1f3ce"), (r"格闘技|相撲|ボクシング", "1f94b"),
         (r"将棋|囲碁|チェス|chess", "265f"), (r"宇宙|space", "1f30c"), (r"ロケット|rocket", "1f680"), (r"台風|typhoon", "1f300"),
         (r"天気|weather", "26c5"), (r"美術館|展覧会|アート|art\b", "1f5bc"), (r"博物館|museum", "1f3db"), (r"テーマパーク", "1f3a2"),
         (r"温泉|宿", "2668"), (r"旅行|観光|travel", "1f5fa"), (r"アウトドア|キャンプ", "26fa"), (r"ラーメン", "1f35c"),
         (r"グルメ|料理|food", "1f37d"), (r"健康", "1f3c3"), (r"インテリア", "1f6cb")]


def icons_for(name, section, subs):
    """題材の版面 → emblem_icon（空白区切りの Twemoji の番号、最大 3）。名前の言葉 → 小分類の言葉、どちらも当たらなければ板块の記号。"""
    import taxonomy
    out = []
    for text in [name, *(subs or {}).values()]:
        out += [c for rx, c in ICONS if re.search(rx, str(text), re.I) and c not in out]
    icon = (taxonomy.SECTIONS.get(section) or {}).get("icon")
    if icon and not out:   # 言葉に当たらないときだけ（其他の 📦 を将棋に足さない）
        out.append(str(icon))
    return " ".join(out[:3])


def _claims(ent, prop):
    """Wikidata の項目の 1 つの性質の値（番号の項目は Q…、文字は そのまま）。"""
    out = []
    for c in (ent.get("claims") or {}).get(prop) or []:
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        out.append(v.get("id") if isinstance(v, dict) else v)
    return [v for v in out if v]


def _fandom(ent):
    """Fandom の wiki の番号（P4073）のうち言語の前置きのないもの（pokemon。de.pokemon は飛ばす）。"""
    return next((v for v in _claims(ent, "P4073") if "." not in str(v)), None)


def wd_entity(qid, get=None):
    """Wikidata → {human: 人か, links: {lang: 記事名}, anilist: AniList の番号, fandom: Fandom の wiki}。番号がなければ {}。
    名簿の手がかり（店長の版面は手で持つ anilist_id・emblem_fandom）を規則で：AniList はアニメ（P8729）→ 漫画（P8731）、
    Fandom は項目の P4073 → なければシリーズ（P179：スプラトゥーン3 → Splatoon）の P4073。断られたら library.WdBlocked（その版面は次の回に）。"""
    if not qid:
        return {}
    import library
    get = get or library._wd_get

    def ent_of(q):
        return ((get({"action": "wbgetentities", "ids": q, "props": "claims|sitelinks"}).get("entities") or {}).get(q) or {})
    ent = ent_of(qid)
    links = {k[:-4]: v.get("title") for k, v in (ent.get("sitelinks") or {}).items()
             if re.fullmatch(r"(en|ja|zh|ko)wiki", k) and v.get("title")}
    fandom = _fandom(ent)
    for s in _claims(ent, "P179")[:1] if not fandom else []:
        fandom = _fandom(ent_of(s))
    anilist = next(iter(_claims(ent, "P8729") + _claims(ent, "P8731")), None)
    ids = _claims(ent, "P674")[:40]   # 登場人物：分類が本当にこの作品のキャラか確かめる（GTA 6 の wiki の「Playable characters」は GTA IV・V の主役だった）
    labs = (get({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels", "languages": "en"}).get("entities") or {}) if ids else {}
    leads = [((labs.get(q) or {}).get("labels") or {}).get("en", {}).get("value") for q in ids]
    return {"human": "Q5" in _claims(ent, "P31"), "links": links, "anilist": anilist, "fandom": fandom, "leads": [x for x in leads if x]}


MEMBERS_MAX = 12   # グループのメンバーとして集める人数の上限（店長の ILLIT 5・A2O LITE 9 と同じ規模）


def group_members(qid, get=None, limit=MEMBERS_MAX):
    """グループの Wikidata の番号 → メンバーの名前（emblem_who）。店長のグループは emblem_who を手で書くが、ライブラリの版面にはなく、
    グループの写真は「何人も写っている」で落ちて 0 枚だった（BTS・YOASOBI・Mrs. GREEN APPLE）。
    グループの has part（P527）＋ member of（P463）がそのグループの人（P31 = 人 Q5）を、英語（なければ日本語）の名前で。断られたら []（次の回）。"""
    import library
    get = get or library._wd_get
    try:
        ent = (get({"action": "wbgetentities", "ids": qid, "props": "claims"}).get("entities") or {}).get(qid) or {}
        ids = [v for v in _claims(ent, "P527") if re.fullmatch(r"Q\d+", str(v))]
        found = get({"action": "query", "list": "search", "srsearch": f"haswbstatement:P463={qid}", "srlimit": 30}).get("query", {}).get("search") or []
        ids += [x["title"] for x in found if re.fullmatch(r"Q\d+", str(x.get("title")))]
        ids = list(dict.fromkeys(ids))[:50]
        if not ids:
            return []
        ents = get({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|claims", "languages": "en|ja"}).get("entities") or {}
    except library.WdBlocked:
        return []
    out = []
    for q in ids:
        e = ents.get(q) or {}
        if "Q5" not in _claims(e, "P31"):
            continue
        lab = e.get("labels") or {}
        name = ((lab.get("en") or lab.get("ja") or {}).get("value") or "").strip()
        if name and name not in out:
            out.append(name)
    return out[:limit]


def board_item(board, follow, get=None):
    """ライブラリの版面 1 つ → emblem_fill が読む items.yaml の 1 項目。前の回の手がかり（emblem_*）は config から続ける。"""
    import user_pages
    cfg = board.get("config") or {}
    sec = (follow or {}).get("section") or ""
    wd = wd_entity(board.get("wd"), get)
    human, links = wd.get("human", False), wd.get("links") or {}
    old = int((cfg.get("emblem_state") or {}).get("v") or 1) < RULES
    item = {k: v for k, v in cfg.items() if (k.startswith("emblem") and k != "emblem_state" or k in ("emblem", "theme", "anilist_id", "wiki"))
            and v is not None and not (old and k in REDO)}
    if old and any(x.get("lock") for x in cfg.get("emblem") or []):   # 固定した小元素は規則の版が上がっても残す
        item["emblem"] = [x for x in cfg["emblem"] if x.get("lock")]
    item.update(name=board["name"], type=user_pages.TYPE_OF_SEC.get(sec, "category"),
                keywords=cfg.get("keywords") or [board["name"]])
    item.setdefault("emblem_kind", kind_for(sec, (follow or {}).get("subs"), human))
    if item["emblem_kind"] == "character":   # 名簿（roster）と Fandom の立ち絵の手がかり。前の回に書いたもの・店長の手書きが先
        if wd.get("anilist") and str(wd["anilist"]).isdigit():
            item.setdefault("anilist_id", int(wd["anilist"]))
        if wd.get("fandom") and re.fullmatch(r"[a-z0-9-]+", str(wd["fandom"])):
            item.setdefault("emblem_fandom", wd["fandom"])
    if item["emblem_kind"] == "group" and not item.get("emblem_who") and board.get("wd"):   # メンバー（店長のグループの emblem_who と同じ）を Wikidata から
        who = group_members(board["wd"], get)
        if who:
            item["emblem_who"] = who
    if item["emblem_kind"] == "topic" and not item.get("emblem_icon"):
        item["emblem_icon"] = icons_for(board["name"], sec, (follow or {}).get("subs"))
    if links and not item.get("wiki"):
        item["wiki"] = [f"{k}:{v}" for k, v in sorted(links.items())]
    if board.get("wd"):
        item["wikidata"] = board["wd"]
    return item


def yaml_text(item):
    """emblem_fill・emblem が行で書き換えられる形（「  - name: …」の下に「    key: 値」1 行ずつ。値は JSON = YAML のフロー）。"""
    rows = [f'  - name: "{item["name"]}"']   # emblem の行の探し方（"?名前"?）に合わせて字はそのまま（" と \\ のある名前は fill_board で飛ばす）
    rows += [f"    {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in item.items() if k != "name"]
    return "items:\n" + "\n".join(rows) + "\n"


@contextlib.contextmanager
def sandbox(item):
    """版面 1 つだけの items.yaml と docs/emblems を一時の場所に作り、emblem・emblem_fill をそこへ向ける（本物の items.yaml には触れない）。"""
    import emblem
    import emblem_fill
    import sitedir
    saved = (emblem.ROOT, emblem_fill.ROOT, sitedir.SITE_DIR, emblem.EMB_DIR, emblem_fill._live)
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "items.yaml").write_text(yaml_text(item), encoding="utf-8")
        site = root / "site"
        emblem.ROOT = emblem_fill.ROOT = root
        sitedir.SITE_DIR, emblem.EMB_DIR = site, site / "emblems"
        emblem_fill._live = lambda *a, **k: None   # 「いま動いているもの」に版面の名前を出さない
        try:
            yield root, site
        finally:
            emblem.ROOT, emblem_fill.ROOT, sitedir.SITE_DIR, emblem.EMB_DIR, emblem_fill._live = saved


def public_url(base, path):
    return f"{base.rstrip('/')}/storage/v1/object/public/{BUCKET}/{path}"


def stash(emblems, site, stem, upload, base):
    """切り抜いて手元に置いた画像（emblems/…webp）を公開の箱へ上げ、網址に書き換える。→ 新しいリスト。"""
    out = []
    for x in emblems or []:
        x = dict(x)
        img = str(x.get("image") or "")
        if re.fullmatch(r"emblems/[^/]+\.webp", img):
            data = (site / img).read_bytes()
            name = f"{stem}-{hashlib.sha1(data).hexdigest()[:10]}.webp"
            upload(name, data)
            x["image"] = public_url(base, name)
        out.append(x)
    return out


def unbroken(emblems, photo, fetch=None):
    """公開の箱の網址の小元素のうち、壊れたもの（emblem_fill.broken_image）を外す。→ 新しいリスト。読めないものは残す（次の回）。"""
    import urllib.request
    from PIL import Image
    import emblem
    import emblem_fill
    fetch = fetch or (lambda u: urllib.request.urlopen(u, timeout=20).read())
    out, hashes = [], []
    for x in emblems or []:
        u = str(x.get("image") or "") if isinstance(x, dict) else ""
        if isinstance(x, dict) and emblem.bad_source(x):   # 別の作品・持ち物の絵（原神 Kaeya の Item_Stella_Fortuna）
            continue
        if f"/storage/v1/object/public/{BUCKET}/" in u and x.get("shape") not in ("logo", "icon", "badge"):   # 自分で切り抜いて上げたものだけ
            try:
                im = Image.open(io.BytesIO(fetch(u)))
                if emblem_fill.too_small(im, bool(x.get("body"))) or emblem_fill.broken_image(im, photo):
                    continue
                h = emblem_fill._hash(im)   # 同じ見た目の画像は 1 枚（前の回に別の名前で上がった同じ絵）。固定は残す
                if not x.get("lock") and any(bin(h ^ y).count("1") <= emblem_fill.SAME_BITS for y in hashes):
                    continue
                hashes.append(h)
            except Exception:
                pass
        out.append(x)
    return out


def split_closeups(emblems, fetch=None, staged=False):
    """公開の箱の網址の小元素のうち顔だけのアップ（emblem_fill.closeup_of：顔の幅 > CLOSE_W か、顔の下 < SHOULDER_MIN）を分ける。
    → (残す, 外す, 段階的に入れ替える)。1 版面で CLOSE_HOLD 以上が当たる版面（前から段階的に入れ替え中の staged も）は外さず「段階的に入れ替える」へ
    （stage_holds：胸像が取れた人から入れ替え・取れなくて CLOSE_TRIES 回で外す）。顔が測れない・読めないものは残す。固定・全身・ロゴは見ない。
    外したものの元の画像は emblem_reject、人は emblem_redo に（呼び側。DB には直接書かない：この回の config の書き直しの道）。"""
    import urllib.request
    from PIL import Image
    import emblem_fill
    fetch = fetch or (lambda u: urllib.request.urlopen(u, timeout=20).read())
    keep, gone = [], []
    for x in emblems or []:
        u = str(x.get("image") or "") if isinstance(x, dict) else ""
        if isinstance(x, dict) and f"/storage/v1/object/public/{BUCKET}/" in u and x.get("shape") not in ("logo", "icon", "badge") and not x.get("body") and not x.get("lock"):
            try:
                if emblem_fill.closeup_of(Image.open(io.BytesIO(fetch(u)))):
                    gone.append(x)
                    continue
            except Exception:
                pass
        keep.append(x)
    if gone and emblems and (staged or len(gone) / len(emblems) >= emblem_fill.CLOSE_HOLD):
        return list(emblems), [], gone
    return keep, gone, []


def stage_holds(item, emblems, hold, pend, fetch=None):
    """半分以上が顔だけのアップの版面の段階的な入れ替え（店長の emblem_fill.stage_closeups と同じ形。回数は boards.config.emblem_closeup {人: 回数}）。
    胸像の代わりを探し、取れた人から入れ替える（取れるまでは元のまま）。CLOSE_TRIES 回取れなかった人は外す（名簿の上位 CLOSE_TOP 人は探し続ける）。
    入れ替えた胸像は手元（sandbox の emblems/）に置く：あとの stash が公開の箱へ上げる。→ (新しい小元素, 外した小元素, 新しい回数)"""
    import emblem
    import emblem_fill
    who = item.get("emblem_who") or []
    cur = {x["subject"] for x in hold}
    tries = {s: int(pend.get(s) or 0) for s in cur}
    by = {x["subject"]: x for x in hold}
    skip = set(item.get("emblem_reject") or []) | {u for x in emblems or [] if isinstance(x, dict) for u in (x.get("image"), x.get("source")) if u}
    out, new, dropped, swapped = {}, dict(tries), [], {}
    for s in emblem_fill.close_round(cur, who, tries):   # 店長と同じ：上位 12 人は毎回・ほかは 1 回 8 人
        try:
            emblem_fill._check_time()
        except emblem_fill.OutOfTime:
            break
        try:   # 元の画像（質の下限・「元より上がるときだけ」の比べ先）
            import urllib.request
            from PIL import Image
            ou = str(by[s].get("image") or "")
            orig = Image.open(io.BytesIO((fetch or (lambda u: urllib.request.urlopen(u, timeout=20).read()))(ou))) if ou.startswith("http") else None
        except Exception:
            orig = None
        got = emblem_fill.bust_replacement(item, by[s], skip, orig=orig)
        if got:
            swapped[s] = got
            new.pop(s, None)
        else:
            new[s] = tries[s] + 1
            if new[s] >= emblem_fill.CLOSE_TRIES and not emblem_fill.close_top(s, who):
                dropped.append(by[s])
                new.pop(s, None)
    rows = []
    for x in emblems or []:
        if isinstance(x, dict) and x.get("subject") in swapped and x in hold:
            url, cut, fs = swapped[x["subject"]]
            slug = emblem.slugify(item["name"], x["subject"]) + "-bust"
            emblem.save_cut(cut, slug)
            y = {k: v for k, v in x.items() if k not in ("face", "fs", "crop", "upper", "ar")}
            y.update(image=f"emblems/{slug}.webp", source=url, shape="cutout", fs=fs, why=f"{x['subject']}（Fandom のページの胸像：顔だけのアップの代わり）")
            rows.append(y)
        elif not any(x is d for d in dropped):
            rows.append(x)
    return rows, dropped, {s: n for s, n in new.items() if s in cur and n is not None}


def closeup_fields(pend, who):
    """胸像待ちの boards.config に書く分。待ちの人 {人: 取れなかった回数}（なくなれば None で消す）・各人の次に試す見込み・版面の見込み
    （店長の state/emblem_closeup*.json と同じ式 emblem_fill.close_plan）。点検 emb_check E20 が読む。"""
    import emblem_fill
    at, eta = emblem_fill.close_plan(pend, who) if pend else (None, None)
    return {"emblem_closeup": pend or None, "emblem_closeup_next": at, "emblem_closeup_eta": eta}


def measure_faces(emblems, fetch=None):
    """人物の切り抜き（公開の箱の網址）の顔を測る（店長の items.yaml と同じ emblem_face.measure）。→ (新しいリスト, 測った枚数)。
    お客さまの版面も店長と同じ fit/view で顔の大きさをそろえる材料（boards.config.emblem[].face）。"""
    import urllib.request
    from PIL import Image
    import emblem_face
    get = fetch or (lambda u: urllib.request.urlopen(u, timeout=20).read())

    def load(u):
        try:
            return Image.open(io.BytesIO(get(u))) if u.startswith("http") else None
        except Exception:
            return None
    out = [dict(x) if isinstance(x, dict) else x for x in emblems or []]
    return out, emblem_face.measure_emblems(out, load)


def fill_board(board, follow, upload, base, fill=None, get=None, now=None, fetch=None):
    """版面 1 つ → boards.config に足す分 {emblem, theme, emblem_*, emblem_state}。"""
    import emblem
    import emblem_fill
    import yaml
    fill = fill or emblem_fill.fill_one
    if re.search(r'["\\\n]', board["name"]):
        return {"emblem_state": {"state": "failed", "have": 0, "at": int(now or time.time()), "note": "名前に \" か \\ がある", "v": RULES}}
    item = board_item(board, follow, get)
    with sandbox(item) as (root, site):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):   # emblem の print（版面・人の名前、多くは stderr）を公開のログに出さない
            try:
                r = fill(item, log=lambda *a, **k: None)
            except emblem_fill.OutOfTime:
                r = {"state": "failed", "note": "時間切れ"}
        got = (yaml.safe_load((root / "items.yaml").read_text(encoding="utf-8"))["items"] or [{}])[0]
        recheck = int(((board.get("config") or {}).get("emblem_state") or {}).get("bv") or 0) < emblem_fill.BROKEN_V
        touched = False
        pend = dict(((board.get("config") or {}).get("emblem_closeup")) or {})   # 顔だけのアップを段階的に入れ替え中の人 {人: 取れなかった回数}
        if recheck and got.get("emblem"):   # 前の回に公開の箱へ上げた小元素は emblem_fill.broken_cuts が見ない（emblems/ の手元の画像だけ）→ ここで同じ規則（ポケモン 2・Mrs. GREEN APPLE 1）
            got["emblem"] = unbroken(got["emblem"], emblem_fill.needs_face(item))
        if (recheck or pend) and got.get("emblem") and emblem_fill.kind_of(item) in ("person", "group", "character"):   # 顔だけのアップ（BROKEN_V 8）
            got["emblem"], gone, hold = split_closeups(got["emblem"], fetch, staged=bool(pend))
            if hold:   # 半分以上：段階的に入れ替え（胸像が取れた人から・3 回で外す）
                got["emblem"], dropped, pend = stage_holds({**item, **got}, got["emblem"], hold, pend, fetch=fetch)
                gone = gone + dropped
            if not hold:
                pend = {}
            touched = True
            if gone:   # 外して元の画像は emblem_reject・人は emblem_redo → 次の回に胸像を探す
                got["emblem_reject"] = list(dict.fromkeys(list(got.get("emblem_reject") or []) + [g.get("source") or g["image"] for g in gone]))
                got["emblem_redo"] = list(dict.fromkeys(list(got.get("emblem_redo") or []) + [g["subject"] for g in gone if g.get("subject")]))
        stem = board.get("wd") or f"b{board['id']}"
        cfg = board.get("config") or {}
        add = {k: v for k, v in got.items() if k not in KEEP and v != cfg.get(k)}
        if touched and (pend or cfg.get("emblem_closeup")):
            add.update(closeup_fields(pend, item.get("emblem_who") or []))
        if got.get("emblem"):
            add["emblem"] = stash(got["emblem"], site, stem, upload, base)
        char = item["emblem_kind"] == "character"
        if int((cfg.get("emblem_state") or {}).get("v") or 1) < RULES:   # 作り直し：前の規則のものは消す
            # 新しい規則で作ったもの（got）は前と同じ値でも残す。消すのは新しい規則が作らなかったものだけ（前は「前と同じ」名簿・分類まで null にしていた）
            add.update({k: None for k in REDO if cfg.get(k) is not None and got.get(k) is None})
            # 新しい規則で 1 枚も取れなければ前のものを残す（0 枚にしない、#333 のあと BTS・iPhone）。キャラも同じ：名簿は分類の全員（原神 139 人）なので
            # 「名簿にいる人を残す」では字の順で取った前の脇役（Aino・Alhaitham…）が全部残っていた。字だけ・図・古い写真は外す
            if not add.get("emblem"):
                keep = [x for x in cfg.get("emblem") or [] if not emblem_fill.not_emblem(urllib.parse.unquote(str(x.get("image") or "")))]
                keep = unbroken(keep, emblem_fill.needs_face(item))   # 前のものを残すときも頭が切れた・ぼやけたものは残さない
                if keep:
                    add["emblem"] = keep
        if add.get("emblem"):   # 同じ画像は 1 枚（公開の箱の名前は中身の指紋：スプラ 3 の Agent 8 が 2 回）・キャラでないページは外す
            imgs, out = set(), []
            for x in add["emblem"]:
                if x.get("image") in imgs or char and emblem.not_character(x.get("subject")):
                    continue
                imgs.add(x.get("image"))
                out.append(x)
            add["emblem"] = out
    cur_em = add["emblem"] if "emblem" in add else cfg.get("emblem")   # 顔の大きさ：新しいものも、前の回から続くもの（網址）も、店長と同じに測る
    if cur_em:
        measured, n = measure_faces(cur_em, fetch)
        if n:
            add["emblem"] = measured
    have = len(add.get("emblem") or []) if "emblem" in add else len(got.get("emblem") or [])
    note = re.sub(r"新しい記事が来たらすぐ、来なくても \d+ 時間後", f"{RETRY_HOURS} 時間後", str(r.get("note") or ""))  # 店長の文のまま（材料の指紋・毎時）だと中身と合わない
    add["emblem_state"] = {"state": r.get("state", "failed"), "have": have, "at": int(now or time.time()), "note": note[:200], "v": RULES,
                         "nv": emblem_fill.NAMES_V, "bv": emblem_fill.BROKEN_V}   # bv：公開の箱の小元素を見直した壊れ方の規則の版   # 名簿の規則の版（上がると、そろった版面も 1 回名簿を数え直す）
    return add


NAMES_HINT = ("emblem_fandom", "emblem_category", "emblem_who", "anilist_id")   # キャラの名簿の手がかり（届かなかった版面のうち、名簿の版で数え直すもの）


def cfg(b):
    return b.get("config") or {}


def apply_requests(c):
    """管理ページ「小元素」の依頼（boards.config.emblem_requests：_emblem_swap・_emblem_lock・_emblem_reject）を版面の config に反映する。
    店長の版面の digest.reject_emblems / lock_emblems と同じ決まり：外す・替える = 小元素から抜いて元の画像を emblem_reject に（二度と選ばない）、
    替える はその人（subject）を emblem_redo に残して次の回に同じ人の別の写真を探す、固定 = lock: true（作り直しでも替えない）。
    → config に足す分。替える・外すがあれば、足りない分を次の回に埋める（emblem_state を running に）。依頼がなければ {}。"""
    import emblem_fill
    reqs = [r for r in c.get("emblem_requests") or [] if isinstance(r, dict)]
    if not reqs:
        return {}
    ems = [x for x in c.get("emblem") or [] if isinstance(x, dict)]
    rej, redo, gone = list(c.get("emblem_reject") or []), list(c.get("emblem_redo") or []), 0
    looks = [s for s in c.get("emblem_reject_look") or [] if isinstance(s, str)]   # 外した絵の見た目の鍵（emblem_fill.check が近い絵を落とす）

    def hit(x, want):
        return x.get("image") in want or x.get("source") in want
    for r in reqs:
        for key in ("_emblem_swap", "_emblem_reject"):
            want = {m.get("image") for m in r.get(key) or [] if isinstance(m, dict)}
            for x in [x for x in ems if hit(x, want)]:
                ems.remove(x)
                gone += 1
                h = emblem_fill.look_of(x)
                if h and h not in looks:
                    looks.append(h)
                rej += [u for u in (x.get("source"), x.get("image")) if isinstance(u, str) and re.match(r"https?://", u)]
                if key == "_emblem_swap" and x.get("subject"):
                    redo.append(x["subject"])
        for m in r.get("_emblem_lock") or []:
            for x in ems:
                if isinstance(m, dict) and hit(x, {m.get("image")}):
                    x.pop("lock", None)
                    if m.get("on") is not False:
                        x["lock"] = True
    import emblem_cands   # 候補から選ぶ：集める人（emblem_want）・選んだ候補（emblem_picks。並んだ候補にある網址だけ）
    want, picks = list(c.get("emblem_want") or []), list(c.get("emblem_picks") or [])
    for r in reqs:
        for m in r.get("_emblem_cands") or []:
            s = str(m.get("subject") or "")[:120] if isinstance(m, dict) else ""
            if s and s not in want and len(want) < emblem_cands.MAX_WANT:
                want.append(s)
        for m in r.get("_emblem_pick") or []:
            f = emblem_cands.lookup(c.get("emblem_cands"), m.get("pick")) if isinstance(m, dict) else None
            if f and isinstance(m.get("image"), str):
                picks.append({"old": m["image"], "subject": f[0], "cand": f[1]})
    add = {"emblem": ems, "emblem_reject": list(dict.fromkeys(rej)), "emblem_requests": [], "emblem_want": want, "emblem_picks": picks}
    if looks:
        add["emblem_reject_look"] = looks
    if redo:
        add["emblem_redo"] = list(dict.fromkeys(redo))
    if gone:
        add["emblem_state"] = {**(c.get("emblem_state") or {}), "state": "running", "have": len(ems)}
    return add


def serve(board, follow, upload, base, get=None):
    """候補から選ぶ（emblem_cands）：選ばれた候補への入れ替え（fill_board と同じ一時の場所・同じ公開の箱）と、候補集め。→ boards.config に足す分。"""
    import emblem_cands
    import emblem_fill
    c = cfg(board)
    add, cands = {}, dict(c.get("emblem_cands") or {})
    picks = [p for p in c.get("emblem_picks") or [] if isinstance(p, dict)]
    if picks:
        def pick_fill(item, log=print):
            for p in picks:
                emblem_cands.apply_pick(item["name"], p["old"], p["cand"], log)
            it = next(i for i in emblem_fill.load_items() if i["name"] == item["name"])
            return {"state": "ok" if emblem_fill.status(it)["state"] == "ok" else "running", "note": "候補から選んだ"}
        add = fill_board(board, follow, upload, base, fill=pick_fill, get=get)
        for p in picks:
            cands.pop(p.get("subject"), None)
        add["emblem_picks"] = []
    want = [s for s in c.get("emblem_want") or [] if isinstance(s, str)]
    if want:
        item = board_item(board, follow, get)
        left = []
        with sandbox(item), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            for s in want:
                try:
                    cands[s] = emblem_cands.find(item, s, log=lambda *a, **k: None)
                except emblem_fill.OutOfTime:
                    left.append(s)
                except Exception:  # noqa: BLE001  1 人の失敗でほかを止めない
                    cands[s] = []
        add["emblem_want"] = left
    add["emblem_cands"] = cands
    return add


def due(boards, now):
    """やる順：まだ一度も試していない版面 → 0 枚の版面（エンブレムが出ていない：途中・届かなかったもの）→ 途中（running）→
    届かなかったものは RETRY_HOURS たってから（前の版の規則で試したものはすぐ）。済み（ok）は飛ばす。
    0 枚を先に：キャラの多い途中の版面（1 回 1 版面 5 分）が前にいると、0 枚の版面が何回も待たされる（#329 のあと 28 版面待ち）。"""
    import emblem_fill
    names_v = emblem_fill.NAMES_V
    out = []
    for b in boards:
        st = (b.get("config") or {}).get("emblem_state") or {}
        zero = not int(st.get("have") or 0)
        if not st:
            out.append((0, b["id"], b))
        elif st.get("state") == "running":
            out.append((1 if zero else 2, st.get("at", 0), b))
        elif int(st.get("v") or 1) < RULES or st.get("state") != "ok" and now - int(st.get("at") or 0) > RETRY_HOURS * 3600:
            out.append((1 if zero else 3, st.get("at", 0), b))
        elif st.get("state") != "ok" and (st.get("nv") != names_v or int(st.get("bv") or 0) < emblem_fill.BROKEN_V):   # 届かなかった版面も、規則の版が上がったら 24 時間を待たない
            out.append((1 if zero else 1.5, st.get("at", 0), b))
        elif st.get("nv") != names_v and (st.get("state") == "ok" or any(cfg(b).get(k) for k in NAMES_HINT)):
            # そろっていても、届かなかったキャラの版面も（RETRY_HOURS を待たずに）、名簿の規則が新しくなったら 1 回数え直す（呪術廻戦が AniList の主役 4 人で止まっていた）
            # 届かなかった版面の数え直しは途中（running）より先（1.5）：途中の版面は 10 枚ずつで何十回も続き、後ろの 142・146 が 24 時間待たされていた
            out.append((1.8 if st.get("state") == "ok" else 1 if zero else 1.5, st.get("at", 0), b))   # 済みの数え直しは軽い（名簿を数えるだけ）ので途中（2）より先：最後だと 41 版面の後ろで 4 時間たっても回らなかった（ポケモンの名簿の順）
        elif cfg(b).get("emblem_closeup"):   # 顔だけのアップを段階的に入れ替え中（胸像を探す・3 回で外す）：待たずに次の回も
            out.append((1.6, st.get("at", 0), b))
        elif not zero and int(st.get("bv") or 0) < emblem_fill.BROKEN_V:
            # 公開の箱の小元素を今の壊れ方の規則（頭が切れた・ぼやけた）でまだ見ていない版面は、届かなかった・済みでも待たずに 1 回（ポケモンが 24 時間待ち）
            out.append((1.5, st.get("at", 0), b))
    return [b for *_, b in sorted(out, key=lambda t: (t[0], t[1]))]


def _upload(base, key):
    def up(name, data):
        req = urllib.request.Request(f"{base.rstrip('/')}/storage/v1/object/{BUCKET}/{name}", data=data, method="POST",
                                     headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "image/webp",
                                              "x-upsert": "true", "Cache-Control": "max-age=31536000"})
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
    return up


def main(argv):
    import os
    import digest
    import emblem_face
    import emblem_fill
    import library
    minutes = float(argv[argv.index("--minutes") + 1]) if "--minutes" in argv else 25
    end = time.time() + minutes * 60
    emblem_fill._deadline[0] = end
    settings, _ = digest.load_config()
    base, key = settings.get("supabase_url") or "", os.environ.get("SUPABASE_SERVICE_KEY")
    if not (base and key):
        raise SystemExit("SUPABASE_SERVICE_KEY がありません")
    shop = {f["board_id"] for f in digest.supabase("follows?account=eq.test1&select=board_id") or []}
    boards = [b for b in digest.supabase("boards?followers=gt.0&select=id,name,wd,config&order=id") or [] if b["id"] not in shop]
    for b in boards:   # 管理ページの 替える・固定・外す の依頼を先に反映（替える・外すは次の due で同じ人の別の写真を探す）
        add = apply_requests(cfg(b))
        if add:
            cur = (digest.supabase(f"boards?id=eq.{b['id']}&select=config") or [{}])[0].get("config") or {}
            b["config"] = {**cur, **add}
            digest.supabase(f"boards?id=eq.{b['id']}", {"config": b["config"]}, method="PATCH")
    for b in boards:   # 候補から選ぶ（入れ替え・候補集め）。名前は出さない
        if cfg(b).get("emblem_want") or cfg(b).get("emblem_picks"):
            f = (digest.supabase(f"follows?board_id=eq.{b['id']}&select=section,subs&order=created_at&limit=1") or [{}])[0]
            try:
                add = serve(b, f, _upload(base, key), base)
            except Exception as ex:  # noqa: BLE001
                print(f"候補から選ぶ：1 版面で失敗 {type(ex).__name__}")
                continue
            cur = (digest.supabase(f"boards?id=eq.{b['id']}&select=config") or [{}])[0].get("config") or {}
            b["config"] = {**cur, **add}
            digest.supabase(f"boards?id=eq.{b['id']}", {"config": b["config"]}, method="PATCH")
    for b in boards:   # 顔を測っていない小元素のある版面（前に作ったもの）を測る。1 回済めば次からは何もしない
        if end - time.time() < PER_BOARD_S:
            break
        if emblem_face.unmeasured(cfg(b).get("emblem")):
            try:
                em, n = measure_faces(cfg(b).get("emblem"))
            except Exception:  # noqa: BLE001
                continue
            if n:
                cur = (digest.supabase(f"boards?id=eq.{b['id']}&select=config") or [{}])[0].get("config") or {}
                b["config"] = {**cur, "emblem": em}
                digest.supabase(f"boards?id=eq.{b['id']}", {"config": b["config"]}, method="PATCH")
    todo = due(boards, time.time())
    done = {"ok": 0, "running": 0, "failed": 0, "blocked": 0}
    for b in todo:
        if end - time.time() < PER_BOARD_S:
            break
        f = (digest.supabase(f"follows?board_id=eq.{b['id']}&select=section,subs&order=created_at&limit=1") or [{}])[0]
        try:
            add = fill_board(b, f, _upload(base, key), base)
        except library.WdBlocked:   # 種類（人かどうか）が決まらない：書かずに次の回へ
            done["blocked"] += 1
            continue
        except Exception as ex:  # noqa: BLE001  1 版面の失敗でほかを止めない（名前は出さない）
            add = {"emblem_state": {"state": "failed", "have": 0, "at": int(time.time()), "note": type(ex).__name__}}
        cur = (digest.supabase(f"boards?id=eq.{b['id']}&select=config") or [{}])[0].get("config") or {}
        digest.supabase(f"boards?id=eq.{b['id']}", {"config": {**cur, **add}}, method="PATCH")
        st = add["emblem_state"]["state"]
        done[st] = done.get(st, 0) + 1
    print(f"ライブラリの小元素：対象 {len(todo)} 版面（店長の版面を除く {len(boards)}）・"
          f"そろった {done['ok']}・途中 {done['running']}・届かない {done['failed']}・Wikidata に断られて次へ {done['blocked']}")


if __name__ == "__main__":
    main(sys.argv[1:])
