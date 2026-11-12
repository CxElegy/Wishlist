"""ハーネス v2 のやることの列（HARNESS_V2.md）。1 段 = harness/tasks/T-NNNN.json の 1 ファイル。

BACKLOG.md（551KB）を係が毎回読むのをやめる。係は `q.py next` で次の段だけを受け取り、列の全部は読まない。
push はしない：取った印（claim）・途中の状態（attempts・parked など）は手元の D:/Claude/hf/state/ に置く（環境変数 HF_STATE で変えられる）。
リポジトリの中のファイルが変わるのは add（新しい段）と done --file（合併する PR に入れる）だけ。

  python harness/q.py next [--n 3] [--kind fix] [--json]      次に進められる段（範囲のファイルが重ならないものだけ）
  python harness/q.py claim T-0003 --owner build:T-0003        取る（同じ持ち主がもう一度呼べば時刻を更新。60 分動きがなければ取り直せる）
  python harness/q.py release T-0003
  python harness/q.py contract T-0003 --kind visual --complexity normal --scope a.py,b.css --done-when "…" [--done-when "…"]   計画の係が約束を決めて凍らせる
  python harness/q.py done T-0003 [--pr URL] [--file]          済み（--file：リポジトリのファイルも status=done にする。合併する枝の中で）
  python harness/q.py park T-0003 --why "…" [--waiting] [--cls infra|work|size|conflict] [--resume-branch B --resume-worktree W --resume-commit C --resume-stage build|fix|ship --resume-note "…"]
                                                               止める（--waiting：店長の答え待ち）。--cls infra（PC の負荷・網の不安定で止めた）は次の回にいちばん先に出る（3 回まで）。
                                                               --resume-*：枝・作業ツリー・コミット・どの段から続けるか（次の係は作り直さずにここから続ける）
  python harness/q.py split T-0009 --from-json F.json          1 つの係で作りきれない段を、順番つきの小さい段に分ける（{"parts":[{title,kind,complexity,scope,done_when}…]}）。
                                                               子は凍った約束で生まれ、前の子が済むまで出ない（after）。親は split、子が全部済めば済み
  python harness/q.py reopen T-0003
  python harness/q.py add --title … --why … [--quote …] [--kind fix] [--scope a,b] [--done-when …] [--priority 5] [--local]
  python harness/q.py contract T-0003 --from-json F.json      （おすすめ）UTF-8 の JSON ファイルから読む。シェルの path 変換を受けない
  python harness/q.py add --from-json F.json [--local]         同上（title・why・quote・kind・complexity・priority・scope・done_when・source）
  python harness/q.py repair T-0003 --from-json F.json --reason "…"   凍った約束を 1 段だけ書き直す（主の会話だけが使う。notes に repaired_at と理由）
  python harness/q.py index [--out PATH]                       人が読む一覧（既定 harness/tasks/INDEX.md）
  python harness/q.py show T-0003
  python harness/q.py import-backlog BACKLOG.md [--limit N]    「## いちばん先」の開いている段を写す（1 回だけ）

段のファイルの形（約束＝title・why・quote・kind・complexity・scope・done_when は frozen のあと変えない。変わるのは status・attempts・notes だけ）：
  {"id","title","why","quote","kind":"fix|visual|options|kpi|verify","complexity":"light|normal|hard","priority","scope":[ファイル],"done_when":[確かめ方],
   "status":"open|done|parked|waiting","attempts":0,"notes":[],"frozen":false,"source","created"}
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time

KINDS = ("fix", "visual", "options", "kpi", "verify")   # verify はループが自分で足す「本番でまだ確かめていない」段
STATUSES = ("open", "done", "parked", "waiting", "split")
PARK_CLASSES = ("infra", "work", "size", "conflict")   # infra＝PC の負荷・網の不安定（中身は良い）／work＝審査・試験を通らない／size＝1 つの係で作りきれない／conflict＝main と競合
INFRA_RETRIES = 3   # infra で止めた段を自動でやり直す回数（attempts がこれ未満のあいだ）
RESUME_KEYS = ("branch", "worktree", "commit", "stage", "note")
COMPLEXITY = ("light", "normal", "hard")   # 作る・直す係のモデルを決める：light=Haiku・normal=Sonnet・hard=Opus（計画の係が付ける）
CLAIM_STALE_MIN = 60
JST = dt.timezone(dt.timedelta(hours=9))
CONTRACT = ("title", "why", "quote", "kind", "complexity", "scope", "done_when")


# Git Bash（MSYS）が引数の「/ で始まる・D:/ に見える」文字を勝手に書き換えた跡。凍る約束にこれが入ると直せないので、書く前に断る。
MANGLED_RE = re.compile(r"C:\\Program Files\\Git\\|[A-Za-z]?;[A-Za-z]:\\|(?<![\w:\.])(?:harness|scripts|docs|tests|db|\.github)\\\w")
MANGLED_HINT = ("Git Bash の path 変換で文字が書き換わっている（C:\\Program Files\\Git\\… ・ ;C:\\ ・ harness\\x.py など）。"
                "命令の前に MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' を付けるか、--from-json <UTF-8 の JSON ファイル> で渡すこと")


def check_mangled(**fields):
    """文字（または文字の列）の中に MSYS の書き換え跡があれば ValueError。"""
    for k, v in fields.items():
        for x in ([v] if isinstance(v, str) else v or []):
            if isinstance(x, str) and MANGLED_RE.search(x):
                raise ValueError(f"{k} が壊れている：{x[:80]!r} … {MANGLED_HINT}")


def read_json_arg(path):
    """--from-json：UTF-8（BOM 付きも可）の JSON の辞書。scope・done_when は文字でも列でも可。"""
    try:
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ValueError(f"--from-json {path} を読めない：{e}")
    if not isinstance(d, dict):
        raise ValueError("--from-json は {…} の形")
    if isinstance(d.get("scope"), str):
        d["scope"] = [x for x in d["scope"].split(",") if x.strip()]
    if isinstance(d.get("done_when"), str):
        d["done_when"] = [d["done_when"]]
    return d


def state_dir():
    return pathlib.Path(os.environ.get("HF_STATE") or "D:/Claude/hf/state")


def repo_root():
    """今いる作業ツリー（harness/tasks があるもの）。なければこのファイルのリポジトリ。"""
    if os.environ.get("HF_ROOT"):
        return pathlib.Path(os.environ["HF_ROOT"])
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
        if top and (pathlib.Path(top) / "harness" / "tasks").is_dir():
            return pathlib.Path(top)
    except OSError:
        pass
    return pathlib.Path(__file__).resolve().parent.parent


def tasks_dir(root=None):
    return (root or repo_root()) / "harness" / "tasks"


def now_iso(now=None):
    return dt.datetime.fromtimestamp(now or time.time(), JST).isoformat(timespec="seconds")


def _read(p):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _safe(s):
    """段の文に鍵の名前をそのまま書かない（harness/free_tier_gate.py の token_hits が .json も見る）。値は元から書かない決まり。"""
    return s.replace("SUPABASE_ACCESS" + "_TOKEN", "SUPABASE_ACCESS＿TOKEN")


def _write(p, obj):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes((_safe(json.dumps(obj, ensure_ascii=False, indent=1)) + "\n").encode("utf-8"))   # いつも LF
    os.replace(tmp, p)


def load(root=None, state=None):
    """id → 段。リポジトリのファイルに、手元の写し（まだ合併していない段・凍らせた約束）と手元の状態を重ねる。"""
    state = state or state_dir()
    out = {}
    for p in sorted(tasks_dir(root).glob("T-*.json")):
        t = _read(p)
        if t and t.get("id"):
            out[t["id"]] = t
    for p in sorted((state / "tasks_local").glob("T-*.json")):
        t = _read(p)
        if not t or not t.get("id"):
            continue
        old = out.get(t["id"])
        if old is None:
            out[t["id"]] = t
        elif t.get("frozen") and not old.get("frozen"):
            out[t["id"]] = {**old, **{k: t[k] for k in CONTRACT if k in t}, "frozen": True}
    for t in out.values():
        ov = _read(state / "q" / f"{t['id']}.json") or {}
        # リポジトリで済みになった段は、手元の古い状態で開け直さない
        if t.get("status") == "done" and not t.get("recurring"):
            ov.pop("status", None)
        t.update({k: v for k, v in ov.items() if k in ("status", "attempts", "notes", "pr", "last_done", "repaired_at", "park_class", "resume")})
        t.setdefault("status", "open")
        t.setdefault("scope", [])
        t.setdefault("done_when", [])
        t.setdefault("complexity", "normal")
    return out


def overlay(tid, state=None, **kv):
    p = (state or state_dir()) / "q" / f"{tid}.json"
    ov = _read(p) or {}
    note = kv.pop("note", None)
    ov.update(kv)
    if note:
        ov["notes"] = (ov.get("notes") or [])[-9:] + [f"{now_iso()} {note}"]
    _write(p, ov)
    return ov


# ---------- 取った印（手元だけ） ----------
def claim_of(tid, state=None, now=None):
    """生きている印（60 分以内に動きがある）だけ返す。"""
    c = _read((state or state_dir()) / "claims" / f"{tid}.json")
    if not c:
        return None
    return c if (now or time.time()) - c.get("beat", 0) < CLAIM_STALE_MIN * 60 else None


def claim(tid, owner, state=None, now=None):
    """取れたら True。ほかの持ち主の生きている印があれば False。"""
    state = state or state_dir()
    now = now or time.time()
    p = state / "claims" / f"{tid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"task": tid, "owner": owner, "since": now, "beat": now}
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)   # 同時に 2 人が取らない
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        return True
    except FileExistsError:
        cur = _read(p) or {}
        live = now - cur.get("beat", 0) < CLAIM_STALE_MIN * 60
        if live and cur.get("owner") != owner:
            return False
        if live:
            rec["since"] = cur.get("since", now)
        _write(p, rec)
        return True


def touch_claim(tid, state=None, now=None):
    """心拍（hb.py beat）が呼ぶ：印があれば時刻だけ更新。"""
    p = (state or state_dir()) / "claims" / f"{tid}.json"
    c = _read(p)
    if c:
        c["beat"] = now or time.time()
        _write(p, c)


def release(tid, state=None):
    try:
        ((state or state_dir()) / "claims" / f"{tid}.json").unlink()
    except OSError:
        pass


# ---------- 次の段 ----------
def norm_scope(scope):
    return {s.strip().replace("\\", "/").lstrip("./").lower() for s in scope or [] if s and s.strip()}


def overlaps(a, b):
    """範囲のファイルが 1 つでも同じなら重なる。範囲が空の段は「どこを触るか分からない」ので、空どうしは重なる扱い。"""
    a, b = norm_scope(a), norm_scope(b)
    if not a and not b:
        return True
    return bool(a & b)


def pick(tasks, n):
    """優先の順に、前に選んだものと範囲が重ならない段だけ n 個まで。"""
    out = []
    for t in tasks:
        if len(out) >= n:
            break
        if not any(overlaps(t.get("scope"), o.get("scope")) for o in out):
            out.append(t)
    return out


def retry_infra(t):
    """PC の負荷・網で止めた段（中身は良い）：次の回に自動でやり直す。"""
    return t.get("status") == "parked" and t.get("park_class") == "infra" and t.get("attempts", 0) < INFRA_RETRIES


def blocked(t, tasks):
    """前の段（after）がまだ済んでいない。"""
    return any((tasks.get(a) or {}).get("status") != "done" for a in t.get("after") or [])


def ready(tasks, state=None, now=None, kind=None, owner=None):
    """開いていて、ほかの係が取っていない段を優先の順に。kind を言わなければ verify は出さない（確かめの係だけが取る）。
    infra で止めた段（中身は良い・PC の負荷で合併できなかった）は open と同じに出し、いちばん先に並べる。前の段（after）が済んでいない段は出さない。"""
    out = []
    for t in tasks.values():
        if not (t["status"] == "open" or retry_infra(t)) or (kind and t.get("kind") != kind) or (not kind and t.get("kind") == "verify"):
            continue
        if blocked(t, tasks):
            continue
        c = claim_of(t["id"], state, now)
        if c and owner != "*" and c.get("owner") != owner:   # owner="*"：取られた段も含める（一覧・要約）
            continue
        out.append(t)
    return sorted(out, key=lambda t: (0 if retry_infra(t) else 1, t.get("priority", 999), t["id"]))


def brief(t, why=500):
    return {"id": t["id"], "title": t["title"], "kind": t.get("kind", "fix"), "complexity": t.get("complexity", "normal"), "priority": t.get("priority", 999),
            "scope": t.get("scope", []), "done_when": t.get("done_when", []), "frozen": bool(t.get("frozen")),
            "attempts": t.get("attempts", 0), "why": (t.get("why") or "")[:why], "quote": t.get("quote", ""),
            "status": t.get("status", "open"), "park_class": t.get("park_class", ""), "resume": t.get("resume") or {},
            "after": t.get("after") or [], "parent": t.get("parent", "")}


# ---------- 足す ----------
def title_key(title):
    return hashlib.sha1(re.sub(r"[\s\W_]+", "", title.lower()).encode("utf-8")).hexdigest()[:12]


def next_id(tasks):
    n = max([int(i.split("-")[1]) for i in tasks if re.fullmatch(r"T-\d+", i)] or [0])
    return f"T-{n + 1:04d}"


def add(title, why="", quote="", kind="fix", scope=(), done_when=(), priority=50, source="", root=None, state=None,
        local=False, created=None, extra=None, complexity="normal"):
    """新しい段。同じ題（記号・空白を除いて同じ）がもう開いていれば足さず、その id を返す（(id, False)）。"""
    if kind not in KINDS:
        raise ValueError(f"kind は {KINDS} のどれか")
    if complexity not in COMPLEXITY:
        raise ValueError(f"complexity は {COMPLEXITY} のどれか")
    check_mangled(title=title, why=why, quote=quote, scope=list(scope), done_when=list(done_when))
    state = state or state_dir()
    tasks = load(root, state)
    key = title_key(title)
    for t in tasks.values():
        if title_key(t["title"]) == key and t["status"] != "done":
            return t["id"], False
    t = {"id": next_id(tasks), "title": title.strip(), "why": why.strip(), "quote": quote.strip(), "kind": kind,
         "complexity": complexity, "priority": int(priority), "scope": [s for s in scope if s], "done_when": [d for d in done_when if d],
         "status": "open", "attempts": 0, "notes": [], "frozen": False, "source": source,
         "created": created or now_iso()[:10]}
    t.update(extra or {})
    _write(state / "tasks_local" / f"{t['id']}.json", t)   # 合併の前でも次の計画から見える
    if not local:
        _write(tasks_dir(root) / f"{t['id']}.json", t)
    return t["id"], True


def set_contract(tid, kind=None, scope=None, done_when=None, root=None, state=None, complexity=None):
    """計画の係が約束を決めて凍らせる（手元の写しに書く。リポジトリには done --file のときに入る）。凍ったあとは変えられない。"""
    state = state or state_dir()
    t = load(root, state).get(tid)
    if not t:
        raise KeyError(tid)
    if t.get("frozen"):
        raise ValueError(f"{tid} の約束はもう凍っている（変えない）")
    check_mangled(scope=scope, done_when=done_when)
    if kind:
        if kind not in KINDS:
            raise ValueError(f"kind は {KINDS} のどれか")
        t["kind"] = kind
    if complexity:
        if complexity not in COMPLEXITY:
            raise ValueError(f"complexity は {COMPLEXITY} のどれか")
        t["complexity"] = complexity
    if scope is not None:
        t["scope"] = [s for s in scope if s]
    if done_when:
        t["done_when"] = list(done_when)
    if not t["done_when"]:
        raise ValueError("done_when（確かめ方）が 1 つも無い約束は凍らせない")
    t["frozen"] = True
    keep = {k: v for k, v in t.items() if k not in ("status", "attempts", "notes", "pr", "last_done")}
    _write(state / "tasks_local" / f"{tid}.json", {**keep, "status": "open", "attempts": 0, "notes": []})
    return t


def split(tid, parts, root=None, state=None):
    """1 つの係で作りきれない段を、順番つきの子に分ける（計画の係）。子は凍った約束で手元に生まれ、前の子の after を持つ。
    親は status=split（子が全部済めば done が親も済みにする）。親の枝・作業ツリー（resume）は最初の子が引き継ぐ。"""
    state = state or state_dir()
    t = load(root, state).get(tid)
    if not t:
        raise KeyError(tid)
    if not parts or len(parts) < 2:
        raise ValueError("分けるなら 2 つ以上（parts）")
    for i, p in enumerate(parts):
        if not p.get("title") or not p.get("done_when"):
            raise ValueError(f"parts[{i}] に title と done_when が要る")
    ids, prev = [], None
    for i, p in enumerate(parts):
        dw = p["done_when"] if isinstance(p["done_when"], list) else [p["done_when"]]
        extra = {"parent": tid, "after": [prev] if prev else [], "frozen": True}
        nid, new = add(p["title"], why=p.get("why") or t.get("why", ""), quote=t.get("quote", ""), kind=p.get("kind") or t.get("kind", "fix"),
                       scope=p.get("scope") or t.get("scope", []), done_when=dw, priority=t.get("priority", 50),
                       source=f"split:{tid}", root=root, state=state, local=True, extra=extra, complexity=p.get("complexity") or "normal")
        if not new:
            raise ValueError(f"同じ題の段がもうある：{nid}（題を変える）")
        if i == 0 and t.get("resume"):
            overlay(nid, state, resume=t["resume"])
        ids.append(nid)
        prev = nid
    overlay(tid, state, status="split", note=f"分けた：{' → '.join(ids)}")
    release(tid, state)
    return ids


def repair(tid, fields, reason, root=None, state=None, now=None):
    """凍った約束を 1 段だけ書き直す（文字化け・path 変換の事故の直し）。主の会話だけが使う。notes に repaired_at と理由。
    約束の置き場に直す：手元の写し（tasks_local）、リポジトリのファイルがもう凍っていればそれも。"""
    state = state or state_dir()
    if not (reason or "").strip():
        raise ValueError("--reason（なぜ直すか）が要る")
    t = load(root, state).get(tid)
    if not t:
        raise KeyError(tid)
    new = {k: fields[k] for k in CONTRACT if k in fields}
    if not new:
        raise ValueError(f"JSON に直す欄が無い（{', '.join(CONTRACT)} のどれか）")
    check_mangled(**{k: v for k, v in new.items() if k in ("title", "why", "quote", "scope", "done_when")})
    if "kind" in new and new["kind"] not in KINDS:
        raise ValueError(f"kind は {KINDS} のどれか")
    if "complexity" in new and new["complexity"] not in COMPLEXITY:
        raise ValueError(f"complexity は {COMPLEXITY} のどれか")
    if "done_when" in new and not new["done_when"]:
        raise ValueError("done_when（確かめ方）が空の約束にはしない")
    t.update(new)
    t["frozen"] = True
    keep = {k: v for k, v in t.items() if k not in ("status", "attempts", "notes", "pr", "last_done", "repaired_at")}
    local = state / "tasks_local" / f"{tid}.json"
    _write(local, {**(_read(local) or {"status": "open", "attempts": 0, "notes": []}), **keep})
    rf = _read(tasks_dir(root) / f"{tid}.json")
    if rf and rf.get("frozen"):   # 合併した凍った約束は、リポジトリのファイルのほうが勝つので、そちらも直す（PR に入れる）
        _write(tasks_dir(root) / f"{tid}.json", {**rf, **new})
    stamp = now_iso(now)
    overlay(tid, state, repaired_at=stamp, note=f"約束を直した（repaired_at {stamp}）：{reason.strip()}（直した欄：{', '.join(new)}）")
    return load(root, state)[tid]


def done(tid, pr="", file=False, root=None, state=None, now=None):
    state = state or state_dir()
    t = load(root, state).get(tid)
    if not t:
        raise KeyError(tid)
    if file:   # 合併する枝の中のファイル（約束ごと）を済みにする。手元の状態は合併のあとで別に呼ぶ
        if not t.get("recurring"):
            body = {k: v for k, v in t.items() if k not in ("last_done",)}
            body.update(status="done", pr=pr or t.get("pr", ""))
            _write(tasks_dir(root) / f"{tid}.json", body)
        return t
    if t.get("recurring"):   # 毎回やる段（新規ユーザーの KPI）：済みにせず、次の回にまた出す
        overlay(tid, state, status="open", last_done=now_iso(now), pr=pr, note=f"1 回終わり {pr}".strip())
    else:
        overlay(tid, state, status="done", pr=pr, note=f"済み {pr}".strip(), park_class="", resume={})
    release(tid, state)
    par = t.get("parent")
    if par:   # 分けた段：子が全部済めば親も済み
        all_t = load(root, state)
        kids = [k for k in all_t.values() if k.get("parent") == par]
        if kids and all(k["status"] == "done" for k in kids) and (all_t.get(par) or {}).get("status") == "split":
            overlay(par, state, status="done", note=f"子が全部済んだ（{', '.join(sorted(k['id'] for k in kids))}）")
    return t


def park(tid, why, waiting=False, root=None, state=None, cls=None, resume=None):
    """止める。cls（PARK_CLASSES）と resume（枝・作業ツリー・コミット・どの段から）を残すと、次の係は作り直さずにそこから続ける。"""
    state = state or state_dir()
    t = load(root, state).get(tid)
    if not t:
        raise KeyError(tid)
    if cls and cls not in PARK_CLASSES:
        raise ValueError(f"--cls は {PARK_CLASSES} のどれか")
    kv = {"park_class": cls or ""}
    res = {k: v for k, v in (resume or {}).items() if k in RESUME_KEYS and v}
    if res:
        check_mangled(**{k: v for k, v in res.items() if k != "note"})
        kv["resume"] = {**(t.get("resume") or {}), **res}
    overlay(tid, state, status="waiting" if waiting else "parked", attempts=t.get("attempts", 0) + 1,
            note=("店長待ち：" if waiting else "止めた" + (f"［{cls}］" if cls else "") + "：") + why, **kv)
    release(tid, state)


# ---------- 一覧 ----------
def counts(tasks, state=None, now=None):
    c = {s: 0 for s in STATUSES}
    c["claimed"] = 0
    for t in tasks.values():
        c[t["status"]] = c.get(t["status"], 0) + 1
        if t["status"] == "open" and claim_of(t["id"], state, now):
            c["claimed"] += 1
    return c


def index_md(tasks, state=None, now=None, top=30):
    c = counts(tasks, state, now)
    L = ["# やることの列（harness/q.py が作る。手で書かない）", "",
         f"開いている {c['open']}（うち進行中 {c['claimed']}）・店長待ち {c['waiting']}・止めた {c['parked']}・済み {c['done']}", "",
         f"## 次の {top} 個", ""]
    for t in ready(tasks, state, now, owner="*")[:top]:
        L.append(f"- {t['id']} [{t.get('kind', 'fix')}] {t['title'][:90]}")
    for head, st in (("店長待ち", "waiting"), ("止めた（主の会話が見る）", "parked")):
        rows = [t for t in tasks.values() if t["status"] == st]
        if rows:
            L += ["", f"## {head}", ""]
            L += [f"- {t['id']} {t['title'][:70]} — {(t.get('notes') or [''])[-1][:120]}" for t in sorted(rows, key=lambda t: t["id"])]
    return "\n".join(L) + "\n"


# ---------- BACKLOG.md から写す（1 回だけ） ----------
PATH_RE = re.compile(r"[\w./-]+\.(?:py|ya?ml|js|css|html|md|sql|sh|json)\b")
VISUAL_RE = re.compile(r"画面|見た目|余白|空き|はみ出|スマホ|レイアウト|\d ?px|CSS|\.css|字体|写真の(?:切|帯|大き|高さ|枠)")
QUOTE_RE = re.compile(r"(?:店長|ユーザー|用户)[^「」]{0,12}「([^」]{4,200})」")


def backlog_items(text):
    """「## いちばん先」の節の、開いている - [ ] の段（続きの字下げ行も 1 つに）。[(行番号, 文)]"""
    out, on, cur = [], False, None
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            if on:
                break
            on = line.startswith("## いちばん先")
            continue
        if not on:
            continue
        if line.startswith("- ["):
            cur = [n, line[6:].strip()] if line.startswith("- [ ]") else None
            if cur:
                out.append(cur)
        elif cur and line.startswith((" ", "\t")) and line.strip():
            cur[1] += "\n" + line.rstrip()
        elif not line.strip():
            cur = None
    return [(n, s) for n, s in out]


