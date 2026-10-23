"""コンパクトの直前に、いまの状態を PROGRESS.md の末尾に書く（HARNESS.md「長い会話とコンパクト」）。

書くもの：時刻・BACKLOG.md の進行中／あなた待ち・最近の main の合併 5 件・まだ合併していない作業の枝。失敗しても会話は止めない。
"""
import datetime as dt
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]


def git(*a):
    try:
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def main():
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    back = (ROOT / "BACKLOG.md").read_text(encoding="utf-8") if (ROOT / "BACKLOG.md").exists() else ""
    rows = [l.strip() for l in back.splitlines() if re.match(r"\s*- \[[~?]\]", l)]
    lines = [f"\n## コンパクトの前の記録 {now}（自動）", "- 進行中・あなた待ち："]
    lines += [f"  {r[:200]}" for r in rows] or ["  なし"]
    lines.append("- 最近の main：")
    lines += [f"  {l}" for l in git("log", "--oneline", "-5", "origin/main").splitlines()]
    st = git("status", "--short")
    lines.append(f"- 作業ツリー（{git('branch', '--show-current')}）：" + ("変更なし" if not st else ""))
    lines += [f"  {l}" for l in st.splitlines()[:15]]
    p = ROOT / "PROGRESS.md"
    if not p.exists():
        p.write_text("# 進み具合の記録（HARNESS.md「長い会話とコンパクト」）\n", encoding="utf-8")
    with p.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        pass
