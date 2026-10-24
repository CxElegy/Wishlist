"""ライブラリの控えの時計（2026-10-24）：library.yml の毎時 41 分の定時（お客さまの選んだもの → follows）は GitHub の cron なので抜ける
（2026-10-24 00:41 UTC の回は来ず、01:41 の回は 01:59 に来た）。後台作業（background.yml）は Supabase pg_cron が毎時 17 分に必ず起こすので、
その中で library.yml の最近の回を見て、最後に終わった回（成功）から STALE_MIN 分以上たっていたら workflow_dispatch で起こす（users_only = 番号の引き直しはしない）。

library.py --users は何も変わらなかった回はログに書かない（空回りのコミットを作らない）ので、state/log/library.json ではなく
gh run list の回（成功した回の始まった時刻）で見る。走っている・並んでいる回、RECENT_MIN 分以内に始まった回（失敗した回も）があれば起こさない
（落ち続けても 1 時間に 1 回まで）。選んだものが follows に入るまで：定時が 1 回抜けても 17 分の後台作業で拾う → 2 時間以内。

  python scripts/library_watch.py           判断して、必要なら起こす（GH_TOKEN が要る）
  python scripts/library_watch.py --dry     判断だけ（起こさない）
"""

import datetime as dt
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import collect_watch  # noqa: E402
import runlog  # noqa: E402

WORKFLOW = "library.yml"
STALE_MIN = 80    # 毎時 41 分の定時。これより空いたら定時が抜けている（:17 の後台作業で見る：抜けていれば 96 分）
RECENT_MIN = 30   # library.yml の timeout（15 分）より長く。起こした回がすぐ落ちても毎回起こし直さない
INPUTS = {"users_only": "true"}


def decide(runs, now=None, stale_min=STALE_MIN, recent_min=RECENT_MIN):
    """→ (起こすか, 理由)。runs = library.yml の最近の回（{status, conclusion, createdAt}。None = 読めなかった）。"""
    now = now or collect_watch._now()
    if runs is None:
        return False, "ライブラリの回の様子が読めない（起こさない）"
    for r in runs:
        if r.get("status") in collect_watch.BUSY:
            return False, f"ライブラリの回が{'走っている' if r.get('status') == 'in_progress' else '並んでいる'}（起こさない）"
    oks = [t for t in (collect_watch._at(r.get("createdAt")) for r in runs if r.get("conclusion") == "success") if t]
    if oks:
        mins = int((now - max(oks)).total_seconds() // 60)
        if mins < stale_min:
            return False, f"最後のライブラリの回は {mins} 分前（{stale_min} 分まで待つ）"
        gap = f"最後のライブラリの回から {mins} 分"
    else:
        gap = "成功したライブラリの回がない"
    for r in runs:
        t = collect_watch._at(r.get("createdAt"))
        if t and now - t < dt.timedelta(minutes=recent_min):
            return False, f"{gap}・{int((now - t).total_seconds() // 60)} 分前に始まった回がある（待つ）"
    return True, f"{gap}（定時が抜けた）→ ライブラリ（お客さまの版面）を起こす"


def main(argv=None, run=subprocess.run, log_dir=None, now=None):
    """→ (起こすべきか, 起こしたか, 理由)。GITHUB_OUTPUT に kicked・tried（tried なら state/log/gate.json に 1 行、ワークフローが提交する）。
    同じ失敗が続くときは前の行と同じ理由なら書き足さない。"""
    argv = sys.argv[1:] if argv is None else argv
    dry = "--dry" in argv
    runs = collect_watch.gh_runs(run, workflow=WORKFLOW, fields="status,conclusion,createdAt,event")
    due, why = decide(runs, now)
    kicked = tried = False
    if not dry and (due or runs is None):
        err = "gh run list が読めない"
        if due:
            kicked, err = collect_watch.kick(run, workflow=WORKFLOW, inputs=INPUTS)
            why += "" if kicked else f"・起こせなかった：{err}"
        prev = next((r for r in reversed(runlog.load("gate", log_dir)) if "library_kick" in r), None)
        same = not kicked and prev and not prev.get("library_kick") and prev.get("kick_err") == err
        if not same:
            runlog.add("gate", "ライブラリの控えの時計：" + why, "warn" if kicked else "error", log_dir=log_dir,
                       library_kick=kicked, **({} if kicked else {"kick_err": err}))
            tried = True
    print(why)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"kicked={'true' if kicked else 'false'}\ntried={'true' if tried else 'false'}\n")
    return due, kicked, why


if __name__ == "__main__":
    main()
