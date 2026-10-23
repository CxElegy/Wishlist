"""作業の進み具合を Discord へ（2026-10-23，用户定的：何時に何ができたか・どこが変わったかを、PR ごとに Discord で知らせる）。

GitHub Actions（.github/workflows/progress.yml）が呼ぶ。送り先は速報・週報と同じ DISCORD_WEBHOOK_URL（notify.send）。
- pr     ：PR を出した（opened）／合併した（closed かつ merged）。時刻（日本時間）・題名・本文の最初の数行・変えたファイル数・リンク
- backlog：main の BACKLOG.md が変わった。新しく済んだ段（[x]）・あなた待ちになった段（[?]）・進行中になった段（[~]）・一覧に足した段

    python scripts/progress_notify.py pr < $GITHUB_EVENT_PATH
    python scripts/progress_notify.py backlog <前の BACKLOG.md> <今の BACKLOG.md>
"""
import datetime as dt
import json
import pathlib
import re
import sys

import notify

JST = dt.timezone(dt.timedelta(hours=9))
COLOR = {"opened": 0x5B8DEF, "merged": 0x2EA043, "done": 0x2EA043, "ask": 0xE3B341, "doing": 0x5B8DEF}
ITEM = re.compile(r"^- \[([ x~?])\] (.+)$")


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


def pr_payload(event):
    pr = event.get("pull_request") or {}
    action = event.get("action")
    if action == "closed" and pr.get("merged"):
        kind, head = "merged", "✅ 合併しました"
    elif action == "opened":
        kind, head = "opened", "🛠 作業を始めました（PR）"
    else:
        return None
    desc = body_lines(pr.get("body"))
    if pr.get("changed_files"):
        desc += f"\n（変えたファイル {pr['changed_files']} 個）"
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
        if mark == "x":
            rows.append(("done", "✅ 済み", line))
        elif mark == "?":
            rows.append(("ask", "❓ あなた待ち", line))
        elif mark == "~":
            rows.append(("doing", "🔧 進行中", line))
        elif name not in old:
            rows.append(("doing", "📝 一覧に追加", line))
    if not rows:
        return None
    return {"embeds": [{"title": f"{label}：{line.split(' — ')[0]}"[:250], "description": line[:3500], "color": COLOR[kind],
                        "url": "https://github.com/CxElegy/Wishlist/blob/main/BACKLOG.md",
                        "footer": {"text": f"{now()}（日本時間）· やることの一覧"}} for kind, label, line in rows[:10]]}


def main(argv):
    if argv[:1] == ["pr"]:
        payload = pr_payload(json.load(sys.stdin))
    elif argv[:1] == ["backlog"] and len(argv) == 3:
        read = lambda p: pathlib.Path(p).read_text(encoding="utf-8") if pathlib.Path(p).exists() else ""  # noqa: E731
        payload = backlog_payload(read(argv[1]), read(argv[2]))
    else:
        raise SystemExit(__doc__)
    if payload:
        notify.send(payload)


if __name__ == "__main__":
    main(sys.argv[1:])
