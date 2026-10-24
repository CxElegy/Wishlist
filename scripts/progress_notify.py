"""作業の進み具合を Discord へ（2026-10-23，用户定的：何時に何ができたか・どこが変わったかを、PR ごとに Discord で知らせる）。

GitHub Actions（.github/workflows/progress.yml）が呼ぶ。送り先は速報・週報と同じ DISCORD_WEBHOOK_URL（notify.send）。
- pr     ：合併した（closed かつ merged）。PR を出しただけは送らない（2026-10-24）。時刻（日本時間）・題名・本文の最初の数行・変えたファイル数・リンク・画面の更新あり／なし（変えたファイルの一覧を 2 つ目の引数で）
- backlog：main の BACKLOG.md で、あなた待ちになった段（[?]）だけ（2026-10-24，用户定的：合併とあなた待ちだけ）

    python scripts/progress_notify.py pr "<変えたファイル（空白区切り）>" < $GITHUB_EVENT_PATH
    python scripts/progress_notify.py backlog <前の BACKLOG.md> <今の BACKLOG.md>
"""
import datetime as dt
import json
import pathlib
import re
import sys


JST = dt.timezone(dt.timedelta(hours=9))
COLOR = {"opened": 0x5B8DEF, "merged": 0x2EA043, "done": 0x2EA043, "ask": 0xE3B341, "doing": 0x5B8DEF}
ITEM = re.compile(r"^- \[([ x~?])\] (.+)$")
# 網页（Pages）の中身に効かないファイル：文書・点検の道具・ループの指示・テスト・ログ（2026-10-25，用户定的：合併の知らせに「画面の更新あり／なし」）
NO_PAGE = re.compile(r"(\.md$|^\.claude/|^harness/|^tests/|^hermes/|^\.mcp\.json$|^skills-lock\.json$|^state/log/|^\.github/workflows/(progress|ask_remind|ci)\.yml$)")


def page_effect(files):
    """合併で網页が変わるか：'none'（文書・道具だけ）／'maybe'（作りやデータが変わった。公開を確かめてから before_after.py がもう一度知らせる）。"""
    files = [f for f in files if f]
    return "none" if files and all(NO_PAGE.search(f) for f in files) else "maybe"


def now():
    return dt.datetime.now(JST).strftime("%m/%d %H:%M")


def body_lines(body, n=4):
    """PR の本文の最初の数行（見出し・空行・署名は除く）。"""
    out = []
    for line in (body or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "🤖", "https://claude.ai", "---")) or "Generated with" in s:
            continue
        out.append(s[:180])
        if len(out) >= n:
            break
    return "\n".join(out)


def pr_payload(event, files=None):
    pr = event.get("pull_request") or {}
    action = event.get("action")
    if action == "closed" and pr.get("merged"):
        kind, head = "merged", "✅ 合併しました"
    else:   # PR を出しただけは送らない（2026-10-24，用户定的：合併とあなた待ちだけ）
        return None
    desc = body_lines(pr.get("body"))
    if pr.get("changed_files"):
        desc += f"\n（変えたファイル {pr['changed_files']} 個）"
    if files is not None:
        desc = ("🖥 画面の更新：**なし**（文書・点検の道具だけ。開き直しても見た目は変わりません）" if page_effect(files) == "none" else
                "🖥 画面の更新：**あり（の見込み）**。公開まで約 2〜3 分 → 本番で新しくなったのを確かめたら「🟢 公開を確かめました」をもう一度送ります") + "\n" + desc
    return {"embeds": [{"title": f"{head}：{pr.get('title', '')}"[:250], "url": pr.get("html_url"),
                        "description": desc[:3500], "color": COLOR[kind],
                        "footer": {"text": f"{now()}（日本時間）· #{pr.get('number')}"}}]}


def items(text):
    """BACKLOG.md の段 → {名前: (状態, 行)}（名前 = 「—」より前）。"""
    out = {}
    for line in (text or "").splitlines():
        m = ITEM.match(line.strip())
        if m:
            out[m.group(2).split(" — ")[0].strip()] = (m.group(1), m.group(2))
    return out


def backlog_payload(before, after):
    old, new = items(before), items(after)
    rows = []
    for name, (mark, line) in new.items():
        if old.get(name, (None,))[0] == mark:
            continue
        if mark == "?":   # 送るのはあなた待ちだけ（済みは「合併しました」で届く。進行中・追加は送らない：2026-10-24，用户定的）
            rows.append(("ask", "❓ あなた待ち", line))
    if not rows:
        return None
    return {"embeds": [{"title": f"{label}：{line.split(' — ')[0]}"[:250], "description": line[:3500], "color": COLOR[kind],
                        "url": "https://github.com/CxElegy/Wishlist/blob/main/BACKLOG.md",
                        "footer": {"text": f"{now()}（日本時間）· やることの一覧"}} for kind, label, line in rows[:10]]}


def main(argv):
    if argv[:1] == ["pr"]:
        payload = pr_payload(json.load(sys.stdin), argv[1].split() if len(argv) > 1 else None)
    elif argv[:1] == ["backlog"] and len(argv) == 3:
        read = lambda p: pathlib.Path(p).read_text(encoding="utf-8") if pathlib.Path(p).exists() else ""  # noqa: E731
        payload = backlog_payload(read(argv[1]), read(argv[2]))
    else:
        raise SystemExit(__doc__)
    if payload:
        import notify   # 重い（digest を読む）ので送るときだけ。before_after.py は page_effect だけ使う
        notify.send(payload)


if __name__ == "__main__":
    main(sys.argv[1:])