def guess_scope(text, root):
    found = []
    for m in PATH_RE.findall(text):
        m = m.lstrip("./")
        for pre in ("", "scripts/", "harness/", ".github/workflows/", "docs/", "db/", "tests/"):
            if "/" in pre + m and (root / (pre + m)).is_file():
                if pre + m not in found:
                    found.append(pre + m)
                break
    return found[:8]


def from_backlog(text, root, created, limit=None):
    tasks = []
    for i, (line, body) in enumerate(backlog_items(text)[:limit], 1):
        first = body.split("\n")[0]
        b = re.search(r"\*\*(.+?)\*\*", first)
        title = (b.group(1) if b else re.split(r" — |。", re.sub(r"^(【[^】]*】\s*)+", "", first))[0]).strip()[:120]
        tag = re.match(r"(【[^】]*】)", first)
        if tag and not title.startswith("【"):
            title = f"{tag.group(1)}{title}"
        m = re.search(r"できたと言える条件[：:]\s*(.+)", body)
        dw = m.group(1).split("\n")[0][:400] if m else (first.split(" — ", 1)[1][:300] if " — " in first else "")
        q = QUOTE_RE.search(body)
        d = re.search(r"20\d\d-\d\d-\d\d", first)
        kind = "kpi" if "board_kpi.py" in first and "newuser" in first else "visual" if VISUAL_RE.search(title) else "fix"
        t = {"id": f"T-{i:04d}", "title": title, "why": body, "quote": q.group(1) if q else "", "kind": kind, "complexity": "normal", "priority": i,
             "scope": guess_scope(body, root), "done_when": [dw] if dw else [], "status": "open", "attempts": 0, "notes": [],
             "frozen": False, "source": f"BACKLOG.md:{line}", "created": d.group(0) if d else created}
        if kind == "kpi":
            t["recurring"] = True
        tasks.append(t)
    return tasks


