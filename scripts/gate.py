"""後台のゲート：仕事があるか、Claude（AI）が要るかを、プログラムだけで決める。

Claude の定時タスクは、仕事がなくても起きるたびにトークンを使う。そこで GitHub Actions（無料）が先に見て、
  ・AI の要らない仕事（小元素の補完）はその場で Python で済ませる
  ・AI が要る仕事（AI 編集・写真から愿望）は、仕事があるときだけ Claude の定時タスクを API で起こす
ようにする。同じ仕事で 2 回起こさないように、仕事の中身の指紋（sig）を state/gate.json に残す。

  python scripts/gate.py check    仕事を調べて state/gate.json と GITHUB_OUTPUT（emblem=true など）に書く
  python scripts/gate.py fire     AI が要る仕事があって、まだ起こしていなければ Claude を起こす（トークンがなければ記録だけ）

Claude を起こすには、定時タスクごとの API トークンが要る（claude.ai/code/routines → タスク → 編集 → API の触发器 → 令牌）：
  AI 編集     ROUTINE_TOKEN_EDIT（既存の Secret ROUTINE_FIRE_TOKEN をそのまま渡す）
  写真から愿望 ROUTINE_TOKEN_PHOTOS（Secret ROUTINE_FIRE_TOKEN_PHOTOS）
"""

import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import urllib.request
import zoneinfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runlog  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "gate.json"
INBOX = ROOT / "inbox"
REFIRE_HOURS = 6   # 同じ仕事（指紋が同じ）では、この時間のあいだ起こし直さない

