"""1 台の PC で重い仕事を 1 つずつ（ハーネス v2）：CI のコンテナ・ブラウザーの点検が 2 つ同時に走ると CPU を取り合って両方遅くなる。

  python harness/lock.py ci -- bash harness/ci_local.sh            # 鍵が空くまで待って（既定 20 分）、取って、命令を流し、返す
  python harness/lock.py browser --wait 600 -- python harness/shots.py …

鍵は D:/Claude/hf/state/locks/<名前>/（mkdir は同時に 1 人しか成功しない）。持ち主が落ちて残った鍵は 30 分で古い扱いにして取り直す。
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


def acquire(name, wait=1200, stale=1800, state=None, sleep=time.sleep, clock=time.time, poll=5):
    d = (state or q.state_dir()) / "locks" / name
    d.parent.mkdir(parents=True, exist_ok=True)
    end = clock() + wait
    while True:
        try:
            d.mkdir()
            (d / "owner.json").write_text(json.dumps({"pid": os.getpid(), "since": clock()}), encoding="utf-8")
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


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if "--" not in a or not a or a[0].startswith("-"):
        print(__doc__)
        return 2
    i = a.index("--")
    opts, cmd = a[1:i], a[i + 1:]
    wait = float(opts[opts.index("--wait") + 1]) if "--wait" in opts else 1200
    stale = float(opts[opts.index("--stale") + 1]) if "--stale" in opts else 1800
    d = acquire(a[0], wait, stale)
    if d is None:
        print(f"✗ 鍵 {a[0]} が {int(wait)} 秒空かなかった")
        return BUSY
    try:
        return subprocess.call(cmd)
    finally:
        release(d)


if __name__ == "__main__":
    sys.exit(main())
