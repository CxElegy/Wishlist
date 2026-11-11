"""ハーネス v2 のやることの列（HARNESS_V2.md）。1 段 = harness/tasks/T-NNNN.json の 1 ファイル。

BACKLOG.md（551KB）を係が毎回読むのをやめる。係は `q.py next` で次の段だけを受け取り、列の全部は読まない。
push はしない：取った印（claim）・途中の状態（attempts・parked など）は手元の D:/Claude/hf/state/ に置く（環境変数 HF_STATE で変えられる）。
リポジトリの中のファイルが変わるのは add（新しい段）と done --file（合併する PR に入れる）だけ。

  python harness/q.py next [--n 3] [--kind fix] [--json]      次に進められる段（範囲のファイルが重ならないものだけ）
  python harness/q.py claim T-0003 --owner build:T-0003        取る（同じ持ち主がもう一度呼べば時刻を更新。60 分動きがなければ取り直せる）
  python harness/q.py release T-0003
  python harness/q.py contract T-0003 --kind visual --scope a.py,b.css --done-when "…" [--done-when "…"]   計画の係が約束を決めて凍らせる
  python harness/q.py done T-0003 [--pr URL] [--file]          済み（--file：リポジトリのファイルも status=done にする。合併する枝の中で）
  python harness/q.py park T-0003 --why "…" [--waiting]        止める（--waiting：店長の答え待ち）
  python harness/q.py reopen T-0003
  python harness/q.py add --title … --why … [--quote …] [--kind fix] [--scope a,b] [--done-when …] [--priority 5] [--local]
  python harness/q.py index [--out PATH]                       人が読む一覧（既定 harness/tasks/INDEX.md）
  python harness/q.py show T-0003
  python harness/q.py import-backlog BACKLOG.md [--limit N]    「## いちばん先」の開いている段を写す（1 回だけ）

段のファイルの形（約束＝title・why・quote・kind・scope・done_when は frozen のあと変えない。変わるのは status・attempts・notes だけ）：
  {"id","title","why","quote","kind":"fix|visual|options|kpi|verify","priority","scope":[ファイル],"done_when":[確かめ方],
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
STATUSES = ("open", "done", "parked", "waiting")
CLAIM_STALE_MIN = 60
JST = dt.timezone(dt.timedelta(hours=9))
CONTRACT = ("title", "why", "quote", "kind", "scope", "done_when")


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


def _write(p, obj):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes((json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))   # いつも LF
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
        t.update({k: v for k, v in ov.items() if k in ("status", "attempts", "notes", "pr", "last_done")})
        t.setdefault("status", "open")
        t.setdefault("scope", [])
        t.setdefault("done_when", [])
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


def ready(tasks, state=None, now=None, kind=None, owner=None):
    """開いていて、ほかの係が取っていない段を優先の順に。kind を言わなければ verify は出さない（確かめの係だけが取る）。"""
    out = []
    for t in tasks.values():
        if t["status"] != "open" or (kind and t.get("kind") != kind) or (not kind and t.get("kind") == "verify"):
            continue
        c = claim_of(t["id"], state, now)
        if c and owner != "*" and c.get("owner") != owner:   # owner="*"：取られた段も含める（一覧・要約）
            continue
        out.append(t)
    return sorted(out, key=lambda t: (t.get("priority", 999), t["id"]))


def brief(t, why=500):
    return {"id": t["id"], "title": t["title"], "kind": t.get("kind", "fix"), "priority": t.get("priority", 999),
            "scope": t.get("scope", []), "done_when": t.get("done_when", []), "frozen": bool(t.get("frozen")),
            "attempts": t.get("attempts", 0), "why": (t.get("why") or "")[:why], "quote": t.get("quote", "")}


# ---------- 足す ----------
def title_key(title):
    return hashlib.sha1(re.sub(r"[\s\W_]+", "", title.lower()).encode("utf-8")).hexdigest()[:12]


def next_id(tasks):
    n = max([int(i.split("-")[1]) for i in tasks if re.fullmatch(r"T-\d+", i)] or [0])
    return f"T-{n + 1:04d}"


def add(title, why="", quote="", kind="fix", scope=(), done_when=(), priority=50, source="", root=None, state=None,
        local=False, created=None, extra=None):
    """新しい段。同じ題（記号・空白を除いて同じ）がもう開いていれば足さず、その id を返す（(id, False)）。"""
    if kind not in KINDS:
        raise ValueError(f"kind は {KINDS} のどれか")
    state = state or state_dir()
    tasks = load(root, state)
    key = title_key(title)
    for t in tasks.values():
        if title_key(t["title"]) == key and t["status"] != "done":
            return t["id"], False
    t = {"id": next_id(tasks), "title": title.strip(), "why": why.strip(), "quote": quote.strip(), "kind": kind,
         "priority": int(priority), "scope": [s for s in scope if s], "done_when": [d for d in done_when if d],
         "status": "open", "attempts": 0, "notes": [], "frozen": False, "source": source,
         "created": created or now_iso()[:10]}
    t.update(extra or {})
    _write(state / "tasks_local" / f"{t['id']}.json", t)   # 合併の前でも次の計画から見える
    if not local:
        _write(tasks_dir(root) / f"{t['id']}.json", t)
    return t["id"], True


def set_contract(tid, kind=None, scope=None, done_when=None, root=None, state=None):
    """計画の係が約束を決めて凍らせる（手元の写しに書く。リポジトリには done --file のときに入る）。凍ったあとは変えられない。"""
    state = state or state_dir()
    t = load(root, state).get(tid)
    if not t:
        raise KeyError(tid)
    if t.get("frozen"):
        raise ValueError(f"{tid} の約束はもう凍っている（変えない）")
    if kind:
        if kind not in KINDS:
            raise ValueError(f"kind は {KINDS} のどれか")
        t["kind"] = kind
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
        overlay(tid, state, status="done", pr=pr, note=f"済み {pr}".strip())
    release(tid, state)
    return t


def park(tid, why, waiting=False, root=None, state=None):
    state = state or state_dir()
    t = load(root, state).get(tid)
    if not t:
        raise KeyError(tid)
    overlay(tid, state, status="waiting" if waiting else "parked", attempts=t.get("attempts", 0) + 1,
            note=("店長待ち：" if waiting else "止めた：") + why)
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
        t = {"id": f"T-{i:04d}", "title": title, "why": body, "quote": q.group(1) if q else "", "kind": kind, "priority": i,
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
    s = sub.add_parser("contract"); s.add_argument("id"); s.add_argument("--kind"); s.add_argument("--scope"); s.add_argument("--done-when", action="append", default=[])
    s = sub.add_parser("done"); s.add_argument("id"); s.add_argument("--pr", default=""); s.add_argument("--file", action="store_true")
    s = sub.add_parser("park"); s.add_argument("id"); s.add_argument("--why", required=True); s.add_argument("--waiting", action="store_true")
    s = sub.add_parser("reopen"); s.add_argument("id")
    s = sub.add_parser("add"); s.add_argument("--title", required=True); s.add_argument("--why", default=""); s.add_argument("--quote", default="")
    s.add_argument("--kind", default="fix"); s.add_argument("--scope", default=""); s.add_argument("--done-when", action="append", default=[])
    s.add_argument("--priority", type=int, default=50); s.add_argument("--source", default=""); s.add_argument("--local", action="store_true")
    s = sub.add_parser("index"); s.add_argument("--out")
    s = sub.add_parser("show"); s.add_argument("id")
    s = sub.add_parser("import-backlog"); s.add_argument("file"); s.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
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
                print(f"{t['id']} [{t['kind']}] {t['title']}\n   範囲：{', '.join(t['scope']) or '（未定）'}\n   確かめ：{' / '.join(t['done_when']) or '（未定）'}")
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
        t = set_contract(a.id, a.kind, a.scope.split(",") if a.scope is not None else None, a.done_when)
        print(json.dumps(brief(t), ensure_ascii=False))
    elif a.cmd == "done":
        done(a.id, a.pr, a.file)
        print(f"✓ 済み：{a.id}{'（ファイル）' if a.file else ''}")
    elif a.cmd == "park":
        park(a.id, a.why, a.waiting)
        print(f"✓ {'店長待ち' if a.waiting else '止めた'}：{a.id}")
    elif a.cmd == "reopen":
        if a.id not in load():
            raise KeyError(a.id)
        overlay(a.id, status="open", note="開け直した")
    elif a.cmd == "add":
        tid, new = add(a.title, a.why, a.quote, a.kind, a.scope.split(","), a.done_when, a.priority, a.source, local=a.local)
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