# AI が要る仕事 → (定時タスクの id, トークンの環境変数, 名前)
ROUTINES = {
    "edit": ("trig_01Ly92RcW35cBwZ9amWZr11j", "ROUTINE_TOKEN_EDIT", "AI 編集"),
    "photos": ("trig_015cccBEWhcv2bB47qVg7xx5", "ROUTINE_TOKEN_PHOTOS", "写真から愿望"),
}


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _sig(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def load(path=None):
    try:
        return json.loads(pathlib.Path(path or STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data, path=None):
    p = pathlib.Path(path or STATE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def edit_work(inbox=INBOX, tz="Asia/Shanghai", today=None):
    """今日（出刊の日付の時区）の inbox で、edit.json の _covered より新しい記事がある版面 → {名前: 未編集の件数}。
    AI 編集の定時タスクの「何も変えずに終わり」の条件と同じ。"""
    today = today or _now().astimezone(zoneinfo.ZoneInfo(tz)).date().isoformat()
    path = pathlib.Path(inbox) / f"{today}.json"
    if not path.exists():
        return {}
    try:
        blocks = json.loads(path.read_text(encoding="utf-8")).get("items", [])
        edit_path = path.with_name(f"{today}.edit.json")
        covered = (json.loads(edit_path.read_text(encoding="utf-8")) if edit_path.exists() else {}).get("_covered") or {}
    except ValueError:
        return {}
    out = {}
    for b in blocks:
        n, c = len(b.get("entries") or []), int(covered.get(b.get("name")) or 0)
        if n > c:
            out[b["name"]] = n - c
    return out


def photo_work(inbox=INBOX):
    """書き出された写真（inbox/photos/<id>.json）→ id のリスト。"""
    return sorted(p.stem for p in (pathlib.Path(inbox) / "photos").glob("*.json"))


def emblem_work():
    """小元素：目標に届いていない版面で、今やってよいもの（24 時間以内の失敗は除く）→ 名前のリスト。AI は要らない。"""
    import emblem_fill
    items = emblem_fill.load_items()
    prog = emblem_fill.sync_progress(emblem_fill.load_progress(), items)
    return [i["name"] for i in emblem_fill.due(prog, items, _now().isoformat(timespec="seconds"))]   # EMBLEM_RETRY_NOW=1 なら 24 時間を待たない


def check(tz="Asia/Shanghai", path=None):
    """→ {job: {need, claude, why, items, sig}}。state/gate.json に書く。"""
    edit = edit_work(tz=tz)
    photos = photo_work()
    emblem = emblem_work()
    jobs = {
        "emblem": {"need": bool(emblem), "claude": False, "items": emblem[:20],
                   "why": f"足りない {len(emblem)} 版面（Actions で Python が埋める）" if emblem else "全部そろっているか、24 時間以内に失敗したものだけ"},
        "edit": {"need": bool(edit), "claude": True, "items": sorted(edit),
                 "why": f"未編集の記事 {sum(edit.values())} 件（{len(edit)} 版面）" if edit else "今日の新着はすべて編集済み"},
        "photos": {"need": bool(photos), "claude": True, "items": photos,
                   "why": f"写真 {len(photos)} 枚" if photos else "受付の写真なし"},
    }
    for k, j in jobs.items():
        j["sig"] = _sig([k, edit if k == "edit" else photos if k == "photos" else emblem])
    data = load(path)
    prev = data.get("jobs") or {}
    changed = any((prev.get(k) or {}).get("sig") != j["sig"] or (prev.get(k) or {}).get("need") != j["need"] for k, j in jobs.items())
    data["checked"] = _now().isoformat(timespec="seconds")
    data["jobs"] = {k: {**prev.get(k, {}), **v} for k, v in jobs.items()}
    data["changed"] = changed   # 判断が前と同じなら、ワークフローはゲートの記録だけのコミットをしない
    save(data, path)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            for k, j in jobs.items():
                f.write(f"{k}={'true' if j['need'] else 'false'}\n")
            f.write(f"changed={'true' if changed else 'false'}\n")
    return data


def _post(url, token):
    req = urllib.request.Request(url, data=b"{}", method="POST", headers={
        "Authorization": f"Bearer {token}", "anthropic-beta": "experimental-cc-routine-2026-04-01",
        "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def fire(path=None, post=_post, env=None):
    """AI が要る仕事があって、同じ指紋でまだ起こしていなければ、Claude の定時タスクを起こす。
    → {job: 結果の文}。トークンがなければ起こさず「トークン未設定」と残す（定時のほうで拾われる）。"""
    env = os.environ if env is None else env
    data = load(path)
    now = _now()
    results = {}
    for job, (rid, var, name) in ROUTINES.items():
        j = (data.get("jobs") or {}).get(job) or {}
        if not j.get("need"):
            results[job] = "仕事なし（起こさない）"
            continue
        last = j.get("fired") or {}
        try:
            recent = last.get("sig") == j.get("sig") and now - dt.datetime.fromisoformat(last["at"]) < dt.timedelta(hours=REFIRE_HOURS)
        except (KeyError, ValueError):
            recent = False
        if recent:
            results[job] = "同じ仕事で起こし済み"
            continue
        token = env.get(var)
        if not token:
            results[job] = "トークン未設定（定時を待つ）"
            continue
        try:
            post(f"https://api.anthropic.com/v1/claude_code/routines/{rid}/fire", token)
            j["fired"] = {"at": now.isoformat(timespec="seconds"), "sig": j.get("sig")}
            results[job] = "Claude を起こした"
        except Exception as e:   # 起こせなくても、定時のほうで拾われる
            results[job] = f"起こせなかった：{str(e)[:80]}"
        data.setdefault("jobs", {})[job] = j
    data["fired"] = {"at": now.isoformat(timespec="seconds"), "results": results}
    save(data, path)
    return results


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        data = check()
        for k, j in data["jobs"].items():
            print(f"{k:<7} {'仕事あり' if j['need'] else '仕事なし'}{'（Claude）' if j['claude'] and j['need'] else ''}：{j['why']}")
        if data.get("changed"):   # 判断が変わったときだけ 1 行（2 時間ごとに同じ行を積まない）
            runlog.add("gate", "判断：" + " · ".join(f"{k} {'あり' if j['need'] else 'なし'}（{j['why']}）" for k, j in data["jobs"].items()),
                       "info", jobs={k: j["need"] for k, j in data["jobs"].items()})
    elif cmd == "fire":
        res = fire()
        for k, v in res.items():
            print(f"{k:<7} {v}")
        woke = [ROUTINES[k][2] for k, v in res.items() if v == "Claude を起こした"]
        runlog.add("gate", ("Claude を起こした：" + "・".join(woke)) if woke else "Claude は起こさなかった（" + " / ".join(f"{ROUTINES[k][2]} {v}" for k, v in res.items()) + "）",
                   "ok" if woke else "info", results=res)
    else:
        sys.exit("使い方：gate.py check | fire")


if __name__ == "__main__":
    main()
