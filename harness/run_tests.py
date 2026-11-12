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
INFRA = 3   # 終了コード：落ちたのは「負荷で落ちる基盤の不安定」だけ（試験の中身の赤ではない）
# 2026-11-12 run 1112b：PC で 3〜4 の係が Playwright・CI を同時に流し、test_wall_shapes が Page.goto 30 秒切れ（単独の流し直しも同じ負荷の中で赤）。
# ブラウザの起動・ページを開く・つながる所の時間切れ／切断は、試験の中身ではなく PC の負荷。合併の係はこれを分けて、静かになってから流し直す（HARNESS_V2.md）
INFRA_RE = re.compile(r"(?:TimeoutError: (?:Page\.goto|BrowserType\.launch|Browser\.new_page|BrowserContext\.new_page|Page\.wait_for_load_state)|"
                      r"Target (?:page, context or browser|closed)|Browser has been closed|browser has disconnected|net::ERR_|"
                      r"ConnectionResetError|Connection refused|（\d+ 秒で打ち切り）)")
FAIL_RE = re.compile(r"^(?:FAIL|ERROR): .*?(?=^={70}|^-{70}\nRan )", re.M | re.S)


def is_infra(out):
    """落ちた試験の出力が全部、基盤の不安定（上の INFRA_RE）によるものか。assert の赤が 1 つでもあれば False。"""
    blocks = FAIL_RE.findall(out) or [out[-3000:]]
    return all(bool(INFRA_RE.search(b)) and "AssertionError" not in b for b in blocks)


def one(name):
    t = time.time()
    try:
        # 試験の頭で sys.path を足し忘れても、前の試験が足した分に頼らないよう、最初から通しておく
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(str(ROOT / d) for d in ("", "scripts", "harness"))}
        p = subprocess.run([sys.executable, "-m", "unittest", f"tests.{name}"], cwd=ROOT, env=env, capture_output=True,
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
    # 並列で重いときだけ時間で落ちる試験がある（test_ux_journey：単独では緑）。落ちたファイルは 1 回だけ単独で流し直し、
    # 通れば「不安定」と名前を出して失敗に数えない（pytest-rerunfailures と同じ考え。2026-11-08）
    flaky = []
    if bad and len(bad) <= 5:
        again = [one(r[0]) for r in bad]
        flaky = [r[0] for r in again if r[1] == 0]
        bad = [r for r in again if r[1] != 0]
        res = [r for r in res if r[0] not in flaky]
    ran = sum(int(m) for r in res for m in re.findall(r"^Ran (\d+) test", r[2], re.M))
    for name, _, out, _ in bad:
        print(f"\n===== {name} =====")
        blocks = FAIL_RE.findall(out)
        print("\n".join(b[:1500] for b in blocks) or out[-1500:])
    slow = sorted(res, key=lambda r: -r[3])[:3]
    print(f"{len(names)} ファイル・{ran} 試験・{time.time() - t0:.0f} 秒・落ちた {len(bad)} ファイル"
          f"（遅い順：{'、'.join(f'{r[0]} {r[3]:.0f}秒' for r in slow)}）")
    if flaky:
        print("不安定（並列で落ち、単独で通った）：" + " ".join(flaky))
    infra = [r[0] for r in bad if is_infra(r[2])]
    if bad:
        print("落ちた：" + " ".join(r[0] for r in bad))
    if infra:
        print("基盤の不安定（負荷：ブラウザ・つながりの時間切れ）：" + " ".join(infra))
    if bad and len(infra) == len(bad):
        return INFRA
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
