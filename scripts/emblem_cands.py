"""小元素の「候補から選ぶ」（2026-10-26，用户定的：管理ページ「小元素」の 🔍。おまかせの「替える」と別に、こだわる時だけ）。

押すと その人（subject）の候補を集め始め、次の後台で 4〜6 枚並ぶ → 1 枚選ぶと 今の写真と入れ替わり、そのまま固定（lock）。
- 依頼：_emblem_cands [{image, subject}]（集めて）／_emblem_pick [{image, pick}]（pick は並んだ候補の画像の網址。ここにない網址は受けない）。
- 店長の版面：digest.take_item_requests が state/emblem_cands.json に積む → emblem_fill.background の頭で run_shop。
- お客さまの版面：library_emblem.apply_requests が boards.config.emblem_want / emblem_picks に積む → library_emblem.serve。
- 集め方は fill_one と同じ段（STRATEGIES）。違うのは、人が選ぶので Web 画像検索も使い、取り方の確かさ（AUTO_SOURCES）で絞らないこと。
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

N = 6             # 並べる候補の数
MAX_WANT = 5      # 1 回の集めで受ける人の数
FILE = pathlib.Path(__file__).resolve().parent.parent / "state" / "emblem_cands.json"
KEYS = ("subject", "why", "image", "page", "source", "shape", "work", "license")


def slim(c):
    """候補 → 保存する形（_img などの重いものは捨てる）。"""
    return {k: c[k] for k in KEYS if c.get(k) not in (None, "")}


def find(item, subject, log=print, n=N):
    """item の subject の候補を n 枚まで。今ある・外した画像は除く。→ [候補]。"""
    import emblem_fill as ef
    base = ef._base_subject(subject)
    kind = ef.kind_of(item)
    probe = {k: v for k, v in item.items() if k != "_no_web"}
    probe.update(emblem=[], emblem_who=[base], emblem_redo=[])
    taken = ef._have_images(item)
    rank = {s: i for i, s in enumerate(ef.PICK_ORDER_BY_KIND.get(kind, ef.PICK_ORDER))}
    out, seen = [], set()
    for label, fn in ef.STRATEGIES:
        ef._check_time()
        try:
            cands = getattr(ef, fn)(probe, log, {})
        except ef.OutOfTime:
            raise
        except Exception as e:   # 1 つの取り方の失敗で止めない
            log(f"  [候補] {label}：{e}")
            continue
        if kind in ("character", "group"):   # 名簿の人は、その人だけ
            cands = [c for c in cands if ef._same_person(ef._base_subject(c["subject"]), base)]
        good = ef.check(cands, log, need_face=ef.needs_face(item), strict=False, reject_looks=ef.reject_looks(item))
        for c in sorted(good, key=lambda c: rank.get(c["source"].split("(")[0], len(rank))):
            k = ef.file_key(c["image"])
            if c["image"] in taken or k in taken or k in seen:
                continue
            seen.add(k)
            out.append(slim(c))
        if len(out) >= n:
            break
    return out[:n]


def apply_pick(name, old, cand, log=print):
    """name の小元素 old（画像）を cand に入れ替えて固定する。今の items.yaml（emblem.ROOT）に書く。→ 入れ替えたら True。"""
    import digest
    import emblem
    import emblem_fill as ef
    path = emblem.ROOT / "items.yaml"
    with ef.WRITE_LOCK:
        try:
            text, _ = digest.reject_emblems(path.read_text(encoding="utf-8"), name, [{"image": old}])
        except ValueError as e:
            log(f"  [候補] {e}")
            return False
        emblem.write_atomic(path, text)
        item = next(i for i in ef.load_items() if i["name"] == name)
        before = {x.get("image") for x in item.get("emblem") or [] if isinstance(x, dict)}
        ef.commit(item, [cand], [1], log=log)
        item = next(i for i in ef.load_items() if i["name"] == name)
        new = [x["image"] for x in item.get("emblem") or [] if isinstance(x, dict) and x.get("image") not in before]
        if new:
            emblem.write_atomic(path, digest.lock_emblems(path.read_text(encoding="utf-8"), name, [{"image": u} for u in new]))
    return bool(new)


def lookup(cands, url):
    """集めた候補（{subject: [候補]}）にある url の (人, 候補)。ないなら None。"""
    return next(((s, c) for s, cs in (cands or {}).items() for c in cs or [] if isinstance(c, dict) and c.get("image") == url), None)


# ---------------------------------------------------------------- 店長の版面（state/emblem_cands.json）
def load(path=None):
    try:
        return json.loads((path or FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(st, path=None):
    p = path or FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def queue(board, cfg, path=None):
    """take_item_requests から：_emblem_cands・_emblem_pick の依頼を積む。ValueError = 受けない。"""
    st = load(path)
    for m in cfg.get("_emblem_cands") or []:
        s = str((m or {}).get("subject") or "")[:120]
        if not s or not isinstance(m.get("image"), str):
            raise ValueError("候補を集める人の指定が正しくない")
        w = st.setdefault("wants", [])
        if len([x for x in w if x["board"] == board]) < MAX_WANT and not any(x["board"] == board and x["subject"] == s for x in w):
            w.append({"board": board, "subject": s})
    for m in cfg.get("_emblem_pick") or []:
        if not isinstance(m, dict) or not isinstance(m.get("image"), str) or not isinstance(m.get("pick"), str):
            raise ValueError("選んだ候補の指定が正しくない")
        found = lookup((st.get("cands") or {}).get(board), m["pick"])
        if not found:
            raise ValueError("その候補はもう並んでいない（集め直してください）")
        st.setdefault("picks", []).append({"board": board, "old": m["image"], "subject": found[0], "cand": found[1]})
    save(st, path)


def run_shop(log=print, path=None, items=None):
    """後台の頭で：積んだ「選ぶ」を入れ替え、「集めて」の候補を集める。何かしたら True。"""
    import emblem_fill as ef
    st = load(path)
    if not st.get("picks") and not st.get("wants"):
        return False
    for p in st.pop("picks", []):
        try:
            ok = apply_pick(p["board"], p["old"], p["cand"], log)
        except Exception as e:  # noqa: BLE001
            log(f"  [候補] {p['board']}：{e}")
            continue
        log(f"  [候補] {p['board']}：{p['subject']} を選んだ候補に入れ替えた" if ok else f"  [候補] {p['board']}：入れ替えなかった")
        (st.get("cands") or {}).get(p["board"], {}).pop(p["subject"], None)
    wants, st["wants"] = st.pop("wants", []), []
    save(st, path)
    for w in wants:
        item = next((i for i in (items or ef.load_items()) if i["name"] == w["board"]), None)
        if not item:
            continue
        try:
            got = find(item, w["subject"], log)
        except ef.OutOfTime:
            st.setdefault("wants", []).append(w)   # 次の回に
            continue
        except Exception as e:  # noqa: BLE001
            log(f"  [候補] {w['board']}：{e}")
            got = []
        st.setdefault("cands", {}).setdefault(w["board"], {})[w["subject"]] = got
        log(f"  [候補] {w['board']}：{w['subject']} の候補 {len(got)} 枚")
        save(st, path)
    save(st, path)
    return True


def view(st, board, emblems):
    """網页に出す分：{画像: {cands: [{image, why}], wait: bool}}。今の小元素にもう入っている画像・外れた人は出さない。"""
    out = {}
    have = {x["image"] for x in emblems}
    waiting = {w["subject"] for w in (st or {}).get("wants") or [] if w["board"] == board}
    for x in emblems:
        s = x.get("subject") or ""
        cs = [{"image": c["image"], "why": c.get("why") or ""} for c in ((st or {}).get("cands") or {}).get(board, {}).get(s) or []
              if c["image"] not in have]
        out[x["image"]] = {"cands": cs, "wait": s in waiting}
    return out

