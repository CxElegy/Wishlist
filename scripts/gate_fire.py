"""AI 編集（Claude の予約）を「記録を先に main へ置いてから」起こす（background.yml・digest.yml が呼ぶ）。

前は gate.py fire が「起こす（POST）→ 記録を書く → あとで push」の順だった。後台作業は小元素の補完を 40 分回したあとに
起こすので、その間に収集（digest.yml）が先に起こして記録を push していても知らず、2 本目を起こした（token が 2 倍・
同じ inbox を 2 つのセッションが編む・edit.json の push がぶつかる）。また push より前に起こすと、AI は
まだ main にない inbox/lib/queue.json を読んだ（T-0005）。

今の順番：
  1. 最新の main に合わせる（git fetch → reset --hard origin/main。呼ぶ前に自分の分は push 済みであること）
  2. gate.check で判断をやり直す（最新の fired・inbox で）
  3. gate.fire(claim=True)：起こしてよい仕事の「起こした」記録だけ書く（POST しない）
  4. 記録を commit して push（rebase しない）。先を越された（non-fast-forward）なら 1 に戻る
     → 相手の記録が見えるので「60 分以内に起こし済み」で起こさない＝2 本目は起きない
  5. push が通ってから gate.send で POST。失敗したら記録を取り消して push（次の回が起こし直せる）
  6. 返ってきた会話の id を記録に足す（できなければそのまま）

    python scripts/gate_fire.py        # 環境変数 GATE_FIRE / GATE_NOW / GATE_NOW_ITEMS / ROUTINE_TOKEN_* は gate.py fire と同じ
"""
import copy
import os
import pathlib
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate  # noqa: E402
import runlog  # noqa: E402

FILES = ("state/gate.json", "state/log/gate.json")
RACE = ("non-fast-forward", "fetch first", "[rejected]", "failed to push some refs", "cannot lock ref", "stale info")
TRIES = 5


def git(repo, *a, timeout=120):
    try:
        return subprocess.run(["git", *a], cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(e.cmd, 124, "", f"timeout {timeout}s")


def sync(repo):
    """origin/main に作業ツリーごと合わせる。CI の使い捨ての checkout の中だけ（手元の作業ツリーを消さない）。"""
    if os.environ.get("GITHUB_ACTIONS") != "true" and not os.environ.get("GATE_FIRE_RESET"):
        raise SystemExit("gate_fire.py は作業ツリーを origin/main に合わせ直す：GitHub Actions の中だけで動く（試験は GATE_FIRE_RESET=1）")
    r = git(repo, "fetch", "-q", "origin", "main")
    if r.returncode:
        raise RuntimeError(f"git fetch に失敗：{r.stderr.strip()[-200:]}")
    r = git(repo, "reset", "-q", "--hard", "origin/main")
    if r.returncode:
        raise RuntimeError(f"git reset に失敗：{r.stderr.strip()[-200:]}")


def commit_push(repo, msg):
    """FILES だけ commit して push。→ "ok" / "race"（先を越された）/ "same"（変わっていない）/ "fail" """
    git(repo, "add", *FILES)
    if git(repo, "diff", "--cached", "--quiet").returncode == 0:
        return "same"
    git(repo, "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-q", "-m", msg)
    r = git(repo, "push", "-q", "origin", "HEAD:main")
    if r.returncode == 0:
        return "ok"
    print(f"push に失敗：{r.stderr.strip()[-300:]}", file=sys.stderr)
    return "race" if any(s in r.stderr for s in RACE) else "fail"


def amend(repo, job, at, change, msg, tries=3, sleep=time.sleep):
    """自分が置いた fired（at が同じ）だけを書き換えて push（取り消し・会話 id の追記）。ほかの仕事・ほかの人の記録は触らない。"""
    for i in range(tries):
        if i:
            sleep(2 ** i + random.random())
        sync(repo)
        data = gate.load()
        j = (data.get("jobs") or {}).get(job) or {}
        if (j.get("fired") or {}).get("at") != at:
            return False   # もう別の記録に変わっている
        change(data, j)
        gate.save(data)
        if commit_push(repo, msg) in ("ok", "same"):
            return True
    return False


def run(repo=".", env=None, post=gate._post, check=None, before_push=None, sleep=time.sleep):
    """→ {job: 結果の文}（起こした仕事は "Claude を起こした…"）。"""
    env = os.environ if env is None else env
    check = check or gate.check
    for i in range(TRIES):
        if i:
            sleep(2 ** i + random.random())
        sync(repo)
        check()
        data = gate.load()
        before = {k: copy.deepcopy((v.get("fired"), ((data.get("fires") or {}).get(gate.day_of(gate._now())) or {}).get(k)))
                  for k, v in (data.get("jobs") or {}).items()}
        res = gate.fire(post=post, env=env, claim=True)
        woke = [k for k, v in res.items() if v.startswith("Claude を起こした")]
        left = [k for k, v in res.items() if "すぐの頼みを残した" in v]
        for k, v in res.items():
            print(f"{k:<7} {v}")
        if not woke and not left:
            return res   # 何も変わらない：記録しない（前の後台作業と同じ）
        if woke:
            runlog.add("gate", "Claude を起こした：" + "・".join(gate.ROUTINES[k][2] for k in woke), "ok", results=res)
        else:
            runlog.add("gate", "Claude は起こさなかった（" + " / ".join(f"{gate.ROUTINES[k][2]} {v}" for k, v in res.items()) + "）", "info", results=res)
        if before_push:
            before_push()
        got = commit_push(repo, "ゲート：AI 編集を起こした（または頼みを残した）")
        if got == "race":
            print(f"{i + 1} 回目：先を越された。最新の記録で判断し直す")
            continue
        if got == "fail":
            print("::warning::ゲートの記録を push できない：起こさない（次の回が見直す）")
            return {k: ("記録を push できなかった：起こさない" if k in woke else v) for k, v in res.items()}
        # 記録は main にある（ほかの回にも見える）。ここで初めて起こす
        for k in woke:
            at = (gate.load().get("jobs") or {}).get(k, {}).get("fired", {}).get("at")
            try:
                out = gate.send(k, post, env)
            except Exception as e:   # noqa: BLE001
                err = str(e)[:80]
                res[k] = f"起こせなかった：{err}"
                print(f"{k:<7} {res[k]}")

                def undo(d, j, k=k, b=before[k]):
                    if b[0]:
                        j["fired"] = b[0]
                    else:
                        j.pop("fired", None)
                    day = gate.day_of(gate._now())
                    f = d.setdefault("fires", {}).setdefault(day, {})
                    f[k] = b[1] if b[1] else 0
                    runlog.add("gate", f"起こせなかった：{gate.ROUTINES[k][2]}（{err}）", "warn")
                amend(repo, k, at, undo, "ゲート：起こせなかったので記録を取り消した", sleep=sleep)
                continue
            resp = gate._resp(out)
            if resp:
                amend(repo, k, at, lambda d, j, r=resp: j["fired"].update(resp=r), "ゲート：会話の id を記録", sleep=sleep)
        return res
    print("::warning::ゲートの記録の push で先を越され続けた：起こさない（次の回が見直す）")
    return {k: "先を越され続けた：起こさない" for k in gate.ROUTINES}


def main():
    run(".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
