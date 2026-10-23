"""ライブラリ（2026-10-23，用户定的）：みんなの版面の置き場（Supabase の boards / board_stories / follows、db/library.sql）。

店長もお客さまも、ライブラリから自分の版面を選ぶ（なければ 1 つ足す）。記事集め・AI 編集・デザインは版面ごとに 1 回。
- 同じものかどうか（board_key）：Wikidata の番号があれば 'wd:Q…'、なければ名前をそろえたもの（全角半角・大小・空白・記号）'n:…'
- items.yaml の 1 項目を、みんなで共有する設定（config）と人ごとの置き方（follows：section・subs・also・size・priority）に分ける（split_item）

    python scripts/library.py --sql > x.sql    # 店長の items.yaml をライブラリへ写す SQL（boards と test1 の follows）
    python scripts/library.py --push           # 同じことを secret key（SUPABASE_SERVICE_KEY）で直接（Actions の library.yml）
"""
import json
import pathlib
import re
import sys
import unicodedata
import urllib.parse

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
PERSONAL = ("section", "subs", "also", "size", "priority")   # 人ごとの置き方（follows の列）。ほかは版面の共有の設定（boards.config）
SHOP = "test1"


def norm_name(name):
    """名前をそろえる（additem.js の normName と同じ考え方＋全角半角）。"""
    t = unicodedata.normalize("NFKC", str(name or "")).lower()
    return re.sub(r"[\s・:!?\-–—.,'\"「」『』()（）]", "", t)


def board_key(item):
    wd = str(item.get("wikidata") or "").strip()
    if re.fullmatch(r"Q\d+", wd):
        return "wd:" + wd
    return "n:" + norm_name(item.get("name"))


def split_item(item):
    """items.yaml の 1 項目 → (共有の設定, 人ごとの置き方)。"""
    shared = {k: v for k, v in item.items() if k not in PERSONAL and k not in ("name", "parent", "wikidata")}
    mine = {k: item[k] for k in PERSONAL if item.get(k) is not None}
    return shared, mine


def q(v):
    return "'" + str(v).replace("'", "''") + "'"


def shop_sql(items):
    """店長の items.yaml → boards（上級を先に）と test1 の follows を入れる SQL。何度流しても同じ（key で上書き）。"""
    out = []
    for item in sorted(items, key=lambda i: bool(i.get("parent"))):
        shared, _ = split_item(item)
        out.append(
            "insert into public.boards (key, name, names, wd, config, created_by) values ("
            f"{q(board_key(item))}, {q(item['name'])}, {q(json.dumps({'ja': item['name']}, ensure_ascii=False))}::jsonb, "
            f"{q(item['wikidata']) if re.fullmatch(r'Q[0-9]+', str(item.get('wikidata') or '')) else 'null'}, "
            f"{q(json.dumps(shared, ensure_ascii=False))}::jsonb, {q(SHOP)}) "
            "on conflict (key) do update set name = excluded.name, config = excluded.config, updated_at = now();")
    by_name = {i["name"]: i for i in items}
    for item in items:
        if item.get("parent") in by_name:
            out.append(f"update public.boards set parent_id = (select id from public.boards where key = {q(board_key(by_name[item['parent']]))}) "
                       f"where key = {q(board_key(item))};")
    for pos, item in enumerate(items):
        _, mine = split_item(item)
        out.append(
            "insert into public.follows (account, board_id, section, subs, also, size, pos) values ("
            f"{q(SHOP)}, (select id from public.boards where key = {q(board_key(item))}), "
            f"{q(mine['section']) if mine.get('section') else 'null'}, {q(json.dumps(mine.get('subs') or {}, ensure_ascii=False))}::jsonb, "
            f"{q(json.dumps(mine.get('also') or {}, ensure_ascii=False))}::jsonb, {q(mine['size']) if mine.get('size') else 'null'}, {pos}) "
            "on conflict (account, board_id) do update set section = excluded.section, subs = excluded.subs, also = excluded.also, size = excluded.size, pos = excluded.pos;")
    return "\n".join(out)


def shop_rows(items):
    """店長の items.yaml → (boards の行, 上級の対応 {key: 上級の key}, follows の行（board_id の代わりに key）)。"""
    by_name = {i["name"]: i for i in items}
    boards, parents, follows = [], {}, []
    for pos, item in enumerate(items):
        shared, mine = split_item(item)
        wd = str(item.get("wikidata") or "")
        boards.append({"key": board_key(item), "name": item["name"], "names": {"ja": item["name"]},
                       "wd": wd if re.fullmatch(r"Q\d+", wd) else None, "config": shared, "created_by": SHOP})
        if item.get("parent") in by_name:
            parents[board_key(item)] = board_key(by_name[item["parent"]])
        follows.append({"account": SHOP, "key": board_key(item), "section": mine.get("section"), "subs": mine.get("subs") or {},
                        "also": mine.get("also") or {}, "size": mine.get("size"), "pos": pos})
    return boards, parents, follows


def push_shop(items):
    """店長の版面をライブラリへ（何度流しても同じ：key・(account, board_id) で上書き）。"""
    import digest
    boards, parents, follows = shop_rows(items)
    got = digest.supabase("boards?on_conflict=key&select=id,key", boards, prefer="resolution=merge-duplicates,return=representation")
    if got is None:
        raise SystemExit("SUPABASE_SERVICE_KEY がないので書けません")
    ids = {r["key"]: r["id"] for r in got}
    for child, parent in parents.items():
        digest.supabase(f"boards?key=eq.{urllib.parse.quote(child)}", {"parent_id": ids[parent]}, method="PATCH")
    rows = [{**{k: v for k, v in f.items() if k != "key"}, "board_id": ids[f["key"]]} for f in follows]
    digest.supabase("follows?on_conflict=account,board_id", rows, prefer="resolution=merge-duplicates")
    print(f"ライブラリ：版面 {len(boards)}・店長の follows {len(rows)}・上級 {len(parents)}")


if __name__ == "__main__":
    items = (yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")) or {}).get("items") or []
    if "--sql" in sys.argv:
        print(shop_sql(items))
    if "--push" in sys.argv:
        sys.path.insert(0, str(ROOT / "scripts"))
        push_shop(items)
