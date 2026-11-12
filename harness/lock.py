"""1 台の PC で重い仕事を 1 つずつ（ハーネス v2）：CI のコンテナ・ブラウザーの点検が 2 つ同時に走ると CPU を取り合って両方遅くなる。

  python harness/lock.py ci -- bash harness/ci_local.sh            # 鍵が空くまで待って（既定 20 分）、取って、命令を流し、返す
  python harness/lock.py browser --wait 600 --timeout 900 -- python harness/shots.py …
  python harness/lock.py status                                    # いま誰が鍵を持っているか（JSON）

鍵は D:/Claude/hf/state/locks/<名前>/（mkdir は同時に 1 人しか成功しない）。持ち主が落ちて残った鍵は 30 分で古い扱いにして取り直す。
命令には HF_LOCK_<名前>=1 を渡す（harness/ci_local.sh は自分で ci の鍵を取るので、鍵の中から呼ばれたら取り直さない）。
--timeout <秒>：命令を時間で打ち切る（終了コード 124）。Windows では「timeout」「bash」をそのまま渡すと System32 の timeout.exe・WSL の bash.exe が
動いてしまう（2026-11-12 run 1112b の合併の係が 2 回つまずいた）ので、この 2 つは Git for Windows のものに読み替える。
終了コード：命令のもの。待ち切れなければ 75。
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import q  # noqa: E402

BUSY = 75
TIMED_OUT = 124
GIT_DIRS = ("C:/Program Files/Git", "C:/Program Files (x86)/Git")


def _git_root():
    """Git for Windows の入っている所（bin/bash.exe があるもの）。"""
    g = shutil.which("git")
    cands = []
    if g:
        p = pathlib.Path(g).resolve()
        cands += [p.parent.parent, p.parent.parent.parent]   # …/Git/cmd/git.exe・…/Git/mingw64/bin/git.exe
    cands += [pathlib.Path(d) for d in GIT_DIRS]
    for c in cands:
        if (c / "bin" / "bash.exe").is_file():
            return c
    return None


def resolve(cmd, windows=None, git_root=None):
    """命令の頭を、Windows で取り違えやすいもの（bash・timeout）だけ Git for Windows のものに読み替える。"""
    windows = (os.name == "nt") if windows is None else windows
    if not cmd or not windows:
        return list(cmd)
    head = cmd[0].replace("\\", "/").lower()
    root = git_root if git_root is not None else _git_root()
    if root is None:
        return list(cmd)
    root = pathlib.Path(root)
    if head in ("bash", "bash.exe", "c:/windows/system32/bash.exe"):
        return [str(root / "bin" / "bash.exe")] + list(cmd[1:])
    if head in ("timeout", "timeout.exe", "c:/windows/system32/timeout.exe"):
        return [str(root / "usr" / "bin" / "timeout.exe")] + list(cmd[1:])
    return list(cmd)


def acquire(name, wait=1200, stale=1800, state=None, sleep=time.sleep, clock=time.time, poll=5, who=""):
    d = (state or q.state_dir()) / "locks" / name
    d.parent.mkdir(parents=True, exist_ok=True)
    end = clock() + wait
    while True:
        try:
            d.mkdir()
            (d / "owner.json").write_text(json.dumps({"pid": os.getpid(), "since": clock(), "who": who, "cwd": os.getcwd().replace("\\", "/")}), encoding="utf-8")
            return d
        except FileExistsError:
            o = q._read(d / "owner.json") or {}
            try:
                since = o.get("since") or d.stat().st_mtime
            except OSError:
                continue   # ちょうど返された
            if clock() - since > stale:
                shutil.rmtree(d, ignore_errors=True)
                continue
        if clock() >= end:
            return None
        sleep(poll)


def release(d):
    shutil.rmtree(d, ignore_errors=True)


def status(state=None, clock=time.time):
    out = {}
    root = (state or q.state_dir()) / "locks"
    for d in sorted(root.glob("*")) if root.is_dir() else []:
        o = q._read(d / "owner.json") or {}
        out[d.name] = {**o, "age_s": round(clock() - (o.get("since") or clock()))}
    return out


def run(cmd, timeout=None, env=None):
    try:
        return subprocess.call(resolve(cmd), env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"✗ {timeout:.0f} 秒で打ち切った：{' '.join(cmd)[:120]}")
        return TIMED_OUT
    except FileNotFoundError as e:
        print(f"✗ 命令が見つからない：{e}")
        return 127


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")   # cp932 の画面でも ✗ や ♥ で落ちない
        except (AttributeError, ValueError):
            pass
    a = list(sys.argv[1:] if argv is None else argv)
    if a[:1] == ["status"]:
        print(json.dumps(status(), ensure_ascii=False))
        return 0
    if "--" not in a or not a or a[0].startswith("-"):
        print(__doc__)
        return 2
    i = a.index("--")
    opts, cmd = a[1:i], a[i + 1:]
    opt = lambda k, d: float(opts[opts.index(k) + 1]) if k in opts else d   # noqa: E731
    wait, stale, limit = opt("--wait", 1200), opt("--stale", 1800), opt("--timeout", None)
    name = a[0]
    env = {**os.environ, f"HF_LOCK_{name.upper()}": "1"}
    if os.environ.get(f"HF_LOCK_{name.upper()}"):   # もう鍵の中：取り直さない（同じ鍵を 2 回取ると自分を待ってしまう）
        return run(cmd, limit, env)
    d = acquire(name, wait, stale, who=" ".join(cmd)[:120])
    if d is None:
        print(f"✗ 鍵 {name} が {int(wait)} 秒空かなかった（持ち主：{json.dumps(status().get(name, {}), ensure_ascii=False)}）")
        return BUSY
    try:
        return run(cmd, limit, env)
    finally:
        release(d)


if __name__ == "__main__":
    sys.exit(main())
