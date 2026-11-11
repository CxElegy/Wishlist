"""お客さまの版面の AI 編集の受け渡し（2026-11-07，用户定的：ログインの要るものはクラウドに任せる）。

クラウドの AI 編集は DB の鍵を持たない。Actions（鍵あり）が間に立つ：
  sync：AI が書いた結果 inbox/lib/edits/<版面 id>.json を DB へ → 次に編む版面を inbox/lib/queue.json へ。
  クラウド：digest.py edit-next → edit-brief --only lib:<id> → lib-publish --only lib:<id>（鍵がないときは edits に書く）→ push。

queue.json に置くのは版面の名前と公開のニュースだけ。だれが追いかけているか（account）は書かない。

    python scripts/lib_queue.py sync     # background.yml
"""
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / "inbox" / "lib" / "queue.json"
EDITS = ROOT / "inbox" / "lib" / "edits"
ROW_KEYS = ("title", "date", "source", "summary", "url", "image")


def load_queue(path=None):
    try:
        data = json.loads(pathlib.Path(path or QUEUE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_queue(data, path=None):
    p = pathlib.Path(path or QUEUE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def _edited_ids(edits=None):
    return {p.stem for p in pathlib.Path(edits or EDITS).glob("*.json")}


def todo(queue=None, edits=None):
    """まだ編んでいない版面 → [(版面 id, 名前, 記事数)]（library.edit_todo と同じ形）。"""
    done = _edited_ids(edits)
    return [(b["id"], b["name"], len(b.get("rows") or [])) for b in load_queue(queue).get("boards") or [] if str(b["id"]) not in done]


def fresh_ids(queue=None):
    """queue.json の版面のうち、一度も AI 編集していないもの（export が fresh を付けた）の id。"""
    return {str(b["id"]) for b in load_queue(queue).get("boards") or [] if b.get("fresh")}


def done_today(today, queue=None, edits=None):
    """今日 AI が編んだ版面の数（gate の「本当に進んだか」の目印）。"""
    d = load_queue(queue).get("done") or {}
    return (int(d.get("n") or 0) if d.get("day") == today else 0) + len(_edited_ids(edits))


def _board(bid, queue=None):
    return next((b for b in load_queue(queue).get("boards") or [] if str(b["id"]) == str(bid)), None)


def brief(bid, queue=None):
    """AI に読ませる短い一覧（library.edit_brief と同じ書き方）。"""
    import library
    b = _board(bid, queue)
    if not b:
        return ""
    rows = b.get("rows") or []
    out = [f"## {b['name']}（ライブラリの版面 {bid}・{len(rows)} 件。全部が整理待ち＝新しく編む）"]
    for n, p in enumerate(rows, 1):
        summ = " ".join(str(p.get("summary") or "").split())[:library.LIB_SUMMARY]
        out.append(f"{n} {str(p.get('date') or '')[:10]} {p.get('source') or ''}｜{p.get('title') or ''}" + (f"｜{summ}" if summ else ""))
    return "\n".join(out)


def save_edit(bid, edit, queue=None, edits=None):
    """AI の結果を置く。番号は一覧に対するものなので、一覧の写しも一緒に置く（あとで記事が増えても番号がずれない）。"""
    b = _board(bid, queue)
    if not b:
        raise SystemExit(f"編む版面の一覧に {bid} がない")
    d = pathlib.Path(edits or EDITS)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{int(bid)}.json").write_text(json.dumps({"day": b["day"], "fp": b["fp"], "rows": b["rows"], "edit": edit}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    return d / f"{int(bid)}.json"


def apply_edits(db, today, queue=None, edits=None, log=print):
    """edits の結果を board_stories.stories へ（Actions）。書けたものだけ消す（失敗は次の回にもう一度）。→ 書いた版面の数"""
    import library
    at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    n = 0
    for p in sorted(pathlib.Path(edits or EDITS).glob("*.json")):
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
            st = library.edited_stories(e["rows"], e["edit"], e["fp"], at)
            db(f"board_stories?board_id=eq.{int(p.stem)}&day=eq.{e['day']}", {"stories": st, "updated_at": at}, "return=minimal", method="PATCH")
        except (OSError, ValueError, KeyError, TypeError) as err:
            log(f"ライブラリの版面 {p.stem}：書けなかった（{type(err).__name__}）")
            continue
        p.unlink()
        n += 1
        log(f"ライブラリの版面 {p.stem}：AI 編集の記事 {sum(1 for s in st if s.get('headline'))} 本")
    return n


def export(db, today, shop_names, applied=0, queue=None, log=print):
    """次に編む版面を queue.json へ（library.LIB_EDIT_MAX まで）。"""
    import library
    data = load_queue(queue)
    done = data.get("done") or {}
    done = {"day": today, "n": (int(done.get("n") or 0) if done.get("day") == today else 0) + applied}
    rows = library.lib_rows(db, today, shop_names, fresh=True)
    boards = []
    for row in library.edit_todo(db, today, shop_names)[:library.LIB_EDIT_MAX]:
        r = rows.get(int(row[0]))
        if r and r.get("pending"):
            boards.append({"id": int(row[0]), "name": r["name"], "day": r["day"], "fp": library.pending_fp(r["pending"]),
                           "fresh": not (r.get("stories") or r.get("prev")),   # 直近の日に一度も AI 編集していない新しい版面（gate が 4 時間待たずに起こす）
                           "rows": [{k: p.get(k) for k in ROW_KEYS} for p in r["pending"]]})
    new = {"done": done, "boards": boards}
    if new != data:
        save_queue(new, queue)
    log(f"ライブラリの版面：書いた {applied}・次に編む {len(boards)}")
    return boards


def sync():
    import digest
    today = digest._lib_today()
    shop = [i["name"] for i in digest.load_config()[1]]
    if digest.supabase("boards?select=id&limit=1") is None:   # 鍵がない・制限中：何も変えない
        print("ライブラリの版面：DB に届かないので飛ばす")
        return 0
    export(digest.supabase, today, shop, apply_edits(digest.supabase, today))
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["sync"]:
        raise SystemExit(__doc__)
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.exit(sync())
