"""収集の控えの時計：GitHub の定時（digest.yml の cron）は混むと抜ける（2026-10-21〜22：12 回のはずが 5 回、最大 4 時間あいた）。
後台作業（background.yml）は Supabase pg_cron が毎時 17 分に必ず起こすので、その中でこれを見て、
最後の収集（state/log/collect.json の、終わった行＝secs つきの最新の時刻）から STALE_MIN 分以上たっていたら
digest.yml を workflow_dispatch で起こす（GITHUB_TOKEN でも workflow_dispatch は別のワークフローを起こせる）。

収集が走っている最中・並んでいる最中、または RECENT_MIN 分以内に始まった回（起こした回も含む）があるときは起こさない
（digest.yml の concurrency は 1 本待ち。並んでいる回があるときに起こすと、並んでいた回が取り消されて入れ替わるだけ）。

  python scripts/collect_watch.py           判断して、必要なら起こす（GH_TOKEN が要る）
  python scripts/collect_watch.py --dry     判断だけ（起こさない）
"""

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runlog  # noqa: E402

STALE_MIN = 150   # 収集は 2 時間ごと（1 回 5〜12 分）。これより空いたら定時が抜けている
RECENT_MIN = 60   # この分数以内に始まった収集の回があれば待つ（push の前・反映の途中かもしれない）。
                  # digest.yml の timeout-minutes（40）より長く：起こした回がすぐ落ちても・40 分で切れ続けても、
                  # 後台作業（:17 pg_cron・:47 GitHub・収集が終わるたびの workflow_run）のたびに起こし直さない＝1 時間に 1 回まで
WORKFLOW = "digest.yml"
BUSY = {"queued", "in_progress", "waiting", "requested", "pending"}


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _at(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def last_collect(log_dir=None):
    """最後に収集が終わった時刻（secs つきの行の at）。記録がなければ None。"""
    ats = [t for t in (_at(r.get("at")) for r in runlog.load("collect", log_dir) if "secs" in r) if t]
    return max(ats) if ats else None


def decide(last, runs, now=None, stale_min=STALE_MIN, recent_min=RECENT_MIN):
    """→ (起こすか, 理由)。last = 最後の収集の時刻（None = 記録なし）、runs = digest.yml の最近の回
    （gh run list の {status, createdAt}。None = 読めなかった）。"""
    now = now or _now()
    if last is not None:
        mins = int((now - last).total_seconds() // 60)
        if mins < stale_min:
            return False, f"最後の収集は {mins} 分前（{stale_min} 分まで待つ）"
        gap = f"最後の収集から {mins} 分"
    else:
        gap = "収集の記録がない"
    if runs is None:
        return False, f"{gap}だが、収集の回の様子が読めない（起こさない）"
    for r in runs:
        if r.get("status") in BUSY:
            return False, f"{gap}・収集の回が{'走っている' if r.get('status') == 'in_progress' else '並んでいる'}（起こさない）"
        t = _at(r.get("createdAt"))
        if t and now - t < dt.timedelta(minutes=recent_min):
            return False, f"{gap}・{int((now - t).total_seconds() // 60)} 分前に始まった回がある（待つ）"
    return True, f"{gap}（定時が抜けた）→ 収集を起こす"


def gh_runs(run=subprocess.run, limit=10, workflow=WORKFLOW, fields="status,createdAt,event"):
    """digest.yml（workflow）の最近の回（gh run list）。読めなければ None。"""
    try:
        out = run(["gh", "run", "list", "--workflow", workflow, "--limit", str(limit), "--json", fields],
                  capture_output=True, text=True, timeout=60)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def kick(run=subprocess.run, workflow=WORKFLOW, inputs=None):
    """digest.yml（workflow）を workflow_dispatch で起こす（inputs = {名前: 値} は -f で渡す）。→ (できたか, エラーの文)"""
    args = ["gh", "workflow", "run", workflow] + [a for k, v in (inputs or {}).items() for a in ("-f", f"{k}={v}")]
    try:
        out = run(args, capture_output=True, text=True, timeout=60)
        return out.returncode == 0, (out.stderr or out.stdout or "").strip()[:120]
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)[:120]


def main(argv=None, run=subprocess.run, log_dir=None, now=None):
    """→ (起こすべきか, 起こしたか, 理由)。GITHUB_OUTPUT に kicked（起こした）と tried（起こそうとした・回の様子が読めなかった）。
    tried のときは state/log/gate.json に 1 行書くので、ワークフローはそれを提交する（起こせない・読めないが続いても管理ページ・ライブログに出る）。
    同じ失敗が続くときは、前の行と同じ理由なら書き足さない（毎時のコミットを増やさない）。"""
    argv = sys.argv[1:] if argv is None else argv
    dry = "--dry" in argv
    now = now or _now()
    last = last_collect(log_dir)
    stale = last is None or now - last >= dt.timedelta(minutes=STALE_MIN)
    runs = gh_runs(run) if stale else []   # 新しいうちは gh を呼ばない
    due, why = decide(last, runs, now)
    kicked = tried = False
    if not dry and (due or (stale and runs is None)):
        err = "gh run list が読めない"
        if due:
            kicked, err = kick(run)
            why += "" if kicked else f"・起こせなかった：{err}"
        prev = next((r for r in reversed(runlog.load("gate", log_dir)) if "collect_kick" in r), None)
        same = not kicked and prev and not prev.get("collect_kick") and prev.get("kick_err") == err
        if not same:
            runlog.add("gate", "収集の控えの時計：" + why, "warn" if kicked else "error", log_dir=log_dir,
                       collect_kick=kicked, **({} if kicked else {"kick_err": err}))
            tried = True
    print(why)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"kicked={'true' if kicked else 'false'}\ntried={'true' if tried else 'false'}\n")
    return due, kicked, why


if __name__ == "__main__":
    main()
