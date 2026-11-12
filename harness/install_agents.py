"""係の型（.claude/agents/hw-*.md）を ~/.claude/agents/ に入れる（主の会話が D:/Claude にあり、リポジトリの外なので）。

    python harness/install_agents.py                  # ~/.claude/agents/ に入れる（店長の PC の設定。主の会話が 1 回流す）
    python harness/install_agents.py --dest <フォルダ>  # 別の所へ（試験用）
    python harness/install_agents.py --check [--dest <フォルダ>]   # 同じ中身か。違う・無いなら終了コード 1
"""
import argparse
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parent.parent / ".claude" / "agents"
NAMES = ("hw-read", "hw-edit", "hw-ops", "hw-diag")


def read(p):
    return pathlib.Path(p).read_bytes().replace(b"\r\n", b"\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(pathlib.Path.home() / ".claude" / "agents"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    dest = pathlib.Path(a.dest)
    bad = []
    for n in NAMES:
        s, d = SRC / f"{n}.md", dest / f"{n}.md"
        if a.check:
            if not d.is_file() or read(d) != read(s):
                bad.append(n)
        else:
            dest.mkdir(parents=True, exist_ok=True)
            d.write_bytes(read(s))
            print(f"入れた {d}")
    if a.check:
        for n in bad:
            print(f"違う／無い {dest / (n + '.md')}")
        if not bad:
            print("ok")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
