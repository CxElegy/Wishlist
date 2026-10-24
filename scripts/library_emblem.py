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
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

BUCKET = "emblems"
RETRY_HOURS = 24      # 届かなかった版面をもう一度試すまで（店長の版面と違い、材料の指紋がないので 1 日おき）
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


def wd_entity(qid, get=None):
    """Wikidata → (人かどうか, {lang: 記事名})。番号がなければ (False, {})。断られたら library.WdBlocked（その版面は次の回に）。"""
    if not qid:
        return False, {}
    import library
    d = (get or library._wd_get)({"action": "wbgetentities", "ids": qid, "props": "claims|sitelinks"})
    ent = (d.get("entities") or {}).get(qid) or {}
    p31 = [((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id") for c in (ent.get("claims") or {}).get("P31") or []]
    links = {k[:-4]: v.get("title") for k, v in (ent.get("sitelinks") or {}).items()
             if re.fullmatch(r"(en|ja|zh|ko)wiki", k) and v.get("title")}
    return "Q5" in p31, links


def board_item(board, follow, get=None):
    """ライブラリの版面 1 つ → emblem_fill が読む items.yaml の 1 項目。前の回の手がかり（emblem_*）は config から続ける。"""
    import user_pages
    cfg = board.get("config") or {}
    sec = (follow or {}).get("section") or ""
    human, links = wd_entity(board.get("wd"), get)
    item = {k: v for k, v in cfg.items() if k.startswith("emblem") and k != "emblem_state" or k in ("emblem", "theme", "anilist_id", "wiki")}
    item.update(name=board["name"], type=user_pages.TYPE_OF_SEC.get(sec, "category"),
                keywords=cfg.get("keywords") or [board["name"]])
    item.setdefault("emblem_kind", kind_for(sec, (follow or {}).get("subs"), human))
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


def fill_board(board, follow, upload, base, fill=None, get=None, now=None):
    """版面 1 つ → boards.config に足す分 {emblem, theme, emblem_*, emblem_state}。"""
    import emblem_fill
    import yaml
    fill = fill or emblem_fill.fill_one
    if re.search(r'["\\\n]', board["name"]):
        return {"emblem_state": {"state": "failed", "have": 0, "at": int(now or time.time()), "note": "名前に \" か \\ がある"}}
    item = board_item(board, follow, get)
    with sandbox(item) as (root, site):
        with contextlib.redirect_stdout(io.StringIO()):   # emblem の print（版面・人の名前）を公開のログに出さない
            try:
                r = fill(item, log=lambda *a, **k: None)
            except emblem_fill.OutOfTime:
                r = {"state": "failed", "note": "時間切れ"}
        got = (yaml.safe_load((root / "items.yaml").read_text(encoding="utf-8"))["items"] or [{}])[0]
        stem = board.get("wd") or f"b{board['id']}"
        add = {k: v for k, v in got.items() if k not in KEEP and v != (board.get("config") or {}).get(k)}
        if got.get("emblem"):
            add["emblem"] = stash(got["emblem"], site, stem, upload, base)
    have = len(got.get("emblem") or [])
    add["emblem_state"] = {"state": r.get("state", "failed"), "have": have, "at": int(now or time.time()), "note": str(r.get("note") or "")[:200]}
    return add


def due(boards, now):
    """やる順：まだ一度も試していない版面 → 途中（running）→ 届かなかったものは RETRY_HOURS たってから。済み（ok）は飛ばす。"""
    out = []
    for b in boards:
        st = (b.get("config") or {}).get("emblem_state") or {}
        if not st:
            out.append((0, b["id"], b))
        elif st.get("state") == "running":
            out.append((1, st.get("at", 0), b))
        elif st.get("state") != "ok" and now - int(st.get("at") or 0) > RETRY_HOURS * 3600:
            out.append((2, st.get("at", 0), b))
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
