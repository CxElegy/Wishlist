"""ux_check を人 × 幅ごとの小さな回に分けて並列に走らせ、1 回 480 秒以内・切れた回だけやり直し・人ごとに結果を書き出す。
使い方：python harness/ux_all.py [--fast] [--who guest,test-a] [--widths 1400,390] [--jobs 4]
結果：harness/shots/ux_<回の名前>.txt と ux_summary.txt。回線切れ（点検の行が出ない・時間切れ・ws_closed）だけ 1 回やり直す。"""
import argparse, concurrent.futures as cf, pathlib, re, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "shots"
LIMIT = 480
BUDGET = 540   # 全体の上限（秒）。呼び出し側の 600 秒の道具より手前で、終わった回の ✓/✗ を必ず出す
WHO = "guest,test-a,test-b,test-c"
SB_N = [0, 0]   # 全部の回の合計：本番への REST 読み（python）・ブラウザから本番へ（2026-11-04 egress）


def units(who, widths):
    u = [(f"{w_}-{x}", ["--part", "who", "--who", w_, "--widths", str(x)]) for w_ in who for x in widths]
    return [("global", ["--part", "global", "--widths", ",".join(map(str, widths))])] + u   # 一番長い global を最初に始める（最後だと持ち時間が足りない）


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
    for i, pat in enumerate((r"本番の \S+ への要求 (\d+) 件", r"ブラウザから本番へ (\d+) 件")):
        SB_N[i] += sum(int(x) for x in re.findall(pat, out))
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
    ap.add_argument("--only", default="", help="走らせる回の名前だけ（前の回で「走らなかった」と出たもの。例 test-b-390,test-b-1400）")
    a = ap.parse_args(argv)
    extra = ["--fast"] if a.fast else []
    us = units(a.who.split(","), [int(x) for x in a.widths.split(",")])
    if a.only:
        us = [u for u in us if u[0] in a.only.split(",")]
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
    lines.append(f"本番の Supabase への要求（全部の回の合計）：python の REST 読み {SB_N[0]} 件・ブラウザから {SB_N[1]} 件（写しが空の最初の回が最大。2 回目からは 0 に近い）")
    lines.append(f"全体：✗ {fails} 件・最後まで走らなかった回 {undone}（回の数 {len(us)}）")
    left = [l.split("：")[0][2:] for l in lines if l[:1] == "✗" and "最後まで走らなかった" in l]
    if left:   # 続きの回：次の 1 回でこれだけ走らせる
        lines.append("続き：python harness/ux_all.py" + (" --fast" if a.fast else "") + " --only " + ",".join(left))
    s = "\n".join(lines)
    print("\n".join(lines[-2:] if left else lines[-1:]), flush=True)
    (OUT / "ux_summary.txt").write_text(s + "\n", encoding="utf-8")
    return 1 if fails or undone else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
