"""AgentBoard の集め係（cxelegy/agentboard の collect.py）を、この機械でまだ動いていなければ裏で起こす hook。

SessionStart・UserPromptSubmit から呼ばれる（HARNESS_V2.md「AgentBoard」）。agentboard を clone していない会話・Windows では何もしない
（PC はタスク スケジューラの AgentBoardCollector が起こす）。会話は止めない：失敗しても黙って終わる。手で起こすときも同じ：
  python3 .claude/hooks/agentboard_start.py
"""
import json
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


def ensure_user_hook(settings=None):
    """クラウドの容器の user の設定（~/.claude/settings.json）にもこの hook を入れる（2026-11-20）。
    いくつもの作業場所を持つ会話は /home/user で始まり、Wishlist の .claude/settings.json が読まれない。
    そのため worker が再起動すると集め係が止まったままだった（11-19 の夜から 27 時間）。
    user の設定は作業場所に関係なく読まれる。クラウドの容器（CLAUDE_CODE_REMOTE_SESSION_ID がある）だけで行い、
    PC や手元の機械の設定には触らない。2 回呼んでも 1 つだけ。"""
    if not os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID"):
        return "skip"
    path = pathlib.Path(settings) if settings else pathlib.Path.home() / ".claude" / "settings.json"
    me = pathlib.Path(__file__).resolve()
    cmd = f'python3 "{me}"'
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return "unreadable"                      # 読めない設定は書き換えない
    hooks = data.setdefault("hooks", {})
    changed = False
    for event in ("SessionStart", "UserPromptSubmit"):
        groups = hooks.setdefault(event, [])
        if any("agentboard_start.py" in h.get("command", "") for g in groups for h in g.get("hooks", [])):
            continue
        groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 10}]})
        changed = True
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return "added" if changed else "present"


def wishlist_dir():
    """site の欄（main・kpi・整理待ち）に使う Wishlist の場所。作業場所が /home/user の会話でも、この hook のある Wishlist を使う"""
    project = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if (project / "harness").is_dir():
        return str(project)
    me = pathlib.Path(__file__).resolve().parents[2]
    return str(me) if (me / "harness").is_dir() else str(project)


def main():
    if os.name == "nt":
        return
    board = find_board()
    if board:
        try:
            ensure_user_hook()
        except Exception:  # noqa: BLE001
            pass
        start(board, wishlist_dir())


if __name__ == "__main__":
    try:
        sys.stdin.read() if not sys.stdin.isatty() else None
    except Exception:  # noqa: BLE001
        pass
    try:
        main()
    except Exception:  # noqa: BLE001
        pass
