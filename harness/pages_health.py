"""公開（Pages）の健康を数える（2026-11-01 BACKLOG「最優先：Pages 公開の失敗」の物差し）。

    python harness/pages_health.py [--hours 24] [--repo CxElegy/Wishlist]

出す：①標準の「pages build and deployment」の回数・失敗（Source が「GitHub Actions」に切り替わると 0 回になる）
②pages.yml（Pages 公開）の回数・失敗・取り消し ③main への提交の数（生成物 / 人 の別）。
終了コード 1：切り替え後に標準の回がまだある・失敗がある（pages.yml の deploy の continue-on-error を外す前の確認にも使う）。
Settings の Source は API の入口が止められているので、標準の回の有無から読む。
"""
import argparse
import datetime as dt
import json
import subprocess

LEGACY = "pages build and deployment"
OURS = "Pages 公開"


def summarize(runs, now, hours=24):
    """runs: Actions API の workflow_runs。{名前: {n, failure, cancelled}} と切り替わったか。"""
    since = now - dt.timedelta(hours=hours)
    out = {}
    for r in runs:
        at = dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        if at < since or r["name"] not in (LEGACY, OURS):
            continue
        s = out.setdefault(r["name"], {"n": 0, "failure": 0, "cancelled": 0, "last": ""})
        s["n"] += 1
        s["failure"] += r.get("conclusion") == "failure"
        s["cancelled"] += r.get("conclusion") == "cancelled"
        s["last"] = max(s["last"], r["created_at"])
    return out


def verdict(s):
    """(ok, 一行)。標準の回が残っている＝Source は未切り替え。"""
    legacy, ours = s.get(LEGACY), s.get(OURS)
    if legacy:
        return False, "Source は未切り替え（標準の回が %d 回・失敗 %d・最後 %s）。Settings → Pages → Source を GitHub Actions に" % (legacy["n"], legacy["failure"], legacy["last"])
    if not ours:
        return False, "公開の回が 0 回（pages.yml が走っていない）"
    if ours["failure"]:
        return False, "pages.yml の失敗 %d 回" % ours["failure"]
    return True, "切り替え済み・pages.yml %d 回（取り消し %d）・失敗 0" % (ours["n"], ours["cancelled"])


def gh_runs(repo, since):
    """標準の回（event=dynamic）と pages.yml の回だけ取る（全部の回は 1 日 2500 件あり paginate で落ちる）。"""
    runs = []
    for path in ("runs?event=dynamic", "workflows/pages.yml/runs?"):
        out = subprocess.run(["gh", "api", "repos/%s/actions/%s&per_page=100&created=>%s" % (repo, path, since), "--jq", ".workflow_runs[]|{name,created_at,conclusion}"],
                             capture_output=True, text=True, check=True).stdout
        runs += [json.loads(x) for x in out.splitlines() if x.strip()]
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--repo", default="CxElegy/Wishlist")
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    s = summarize(gh_runs(a.repo, (now - dt.timedelta(hours=a.hours)).strftime("%Y-%m-%d")), now, a.hours)
    n = subprocess.run(["git", "log", "origin/main", "--since=%d hours ago" % a.hours, "--format=%an"], capture_output=True, text=True).stdout.split()
    bot = sum(x == "github-actions[bot]" for x in n)
    ok, line = verdict(s)
    print("%s %s\nmain への提交 %d（生成物 %d・人と係 %d）／%d 時間" % ("✓" if ok else "✗", line, len(n), bot, len(n) - bot, a.hours))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
