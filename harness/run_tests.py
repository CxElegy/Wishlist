"""試験をファイルごとに別のプロセスで並列に流す（CI・pre-push で同じもの）。

2026-11-07，店長「失敗をなくして、待たせないで」：1 つのプロセスで全部流すと、前の試験が残した
render.AUTH_DB などで後の試験の結果が変わり（手元では緑・CI だけ赤）、時間も 7〜8 分かかった。

    python harness/run_tests.py            # 全部
    python harness/run_tests.py test_gate  # 名前を指定
"""
import concurrent.futures as cf
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
TIMEOUT = 900


def one(name):
    t = time.time()
    try:
        p = subprocess.run([sys.executable, "-m", "unittest", f"tests.{name}"], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
        return name, p.returncode, p.stdout + p.stderr, time.time() - t
    except subprocess.TimeoutExpired:
        return name, 1, f"FAIL: {name}（{TIMEOUT} 秒で打ち切り）\n", time.time() - t


def main(argv):
    names = argv or sorted(p.stem for p in (ROOT / "tests").glob("test_*.py"))
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=int(os.environ.get("TEST_JOBS") or os.cpu_count() or 2)) as ex:
        res = list(ex.map(one, names))
    bad = [r for r in res if r[1] != 0]
    ran = sum(int(m) for r in res for m in re.findall(r"^Ran (\d+) test", r[2], re.M))
    for name, _, out, _ in bad:
        print(f"\n===== {name} =====")
        blocks = re.findall(r"^(?:FAIL|ERROR): .*?(?=^={70}|^-{70}\nRan )", out, re.M | re.S)
        print("\n".join(b[:1500] for b in blocks) or out[-1500:])
    slow = sorted(res, key=lambda r: -r[3])[:3]
    print(f"{len(names)} ファイル・{ran} 試験・{time.time() - t0:.0f} 秒・落ちた {len(bad)} ファイル"
          f"（遅い順：{'、'.join(f'{r[0]} {r[3]:.0f}秒' for r in slow)}）")
    if bad:
        print("落ちた：" + " ".join(r[0] for r in bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
