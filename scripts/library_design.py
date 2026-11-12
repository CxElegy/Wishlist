"""ライブラリの版面（boards）のデザインの回：主題 motif・配色 theme・👍 演出 like_fx を boards.config に足す。
店長の版面は AI 編集が items.yaml に書く（EDITING.md 第 1 步）。ライブラリの版面は誰が追っているかによらず同じ回で：
  python scripts/library_design.py --list            デザインのない版面（id・名前・板块・小分類・小元素の数）を JSON で
  python scripts/library_design.py --apply 案.json   {"id": {"motif": …, "theme": {…}, "like_fx": …}} を足す（あるものは触らない。--force で上書き）
  python scripts/library_design.py --auto [--dry]    デザインのない版面へ、規則だけ（AI なし）の主題・配色を足す（足すだけ。--dry は件数だけ）
  python scripts/library_design.py --check           デザインのない版面が 0 か（0 でなければ終了コード 1）
SUPABASE_SERVICE_KEY が要る（読む・config に足すだけ）。"""

import colorsys
import hashlib
import json
import sys

import sbstate

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


def auto_design(name, section):
    """版面 1 つの規則だけの案（AI なし）。motif：render.template_for と同じ種類（板块 → type → 模版の defaults）。
    theme：名前から決めた色相の主色を theme.py の規則（_shift・_readable・暗い主面と明るい副面）で 6 色に。like_fx は模版の演出。"""
    import render
    import theme
    import user_pages
    typ = user_pages.TYPE_OF_SEC.get(section or "", "category")
    motif = render.template_for({"type": typ, "notes": render.WEB_ITEM_MARK}) or "pop"
    hue = int(hashlib.sha256(str(name).encode("utf-8")).hexdigest()[:6], 16) % 360 / 360
    base = tuple(c * 255 for c in colorsys.hls_to_rgb(hue, 0.5, 0.6))
    bg, alt_bg = theme._shift(base, 0.11), theme._shift(base, 0.93)
    fg, alt_fg = (242, 238, 230), (26, 28, 34)
    accent = theme._readable(theme._shift(base, 0.6, max_sat=0.75), bg)
    alt_accent = theme._readable(accent, alt_bg)
    th = {"bg": bg, "fg": fg, "accent": accent, "alt_bg": alt_bg, "alt_fg": alt_fg, "alt_accent": alt_accent}
    return {"motif": motif, "theme": {k: theme._hex(v) for k, v in th.items()}, "like_fx": render.TEMPLATE_FX.get(motif, "pop")}


def auto(boards, sections, dry=False):
    """デザインのない版面へ足す（あるものは触らない・書き込みは library.put_config だけ）。→ (足した数, 案が使えず飛ばした数)"""
    import library
    import likefx
    import render
    done = skipped = 0
    for b in boards:
        miss = missing(b.get("config"))
        if not miss:
            continue
        d = auto_design(b["name"], sections.get(b["id"]))
        if problems(d, render.MOTIFS, likefx.FX):
            skipped += 1
            continue
        add = {k: d[k] for k in miss}   # 足りない鍵だけ（motif だけあるなら theme だけ）
        if d.get("like_fx") and not (b.get("config") or {}).get("like_fx"):
            add["like_fx"] = d["like_fx"]
        if not dry:
            b["config"] = library.put_config(b["id"], add)
        done += 1
    return done, skipped


def _boards():
    import digest
    rows = digest.supabase("boards?select=id,name,config&order=id")
    if rows is None:
        sbstate.need_db("SUPABASE_SERVICE_KEY がありません")
    return rows


def main(argv):
    import library
    import likefx
    import render
    boards = _boards()
    todo = [b for b in boards if missing(b.get("config"))]
    if "--auto" in argv:
        import digest
        secs = {}
        for f in digest.supabase("follows?select=board_id,section&order=created_at") or []:
            if f.get("section"):
                secs.setdefault(f.get("board_id"), f["section"])
        dry = "--dry" in argv
        done, skipped = auto(boards, secs, dry)
        print(f"{'足せる' if dry else '足した'}版面 {done} / デザインのない版面 {len(todo)}（案が使えず飛ばした {skipped}）")
        return 0
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
            library.put_config(b["id"], add)
            done += 1
        print(f"足した版面 {done}")
        return 0
    print(json.dumps([{"id": b["id"], "name": b["name"], "missing": missing(b.get("config")),
                       "emblems": len((b.get("config") or {}).get("emblem") or [])} for b in todo], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
