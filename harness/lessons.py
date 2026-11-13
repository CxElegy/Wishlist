"""失敗の台帳（HARNESS_V2.md「ハーネス v3」A）。同じ種類の失敗が 3 回たまったら、直す段を出す。

置き場：q.py の取った印・途中の状態と同じ手元の state（D:/Claude/hf/state/lessons.jsonl。HF_STATE で変えられる）。リポジトリには入れない・push しない。
1 行 1 件の JSONL：{t, type, task, what, why_missed}。type は失敗の種類の鍵（例 "ci-redteam-fake402" "visual-band"）。

  python harness/lessons.py add --type K --task T-0004 --what "何が落ちたか" --why-missed "なぜ手元で見つからなかったか"
  python harness/lessons.py list [--type K]
  python harness/lessons.py due [--min 3] [--out DIR]   3 回以上の種類ごとに、直す段の JSON（[] または --out で 1 段 1 ファイル。`q.py add --from-json F.json` にそのまま渡せる）
"""
import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import sys

DUE_MIN = 3
JST = dt.timezone(dt.timedelta(hours=9))


def path():
    return pathlib.Path(os.environ.get("HF_STATE") or "D:/Claude/hf/state") / "lessons.jsonl"


def load(p=None):
    p = p or path()
    out = []
    if p.exists():
        for ln in p.read_text(encoding="utf-8-sig").splitlines():
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("type"):
                out.append(d)
    return out


def add(type_, task="", what="", why_missed="", p=None, now=None):
    type_ = (type_ or "").strip()
    if not type_:
        raise ValueError("type（失敗の種類の鍵）が要る")
    if not what.strip():
        raise ValueError("what（何が落ちたか）が要る")
    rec = {"t": (now or dt.datetime.now(JST)).isoformat(timespec="seconds"), "type": type_, "task": task, "what": what.strip(), "why_missed": why_missed.strip()}
    p = p or path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def due(rows, min_n=DUE_MIN):
    """3 回以上たまった種類 → 直す段の約束（q.py add --from-json の形）。多い順。"""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["type"]].append(r)
    out = []
    for k, rs in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(rs) < min_n:
            continue
        tasks = sorted({r.get("task") for r in rs if r.get("task")})
        whys = [r["why_missed"] for r in rs if r.get("why_missed")]
        out.append({
            "title": f"同じ失敗が {len(rs)} 回：{k}（見つかる仕組みを足す）",
            "why": f"種類 {k} の失敗が {len(rs)} 回（段：{', '.join(tasks) or '不明'}）。手元で見つからなかった理由：{' / '.join(dict.fromkeys(whys))[:400] or '記録なし'}。"
                   f"例：{rs[-1]['what'][:200]}",
            "quote": "", "kind": "fix", "complexity": "normal", "priority": 20, "source": "lessons.py",
            "scope": [], "done_when": [f"種類 {k} の失敗を、push の前に手元（ci_local・self_review・q.py contract --lint など）で見つける検査が 1 つ増え、その検査の試験が通る"],
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add"); s.add_argument("--type", required=True); s.add_argument("--task", default=""); s.add_argument("--what", required=True); s.add_argument("--why-missed", default="")
    s = sub.add_parser("list"); s.add_argument("--type")
    s = sub.add_parser("due"); s.add_argument("--min", type=int, default=DUE_MIN); s.add_argument("--out", help="段ごとに 1 ファイル（q.py add --from-json に渡せる辞書）を書く場所")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "add":
            print(json.dumps(add(a.type, a.task, a.what, a.why_missed), ensure_ascii=False))
        elif a.cmd == "list":
            rows = [r for r in load() if not a.type or r["type"] == a.type]
            for r in rows:
                print(f"{r['t'][:10]} {r['type']} {r.get('task', '')} {r['what']}  ← {r.get('why_missed', '')}")
            c = collections.Counter(r["type"] for r in rows)
            print("合計：" + (", ".join(f"{k}×{n}" for k, n in c.most_common()) or "なし"))
        else:
            got = due(load(), a.min)
            if a.out:
                d = pathlib.Path(a.out)
                d.mkdir(parents=True, exist_ok=True)
                for i, g in enumerate(got):
                    f = d / f"lesson-{i + 1}.json"
                    f.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
                    print(f"✓ {f}  → q.py add --from-json {f}")
            else:
                print(json.dumps(got, ensure_ascii=False, indent=1))
    except ValueError as e:
        print(f"✗ {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
