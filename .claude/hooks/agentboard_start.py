"""AgentBoard の集め係（cxelegy/agentboard の collect.py）を、この機械でまだ動いていなければ裏で起こす hook。

SessionStart・UserPromptSubmit から呼ばれる（HARNESS_V2.md「AgentBoard」）。agentboard を clone していない会話・Windows では何もしない
（PC はタスク スケジューラの AgentBoardCollector が起こす）。会話は止めない：失敗しても黙って終わる。手で起こすときも同じ：
  python3 .claude/hooks/agentboard_start.py
"""
import os
import pathlib
import subprocess
import sys

CANDIDATES = [os.environ.get("AGENTBOARD_DIR") or "", "/home/user/agentboard", str(pathlib.Path.home() / "agentboard")]


def find_board():
    for c in CANDIDATES:
        if c and (pathlib.Path(c) / "collect.py").is_file():
            return pathlib.Path(c)
    return None


def alive(pid):
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    try:   # 使い回された pid を別の命令と取り違えない
        cmd = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes()
        return b"collect.py" in cmd
    except OSError:
        return True


def start(board, project):
    pidf = board / ".collector.pid"
    try:
        if alive(int(pidf.read_text().strip())):
            return "running"
    except (OSError, ValueError):
        pass
    py = sys.executable or "python3"
    cmd = f'"{py}" "{board / "collect.py"}" --loop 5'
    if project and (pathlib.Path(project) / "harness").is_dir():
        cmd += f' --wishlist "{project}"'
    # 見守りの輪：集め係が落ちても 5 秒で起き直す（2026-11-19：worker の再起動のあと 19 分 止まっていた）
    args = ["bash", "-c", f"while :; do {cmd}; sleep 5; done"]
    with open(board / ".collector.log", "ab") as log:
        p = subprocess.Popen(args, cwd=str(board), stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    pidf.write_text(str(p.pid))
    return "started"


def main():
    if os.name == "nt":
        return
    board = find_board()
    if board:
        start(board, os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


if __name__ == "__main__":
    try:
        sys.stdin.read() if not sys.stdin.isatty() else None
    except Exception:  # noqa: BLE001
        pass
    try:
        main()
    except Exception:  # noqa: BLE001
        pass
