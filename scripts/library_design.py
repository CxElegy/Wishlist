"""ライブラリの版面（boards）のデザインの回：主題 motif・配色 theme・👍 演出 like_fx を boards.config に足す。
店長の版面は AI 編集が items.yaml に書く（EDITING.md 第 1 步）。ライブラリの版面は誰が追っているかによらず同じ回で：
  python scripts/library_design.py --list            デザインのない版面（id・名前・板块・小分類・小元素の数）を JSON で
  python scripts/library_design.py --apply 案.json   {"id": {"motif": …, "theme": {…}, "like_fx": …}} を足す（あるものは触らない。--force で上書き）
  python scripts/library_design.py --check           デザインのない版面が 0 か（0 でなければ終了コード 1）
SUPABASE_SERVICE_KEY が要る（読む・config に足すだけ）。"""

import json
import sys

THEME_KEYS = ("bg", "fg", "accent", "alt_bg", "alt_fg", "alt_accent")


def missing(config):
    """config に足りないデザインのキー（motif・theme）。"""
    return [k for k in ("motif", "theme") if not (config or {}).get(k)]


def problems(d, motifs, fxs):
    """案 1 つの不備（空なら使える）。"""
    out = []
    if d.get("motif") not in motifs:
        out.append(f"motif {d.get('motif')!r} は模版にない")
    th = d.get("theme") or {}
    for k in THEME_KEYS:
        v = str(th.get(k) or "")
        if len(v) != 7 or not v.startswith("#") or any(c not in "0123456789abcdefABCDEF" for c in v[1:]):
            out.append(f"theme.{k} が #RRGGBB でない")
    if d.get("like_fx") and d["like_fx"] not in fxs:
        out.append(f"like_fx {d['like_fx']!r} は演出にない")
    return out


def _boards():
    import digest
    rows = digest.supabase("boards?select=id,name,config&order=id")
    if rows is None:
        raise SystemExit("SUPABASE_SERVICE_KEY がありません")
    return rows


def main(argv):
    import digest
    import likefx
    import render
    boards = _boards()
    todo = [b for b in boards if missing(b.get("config"))]
    if "--check" in argv:
        print(f"デザインのない版面 {len(todo)} / {len(boards)}")
        return 1 if todo else 0
    if "--apply" in argv:
        plan = json.load(open(argv[argv.index("--apply") + 1], encoding="utf-8"))
        force, done = "--force" in argv, 0
        for b in boards:
            d = plan.get(str(b["id"]))
            if not d or (not force and not missing(b.get("config"))):
                continue
            bad = problems(d, render.MOTIFS, likefx.FX)
            if bad:
                raise SystemExit(f"版面 {b['id']}：" + "・".join(bad))
            add = {k: d[k] for k in ("motif", "theme", "like_fx") if d.get(k)}
            cur = (digest.supabase(f"boards?id=eq.{b['id']}&select=config") or [{}])[0].get("config") or {}
            digest.supabase(f"boards?id=eq.{b['id']}", {"config": {**cur, **add}}, method="PATCH")
            done += 1
        print(f"足した版面 {done}")
        return 0
    print(json.dumps([{"id": b["id"], "name": b["name"], "missing": missing(b.get("config")),
                       "emblems": len((b.get("config") or {}).get("emblem") or [])} for b in todo], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