# ---------- 命令 ----------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("next"); s.add_argument("--n", type=int, default=3); s.add_argument("--kind"); s.add_argument("--json", action="store_true"); s.add_argument("--owner")
    s = sub.add_parser("claim"); s.add_argument("id"); s.add_argument("--owner", required=True)
    s = sub.add_parser("release"); s.add_argument("id")
    s = sub.add_parser("contract"); s.add_argument("id"); s.add_argument("--kind"); s.add_argument("--complexity", choices=COMPLEXITY); s.add_argument("--scope"); s.add_argument("--done-when", action="append", default=[]); s.add_argument("--from-json")
    s = sub.add_parser("repair"); s.add_argument("id"); s.add_argument("--from-json", required=True); s.add_argument("--reason", required=True)
    s = sub.add_parser("done"); s.add_argument("id"); s.add_argument("--pr", default=""); s.add_argument("--file", action="store_true")
    s = sub.add_parser("park"); s.add_argument("id"); s.add_argument("--why", required=True); s.add_argument("--waiting", action="store_true")
    s.add_argument("--cls", choices=PARK_CLASSES)
    for k in RESUME_KEYS:
        s.add_argument(f"--resume-{k}", default="")
    s = sub.add_parser("split"); s.add_argument("id"); s.add_argument("--from-json", required=True)
    s = sub.add_parser("reopen"); s.add_argument("id")
    s = sub.add_parser("add"); s.add_argument("--title", default=""); s.add_argument("--why", default=""); s.add_argument("--quote", default="")
    s.add_argument("--kind", default="fix"); s.add_argument("--scope", default=""); s.add_argument("--done-when", action="append", default=[])
    s.add_argument("--priority", type=int, default=50); s.add_argument("--source", default=""); s.add_argument("--local", action="store_true"); s.add_argument("--complexity", choices=COMPLEXITY, default="normal"); s.add_argument("--from-json")
    s = sub.add_parser("index"); s.add_argument("--out")
    s = sub.add_parser("show"); s.add_argument("id")
    s = sub.add_parser("import-backlog"); s.add_argument("file"); s.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(errors="replace")   # cp932 の画面でも ✓ ✗ で落ちない
        except (AttributeError, ValueError):
            pass
    try:
        return run(a)
    except (KeyError, ValueError) as e:
        print(f"✗ {e}")
        return 2


