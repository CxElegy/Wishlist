"""ハーネス v2 の心拍と要約（HARNESS_V2.md）。係が止まったことを外から分かるようにする（2026-11-12：係が 7 時間止まっていた）。

ワークフローの台本は時間を測れず、係を止めることもできない。だから係が自分で「まだ動いている」を手元のファイルに書き、
外の見張り（harness/watchdog.ps1）と主の会話がそれを読む。書く先は D:/Claude/hf/state/（HF_STATE で変えられる）。push しない。

  python harness/hb.py beat <役> <段> ["いま何をしているか"]     始めと、大きな区切りごとに（取った印の時刻も更新する）
  python harness/hb.py end <役> <段> [結果]                       終わったとき（見張りの対象から外す）
  python harness/hb.py stale [--minutes 20] [--json]              心拍が N 分ない係（あれば終了コード 1）
  python harness/hb.py result <段> <結果> [--pr URL] [--note …]   段の結果を 1 行（state/results.jsonl）
  python harness/hb.py choice add <段> --url URL --question …     店長に選んでもらう質問（state/pending_choices.json）
  python harness/hb.py choice clear <段>
  python harness/hb.py inbox [--board DIR] [--dir DIR]             店長の書き込みのうち、まだ返事していないもの（AgentBoard の inbox.jsonl）と置かれたファイル
  python harness/hb.py reply <書き込みの t> "返事" [--board DIR]   返事を 1 行（AgentBoard の outbox.jsonl。{t, re, text}）
  python harness/hb.py summary                                    state/summary.json を作る（主の会話とダッシュボードが読むのはこれだけ）
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import q  # noqa: E402

DROP_HOURS = 24   # これより古い心拍は前の回の残り：見張りに出さない


def hb_dir(state=None):
    return (state or q.state_dir()) / "hb"


def _name(role, task):
    return re.sub(r"[^\w.-]+", "_", f"{role}__{task}") + ".json"


def beat(role, task, note="", state=None, now=None):
    now = now or time.time()
    p = hb_dir(state) / _name(role, task)
    cur = q._read(p) or {}
    fresh = not cur or cur.get("ended")
    rec = {"role": role, "task": task, "note": note or cur.get("note", ""), "ts": now, "at": q.now_iso(now),
           "first": now if fresh else cur.get("first", now), "beats": 1 if fresh else cur.get("beats", 0) + 1}
    q._write(p, rec)
    if re.fullmatch(r"T-\d+", task or ""):
        q.touch_claim(task, state, now)
    return rec


def end(role, task, status="done", state=None, now=None):
    now = now or time.time()
    p = hb_dir(state) / _name(role, task)
    cur = q._read(p) or {"role": role, "task": task, "first": now, "beats": 0}
    cur.update(ended=now, status=status, ts=now, at=q.now_iso(now))
    q._write(p, cur)
    return cur


def agents(state=None, now=None):
    """動いている係（終わっていない・24 時間以内）。quiet = 最後の心拍からの分。"""
    now = now or time.time()
    out = []
    for p in sorted(hb_dir(state).glob("*.json")):
        r = q._read(p)
        if not r or r.get("ended") or now - r.get("ts", 0) > DROP_HOURS * 3600:
            continue
        out.append({"role": r.get("role"), "task": r.get("task"), "note": r.get("note", ""), "at": r.get("at"),
                    "quiet": round((now - r["ts"]) / 60, 1), "elapsed": round((now - r.get("first", r["ts"])) / 60, 1),
                    "beats": r.get("beats", 0), "ts": r["ts"]})
    return out


def stale(minutes=20, state=None, now=None):
    return [a for a in agents(state, now) if a["quiet"] >= minutes]


def _jsonl_tail(p, n):
    try:
        lines = pathlib.Path(p).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _append(p, rec):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def result(task, status, pr="", note="", state=None, now=None):
    rec = {"t": q.now_iso(now), "task": task, "status": status, "pr": pr, "note": note}
    _append((state or q.state_dir()) / "results.jsonl", rec)
    return rec


def choices(state=None):
    return q._read((state or q.state_dir()) / "pending_choices.json") or []


def choice_add(task, url, question, state=None, now=None):
    rows = [c for c in choices(state) if c.get("task") != task]
    rows.append({"task": task, "url": url, "question": question, "asked": q.now_iso(now)})
    q._write((state or q.state_dir()) / "pending_choices.json", rows)
    return rows


def choice_clear(task, state=None):
    rows = [c for c in choices(state) if c.get("task") != task]
    q._write((state or q.state_dir()) / "pending_choices.json", rows)
    return rows


BOARD = "D:/Claude/AgentBoard"
INBOX_DIR = "D:/Claude/hf/inbox"


def _jsonl(p):
    return _jsonl_tail(p, 10 ** 6)


def inbox(board=BOARD, dir=INBOX_DIR):
    """{"notes": 返事のまだ無い書き込み [{t, text}], "files": 置かれたファイルのパス}。done/ の中は済み。"""
    board = pathlib.Path(board)
    answered = {o.get("re") for o in _jsonl(board / "outbox.jsonl")}
    notes = [{"t": m.get("t"), "text": m.get("text", "")} for m in _jsonl(board / "inbox.jsonl") if m.get("t") not in answered]
    d = pathlib.Path(dir)
    files = sorted(str(f).replace("\\", "/") for f in d.iterdir() if f.is_file()) if d.is_dir() else []
    return {"notes": notes, "files": files}


def reply(re_t, text, board=BOARD, now=None):
    rec = {"t": int((now or time.time()) * 1000), "re": re_t, "text": text}
    _append(pathlib.Path(board) / "outbox.jsonl", rec)
    return rec


def kpi_excerpt(root=None):
    """harness/kpi/latest.json から、目標を越えた段だけ（経路・段・p50・目標）。"""
    k = q._read((root or q.repo_root()) / "harness" / "kpi" / "latest.json")
    if not k:
        return None
    over = []
    for route, stages in sorted((k.get("boards") or {}).items()):
        for name, s in sorted(stages.items()):
            if isinstance(s, dict) and s.get("ok") is False:
                over.append({"route": route, "stage": name, "p50": s.get("p50"), "target": s.get("target")})
    out = {"at": k.get("at"), "over": over}
    for key in ("pages", "shop"):
        if key in k:
            out[key] = k[key]
    return out


def summary(state=None, root=None, now=None, minutes=20):
    state = state or q.state_dir()
    now = now or time.time()
    tasks = q.load(root, state)
    ag = agents(state, now)
    s = {"at": q.now_iso(now), "ts": now,
         "agents": ag, "stale": [a for a in ag if a["quiet"] >= minutes],
         "queue": q.counts(tasks, state, now),
         "next": [{"id": t["id"], "kind": t.get("kind"), "title": t["title"][:80]} for t in q.ready(tasks, state, now, owner="*")[:5]],
         "waiting": [{"id": t["id"], "title": t["title"][:80], "note": (t.get("notes") or [""])[-1]} for t in tasks.values() if t["status"] == "waiting"],
         "parked": [{"id": t["id"], "title": t["title"][:80], "note": (t.get("notes") or [""])[-1]} for t in tasks.values() if t["status"] == "parked"],
         "results": _jsonl_tail(state / "results.jsonl", 10),
         "choices": choices(state),
         "alerts": _jsonl_tail(state / "alerts.jsonl", 5),
         "kpi": kpi_excerpt(root)}
    q._write(state / "summary.json", s)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("beat"); s.add_argument("role"); s.add_argument("task"); s.add_argument("note", nargs="?", default="")
    s = sub.add_parser("end"); s.add_argument("role"); s.add_argument("task"); s.add_argument("status", nargs="?", default="done")
    s = sub.add_parser("stale"); s.add_argument("--minutes", type=float, default=20); s.add_argument("--json", action="store_true")
    s = sub.add_parser("result"); s.add_argument("task"); s.add_argument("status"); s.add_argument("--pr", default=""); s.add_argument("--note", default="")
    s = sub.add_parser("choice"); s.add_argument("op", choices=["add", "clear", "list"]); s.add_argument("task", nargs="?")
    s.add_argument("--url", default=""); s.add_argument("--question", default="")
    s = sub.add_parser("inbox"); s.add_argument("--board", default=BOARD); s.add_argument("--dir", default=INBOX_DIR)
    s = sub.add_parser("reply"); s.add_argument("re"); s.add_argument("text"); s.add_argument("--board", default=BOARD)
    s = sub.add_parser("summary"); s.add_argument("--minutes", type=float, default=20)
    a = ap.parse_args(argv)
    if a.cmd == "beat":
        r = beat(a.role, a.task, a.note)
        print(f"♥ {a.role} {a.task} {r['at']}")
    elif a.cmd == "end":
        end(a.role, a.task, a.status)
    elif a.cmd == "stale":
        bad = stale(a.minutes)
        if a.json:
            print(json.dumps(bad, ensure_ascii=False))
        else:
            for b in bad:
                print(f"✗ {b['role']} {b['task']}：{b['quiet']} 分 心拍なし（最後「{b['note']}」{b['at']}）")
            print(f"心拍のない係：{len(bad)}")
        return 1 if bad else 0
    elif a.cmd == "result":
        result(a.task, a.status, a.pr, a.note)
    elif a.cmd == "choice":
        if a.op == "add":
            if not (a.task and a.url):
                print("✗ choice add <段> --url URL --question …")
                return 2
            choice_add(a.task, a.url, a.question)
        elif a.op == "clear":
            choice_clear(a.task)
        print(json.dumps(choices(), ensure_ascii=False))
    elif a.cmd == "inbox":
        print(json.dumps(inbox(a.board, a.dir), ensure_ascii=False))
    elif a.cmd == "reply":
        reply(int(a.re) if a.re.lstrip("-").isdigit() else a.re, a.text, a.board)
        print("✓ 返事を書いた")
    elif a.cmd == "summary":
        s = summary(minutes=a.minutes)
        print(f"✓ summary.json：係 {len(s['agents'])}（止まり {len(s['stale'])}）・開いている段 {s['queue']['open']}・店長待ち {s['queue']['waiting']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
