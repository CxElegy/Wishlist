"""main へ push する共通の道具（全部の workflow・AI 編集の手順がこれを通す。2026-11-05 全体点検 本 1 ①）。

前は workflow ごとに「3 回・5/10/15 秒」の輪を持ち、負けると黙って exit 0（library・photo_cache）や、
依頼を先に done にしてから push に負けてユーザーの設定変更が消えた（requests）。

  python scripts/push_main.py [--regen CMD] [--soft] [--tries 6]

- 呼ぶ前に自分の分をコミットしておく。pull_rebase（-X theirs・modify/delete を解く・--autostash）→ push を最大 6 回、
  間は 2^i 秒＋揺らぎ（ほかの係と同じ間隔でぶつからない）。
- --regen CMD：rebase で origin/main から新しい提交が入ったときだけ CMD（網页の再生成）を走らせ docs を最後のコミットに畳む
  （提交を増やさない）。何も入らなければ作り直さない（呼ぶ前に作った網页のまま。前は毎回 2 度作っていた）。
  5・6 回目は再生成を飛ばしデータだけ push し、render.yml を起こして網页を作り直させる
  （ほかの render が走っている・並んでいる、自分が render のときは起こさない：cancel-in-progress で走っている render を切らない）。
- push の前に items.yaml が yaml として読めるか確かめる（壊れた items.yaml は全部の workflow を止める）。
- 非 fast-forward（先を越された）以外の失敗（403 など）は待たずに失敗。
- 失敗の終わり方：既定は exit 1（呼んだ回が赤になる）。--soft は ::warning:: を出して exit 0。
"""
import argparse
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pull_rebase  # noqa: E402

RACE = ("non-fast-forward", "fetch first", "[rejected]", "failed to push some refs", "cannot lock ref", "stale info")


def git(*a, timeout=120):
    try:
        return subprocess.run(["git", *a], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(e.cmd, 124, "", f"timeout {timeout}s")


def yaml_ok():
    try:
        import yaml
    except ImportError:   # pip を入れない回（photo_cache）：items.yaml を触らないので確かめない
        return True
    if not os.path.exists("items.yaml"):
        return True
    try:
        yaml.safe_load(open("items.yaml", encoding="utf-8"))
        return True
    except yaml.YAMLError as e:
        print(f"items.yaml が読めない：push しない：{e}", file=sys.stderr)
        return False


def regen(cmd):
    r = subprocess.run(cmd, shell=True)
    if r.returncode:
        print(f"再生成に失敗（{r.returncode}）：データだけ push する", file=sys.stderr)
        return False
    git("add", "docs")
    if git("diff", "--cached", "--quiet").returncode:
        mine = git("rev-list", "--count", "origin/main..HEAD").stdout.strip() not in ("", "0")
        if mine:   # 自分のまだ push していない提交に畳む（提交を増やさない）
            git("-c", "core.editor=true", "commit", "-q", "--amend", "--no-edit")
        else:      # 自分の提交が無い（データに変化なし）：push 済みの提交を書き換えない
            git("commit", "-q", "-m", "重新生成网页（取り込み後）")
    return True


def render_busy():
    """自分が render.yml か、ほかの render.yml の回が走っている・並んでいる（その回が最新を取り込んで作り直す）。"""
    if "/render.yml@" in os.environ.get("GITHUB_WORKFLOW_REF", ""):
        return True
    try:
        r = subprocess.run(["gh", "run", "list", "--workflow", "render.yml", "--limit", "5", "--json", "status",
                            "-q", '[.[] | select(.status != "completed")] | length'], capture_output=True, text=True, timeout=60)
        return r.returncode == 0 and r.stdout.strip() not in ("", "0")
    except (OSError, subprocess.TimeoutExpired):
        return False


def dispatch_render():
    if not os.environ.get("GH_TOKEN") or render_busy():
        return
    try:
        subprocess.run(["gh", "workflow", "run", "render.yml", "--ref", "main"], timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"render を起こせなかった：{e}", file=sys.stderr)


def push(regen_cmd=None, tries=6, sleep=time.sleep):
    """push が通れば True。先を越されたときだけ待ってやり直す。"""
    for i in range(tries):
        if i:
            sleep(2 ** i + random.random())
        base = git("merge-base", "HEAD", "origin/main").stdout.strip()
        if pull_rebase.main() != 0:
            print(f"{i + 1} 回目：rebase できなかった", file=sys.stderr)
            continue
        moved = git("rev-parse", "origin/main").stdout.strip() != base   # 取り込みで新しい提交が入った
        late = i >= tries - 2   # 最後の 2 回は再生成しない（再生成の間に先を越され続けるのを断つ）
        stale = bool(regen_cmd) and moved and (late or not regen(regen_cmd))
        if not yaml_ok():
            return False
        r = git("push", "-q", "origin", "HEAD:main")
        if r.returncode == 0:
            if stale:
                dispatch_render()
            return True
        print(f"{i + 1} 回目：push に失敗：{r.stderr.strip()[-300:]}", file=sys.stderr)
        if not any(s in r.stderr for s in RACE):
            return False   # 権限・網の失敗：待っても通らない
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", help="rebase のあとに走らせる網页の再生成（例：python scripts/digest.py render）")
    ap.add_argument("--soft", action="store_true", help="通らなくても exit 0（::warning:: を出す）")
    ap.add_argument("--tries", type=int, default=6)
    a = ap.parse_args(argv)
    if push(a.regen, a.tries):
        return 0
    if a.soft:
        print("::warning::main へ push できなかった（--soft：この回は続ける）")
        return 0
    print("::error::main へ push できなかった")
    return 1


if __name__ == "__main__":
    sys.exit(main())
