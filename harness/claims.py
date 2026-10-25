"""BACKLOG の [~]（取った段）の持ち主を見る（HARNESS.md「持ち主のいない [~]」、2026-10-25）。

[~] の書き方：  - [~] 段の名前 … （開始 2026-10-26 08:45 JST・持ち主 wf_xxx）
係は段を取るとき、持ち主が今動いている Run でない [~]、または最後の書き込み（最終 / 開始）から 60 分たった [~] を取り直してよい。

    python harness/claims.py BACKLOG.md [--live wf_a,wf_b] [--now 2026-10-26T08:45]   # 持ち主のいない [~] を出す（0 でなければ終了コード 1）
"""
import datetime as dt
import re
import sys

JST = dt.timezone(dt.timedelta(hours=9))
STALE_MIN = 60
OWNER = re.compile(r"持ち主 ([\w.-]+)")
STAMP = re.compile(r"(最終|開始)\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})")


def parse(text):
    """[~] の行ごとに {line, step, owner, at}。at は最後の書き込み（最終があればそれ、なければ開始）。時刻がなければ None。"""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.startswith("- [~]"):
            continue
        o = OWNER.search(line)
        at = {k: dt.datetime.fromisoformat(f"{d}T{t}").replace(tzinfo=JST) for k, d, t in STAMP.findall(line)}
        out.append({"line": n, "step": line[6:60], "owner": o.group(1) if o else None, "at": at.get("最終") or at.get("開始")})
    return out


def claimable(c, live, now):
    """次の係が取り直してよいか：持ち主がいない・動いていない・時刻がない・60 分たった、のどれか。動いている持ち主の新しい [~] は飛ばす。"""
    if not c["owner"] or c["owner"] not in live or not c["at"]:
        return True
    return now - c["at"] >= dt.timedelta(minutes=STALE_MIN)


def orphans(text, live, now):
    return [c for c in parse(text) if claimable(c, set(live), now)]


if __name__ == "__main__":
    a = sys.argv[1:]
    live = a[a.index("--live") + 1].split(",") if "--live" in a else []
    now = dt.datetime.fromisoformat(a[a.index("--now") + 1]).replace(tzinfo=JST) if "--now" in a else dt.datetime.now(JST)
    bad = orphans(open(a[0], encoding="utf-8").read(), live, now)
    for c in bad:
        print(f"持ち主のいない [~] 行 {c['line']}（持ち主 {c['owner']}・{c['at']}）：{c['step']}")
    print(f"持ち主のいない [~]：{len(bad)}")
    sys.exit(1 if bad else 0)
