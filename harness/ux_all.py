"""ux_check を人 × 幅ごとの小さな回に分けて並列に走らせ、1 回 480 秒以内・切れた回だけやり直し・人ごとに結果を書き出す。
使い方：python harness/ux_all.py [--fast] [--who guest,test-a] [--widths 1400,390] [--jobs 4]
結果：harness/shots/ux_<回の名前>.txt と ux_summary.txt。回線切れ（点検の行が出ない・時間切れ・ws_closed）だけ 1 回やり直す。"""
import argparse, concurrent.futures as cf, pathlib, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "shots"
LIMIT = 480
BUDGET = 540   # 全体の上限（秒）。呼び出し側の 600 秒の道具より手前で、終わった回の ✓/✗ を必ず出す
WHO = "guest,test-a,test-b,test-c"


def units(who, widths):
    u = [(f"{w_}-{x}", ["--part", "who", "--who", w_, "--widths", str(x)]) for w_ in who for x in widths]
    return u + [("global", ["--part", "global", "--widths", ",".join(map(str, widths))])]


def run(name, args, extra, deadline=None):
    cmd = [sys.executable, str(HERE / "ux_check.py"), *args, *extra]
    done, out = False, ""
    for _try in range(2):
        left = LIMIT if deadline is None else min(LIMIT, deadline - time.time())
        if left < 20:   # 全体の持ち時間が尽きた：始めずに「走らなかった」と出す
            break
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=left)
            out = r.stdout + r.stderr
            done = "点検：✗" in out
        except subprocess.TimeoutExpired as ex:
            out = (ex.stdout or b"").decode("utf-8", "replace") if isinstance(ex.stdout, bytes) else (ex.stdout or "")
            done = False
        cut = (not done) or "ws_closed" in out or "Execution context" in out
        if not cut:
            break
    out += "" if done else f"\n[ux_all] {name}：持ち時間（1 回 {LIMIT} 秒・全体 {BUDGET} 秒）以内に終わらなかった\n"
    OUT.mkdir(exist_ok=True)
    (OUT / f"ux_{name}.txt").write_text(out, encoding="utf-8")
    bad = [l for l in out.splitlines() if l.startswith("✗")]
    return name, done, bad


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default=WHO)
    ap.add_argument("--widths", default="1400,390")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--budget", type=int, default=BUDGET)
    a = ap.parse_args(argv)
    extra = ["--fast"] if a.fast else []
    us = units(a.who.split(","), [int(x) for x in a.widths.split(",")])
    lines, fails, undone = [], 0, 0
    deadline = time.time() + a.budget
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for f in cf.as_completed([ex.submit(run, u[0], u[1], extra, deadline) for u in us]):   # 終わった順に出す（途中でも見える）
            name, done, bad = f.result()
            fails += len(bad)
            undone += not done
            new = [f"{'✓' if done and not bad else '✗'} {name}：" + (f"✗ {len(bad)} 件" if bad else "崩れなし") + ("" if done else "・最後まで走らなかった")]
            new += ["    " + b[:220] for b in bad]
            lines += new
            print("\n".join(new), flush=True)
    lines.append(f"全体：✗ {fails} 件・最後まで走らなかった回 {undone}（回の数 {len(us)}）")
    s = "\n".join(lines)
    print(lines[-1], flush=True)
    (OUT / "ux_summary.txt").write_text(s + "\n", encoding="utf-8")
    return 1 if fails or undone else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