def run(a):
    if a.cmd == "next":
        got = [brief(t) for t in pick(ready(load(), kind=a.kind, owner=a.owner), a.n)]
        if a.json:
            print(json.dumps(got, ensure_ascii=False))
        else:
            for t in got:
                print(f"{t['id']} [{t['kind']}・{t['complexity']}] {t['title']}\n   範囲：{', '.join(t['scope']) or '（未定）'}\n   確かめ：{' / '.join(t['done_when']) or '（未定）'}")
            if not got:
                print("進められる段がない")
        return 0
    if a.cmd == "claim":
        if a.id not in load():
            raise KeyError(a.id)
        ok = claim(a.id, a.owner)
        print(f"{'✓ 取った' if ok else '✗ ほかの係が進めている'}：{a.id}")
        return 0 if ok else 1
    if a.cmd == "release":
        release(a.id)
    elif a.cmd == "contract":
        j = read_json_arg(a.from_json) if a.from_json else {}
        scope = j["scope"] if "scope" in j else a.scope.split(",") if a.scope is not None else None
        t = set_contract(a.id, j.get("kind") or a.kind, scope, j.get("done_when") or a.done_when, complexity=j.get("complexity") or a.complexity)
        print(json.dumps(brief(t), ensure_ascii=False))
    elif a.cmd == "repair":
        t = repair(a.id, read_json_arg(a.from_json), a.reason)
        print(json.dumps(brief(t), ensure_ascii=False))
    elif a.cmd == "done":
        done(a.id, a.pr, a.file)
        print(f"✓ 済み：{a.id}{'（ファイル）' if a.file else ''}")
    elif a.cmd == "park":
        park(a.id, a.why, a.waiting, cls=a.cls, resume={k: getattr(a, f"resume_{k}") for k in RESUME_KEYS})
        print(f"✓ {'店長待ち' if a.waiting else '止めた'}：{a.id}")
    elif a.cmd == "split":
        j = read_json_arg(a.from_json)
        print(json.dumps({"parent": a.id, "parts": split(a.id, j.get("parts") or [])}, ensure_ascii=False))
    elif a.cmd == "reopen":
        if a.id not in load():
            raise KeyError(a.id)
        overlay(a.id, status="open", note="開け直した")
    elif a.cmd == "add":
        j = read_json_arg(a.from_json) if a.from_json else {}
        g = lambda k, d: j.get(k, d)
        title = g("title", a.title)
        if not title:
            raise ValueError("title が要る（--title か --from-json）")
        tid, new = add(title, g("why", a.why), g("quote", a.quote), g("kind", a.kind), g("scope", a.scope.split(",")), g("done_when", a.done_when),
                       g("priority", a.priority), g("source", a.source), local=a.local or bool(j.get("local")), complexity=g("complexity", a.complexity))
        print(json.dumps({"id": tid, "new": new}, ensure_ascii=False))
    elif a.cmd == "index":
        out = pathlib.Path(a.out) if a.out else tasks_dir() / "INDEX.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(index_md(load()).encode("utf-8"))
        print(f"✓ {out}")
    elif a.cmd == "show":
        t = load().get(a.id)
        if not t:
            raise KeyError(a.id)
        print(json.dumps(t, ensure_ascii=False, indent=1))
    elif a.cmd == "import-backlog":
        root = repo_root()
        if any(tasks_dir(root).glob("T-*.json")):
            raise ValueError("harness/tasks にもう段がある（写すのは 1 回だけ）")
        ts = from_backlog(pathlib.Path(a.file).read_text(encoding="utf-8"), root, now_iso()[:10], a.limit)
        for t in ts:
            _write(tasks_dir(root) / f"{t['id']}.json", t)
        print(f"✓ {len(ts)} 段を写した")
    return 0


if __name__ == "__main__":
    sys.exit(main())
