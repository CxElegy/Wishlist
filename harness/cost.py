"""ハーネス v2 の 1 回の起動で、段ごとにどれだけトークンと時間を使ったか（2026-11-12 run 1112b：17 係・47 分・合併 0 件で、どこに使ったかが見えなかった）。

ワークフローの台本からは係のトークンが見えない。だから回のあとで、主の会話がワークフローの記録（journal.jsonl と agent-*.jsonl）を読ませる：

  python harness/cost.py <ワークフローの記録のフォルダ> --run 1112b            # state/costs.jsonl に 1 回分を足し、表を出す
  python harness/cost.py <フォルダ> --run 1112b --dry                          # 書かずに表だけ

数える物：input・output・cache_creation（新しく読ませた分）・cache_read（使い回し。安い）。「重さ」＝input＋output＋cache_creation。
段（T-NNNN）ごとに足し、係の名前（label の先頭：build・fix・evalF・ship…）ごとにも出す。段でない係（intake・plan・learn など）は「共通」。
summary.json（hb.py summary）は最後の回の段ごとの重さと、合併できた段 1 つあたりの重さを出す。
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import q  # noqa: E402

COMMON = "共通"


def _iso(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def agent_usage(path):
    """1 つの係の記録 → {model, input, output, cache_creation, cache_read, tools, minutes}。同じ message id は 1 回だけ数える。"""
    seen, ts = set(), []
    u = {"model": "", "input": 0, "output": 0, "cache_creation": 0, "cache_read": 0, "tools": 0}
    for line in pathlib.Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        t = _iso(e.get("timestamp") or "")
        if t:
            ts.append(t)
        m = e.get("message")
        if e.get("type") != "assistant" or not isinstance(m, dict):
            continue
        u["model"] = m.get("model") or u["model"]
        u["tools"] += sum(1 for c in m.get("content") or [] if isinstance(c, dict) and c.get("type") == "tool_use")
        if m.get("id") in seen:
            continue
        seen.add(m.get("id"))
        us = m.get("usage") or {}
        u["input"] += us.get("input_tokens", 0)
        u["output"] += us.get("output_tokens", 0)
        u["cache_creation"] += us.get("cache_creation_input_tokens", 0)
        u["cache_read"] += us.get("cache_read_input_tokens", 0)
    u["minutes"] = round((max(ts) - min(ts)).total_seconds() / 60, 1) if ts else 0.0
    return u


def weight(u):
    return u["input"] + u["output"] + u["cache_creation"]


def task_of(label):
    m = re.search(r"T-\d+", label or "")
    return m.group(0) if m else COMMON


def collect(wf_dir):
    """journal.jsonl の label ごとに使った量。[(label, usage)]（始まった順）"""
    d = pathlib.Path(wf_dir)
    rows = []
    for line in (d / "journal.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "started":
            continue
        f = d / f"agent-{e.get('agentId')}.jsonl"
        if f.is_file():
            rows.append((e.get("label") or "", agent_usage(f)))
    return rows


def by_task(rows):
    out = {}
    for label, u in rows:
        t = out.setdefault(task_of(label), {"agents": 0, "weight": 0, "cache_read": 0, "minutes": 0.0, "roles": {}})
        t["agents"] += 1
        t["weight"] += weight(u)
        t["cache_read"] += u["cache_read"]
        t["minutes"] = round(t["minutes"] + u["minutes"], 1)
        role = label.split(":")[0]
        t["roles"][role] = t["roles"].get(role, 0) + weight(u)
    return out


def record(run, tasks, state=None, now=None, results=None):
    """state/costs.jsonl に段ごとに 1 行（run・task・agents・weight・cache_read・minutes・roles・status）。"""
    state = state or q.state_dir()
    status = {}
    for r in results if results is not None else _results(state):
        status[r.get("task")] = r.get("status")
    p = state / "costs.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        for tid, c in sorted(tasks.items()):
            f.write(json.dumps({"t": q.now_iso(now), "run": run, "task": tid, "status": status.get(tid, ""), **c}, ensure_ascii=False) + "\n")


def _results(state):
    p = state / "results.jsonl"
    try:
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def last_run(state=None):
    """summary.json 用：最後の回の段ごとの重さと、合併できた段 1 つあたりの重さ。"""
    state = state or q.state_dir()
    try:
        rows = [json.loads(x) for x in (state / "costs.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return None
    if not rows:
        return None
    run = rows[-1]["run"]
    cur = [r for r in rows if r["run"] == run]
    total = sum(r["weight"] for r in cur)
    shipped = [r for r in cur if r.get("status") in ("merged", "done")]
    return {"run": run, "total_weight": total, "agents": sum(r["agents"] for r in cur), "minutes": round(sum(r["minutes"] for r in cur), 1),
            "shipped": len(shipped), "per_shipped": round(total / len(shipped)) if shipped else None,
            "tasks": [{"task": r["task"], "status": r.get("status", ""), "agents": r["agents"], "weight": r["weight"], "minutes": r["minutes"]} for r in cur]}


def main(argv=None):
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir")
    ap.add_argument("--run", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    rows = collect(a.dir)
    tasks = by_task(rows)
    for label, u in rows:
        print(f"{label:24} {u['model']:22} {u['minutes']:5.1f} 分 道具 {u['tools']:3} 重さ {weight(u):>9,} 使い回し {u['cache_read']:>11,}")
    tot = sum(t["weight"] for t in tasks.values())
    for tid, t in sorted(tasks.items()):
        print(f"{tid:8} 係 {t['agents']:2}  重さ {t['weight']:>9,}（{100 * t['weight'] // max(tot, 1)}%）  {t['minutes']} 分  {t['roles']}")
    print(f"合計 重さ {tot:,}・係 {len(rows)}")
    if not a.dry:
        record(a.run, tasks)
        print(f"✓ {q.state_dir() / 'costs.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
