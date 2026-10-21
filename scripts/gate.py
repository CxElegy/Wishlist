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
本当に起こすかは GATE_FIRE で決める（background.yml がリポジトリ変数 vars.GATE_FIRE を渡す。
GitHub → Settings → Secrets and variables → Actions → Variables）：
  0           起こさない（判断と記録だけ）
  edit / 未設定  AI 編集だけ起こす（変数がないときの既定）（写真から愿望は自分の定時のまま）
  edit,photos / 1 / all   両方起こす

版面には AI 編集が整理した記事しか載らない（未整理の新着は版面の下の「整理待ち」）ので、
今日の inbox に未整理の記事（_covered より後、または edit.json にない版面）があれば AI 編集を起こす。
同じ仕事（指紋が同じ）は 6 時間起こし直さない。指紋が変わっても、前に起こしてから MIN_GAP_MIN 分は待つ（編集中に重ねて起こさない）。
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
import sitedir  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "gate.json"
INBOX = ROOT / "inbox"
REFIRE_HOURS = 6   # 同じ仕事（指紋が同じ）では、この時間のあいだ起こし直さない
MIN_GAP_MIN = 60   # 前に起こしてからこの分数は、何があっても起こし直さない（AI 編集 1 回 ≈ 20 分、収集は 2 時間ごと）。これを過ぎても仕事が減っていなければ「停滞」
# AI 編集は 1 日 2 回（ユーザーが決めた：日本時間 9:00 と 18:00）。その時刻を過ぎて、その回にまだ起こしていなければ起こす。
# 整理待ちがなければ起こさない。停滞（起こしたのに動かない）の起こし直しは別（MAX_ATTEMPTS）。管理ページのボタン（GATE_FORCE）はいつでも
SLOTS = {"edit": [(9, 0), (18, 0)]}
SLOT_TZ = "Asia/Tokyo"


def last_slot(job, now=None):
    """その仕事のいちばん最近の定時（UTC の datetime）。定時のない仕事は None。"""
    if job not in SLOTS:
        return None
    now = now or _now()
    tz = zoneinfo.ZoneInfo(SLOT_TZ)
    local = now.astimezone(tz)
    cands = [dt.datetime.combine(local.date() - dt.timedelta(days=d), dt.time(h, m), tz) for d in (0, 1) for h, m in SLOTS[job]]
    return max(c for c in cands if c <= now).astimezone(dt.timezone.utc)


def next_slot(job, now=None):
    """その仕事の次の定時（UTC の datetime）。"""
    if job not in SLOTS:
        return None
    now = now or _now()
    tz = zoneinfo.ZoneInfo(SLOT_TZ)
    local = now.astimezone(tz)
    cands = [dt.datetime.combine(local.date() + dt.timedelta(days=d), dt.time(h, m), tz) for d in (0, 1) for h, m in SLOTS[job]]
    return min(c for c in cands if c > now).astimezone(dt.timezone.utc)
MAX_ATTEMPTS = 3   # 停滞のとき、仕事が減らないまま起こし直す回数の上限（超えたら REFIRE_HOURS 待つ。管理ページに「止まっている」と出す）

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
    """今日（出刊の日付の時区）の inbox で、AI 編集がまだ整理していない記事がある版面 → {名前: 未整理の件数}。
    未整理 = edit.json の _covered より後の記事、または edit.json にない版面の全部。版面に載らず「整理待ち」に並んでいるもの。
    AI 編集の定時タスクの「何も変えずに終わり」の条件と同じ。"""
    today = today or _now().astimezone(zoneinfo.ZoneInfo(tz)).date().isoformat()
    path = pathlib.Path(inbox) / f"{today}.json"
    if not path.exists():
        return {}
    try:
        blocks = json.loads(path.read_text(encoding="utf-8")).get("items", [])
        edit_path = path.with_name(f"{today}.edit.json")
        edit = (json.loads(edit_path.read_text(encoding="utf-8")) if edit_path.exists() else {}) or {}
        covered = edit.get("_covered") or {}
    except ValueError:
        return {}
    out = {}
    for b in blocks:
        name, n = b.get("name"), len(b.get("entries") or [])
        # digest.publish と同じ読み方：_covered にない版面は、edit.json にあれば全部編集済み・なければ全部未整理
        c = int(covered[name] or 0) if name in covered else n if name in edit else 0
        if n > c:
            out[b["name"]] = n - c
    return out


def edit_done(inbox=INBOX, tz="Asia/Shanghai", today=None):
    """今日の edit.json の _covered の合計。AI 編集が走って書き直すと増える（新着が来ても減らない）＝「本当に進んだか」の目印。"""
    today = today or _now().astimezone(zoneinfo.ZoneInfo(tz)).date().isoformat()
    try:
        covered = (json.loads((pathlib.Path(inbox) / f"{today}.edit.json").read_text(encoding="utf-8")) or {}).get("_covered") or {}
        return sum(int(v or 0) for v in covered.values())
    except (OSError, ValueError, TypeError):
        return 0


def photo_work(inbox=INBOX):
    """書き出された写真（inbox/photos/<id>.json）→ id のリスト。"""
    return sorted(p.stem for p in (pathlib.Path(inbox) / "photos").glob("*.json"))


def emblem_work():
    """小元素：目標に届いていない版面で、今やってよいもの（RETRY_HOURS 以内の失敗で材料が同じものは除く）→ (名前のリスト, 再挑戦待ち)。
    再挑戦待ち = [(名前, 時刻)]：失敗して、新しい材料も RETRY_HOURS もまだ来ていない版面。AI は要らない。"""
    import emblem_fill
    items = emblem_fill.load_items()
    prog = emblem_fill.sync_progress(emblem_fill.load_progress(), items)
    now = _now().isoformat(timespec="seconds")
    return [i["name"] for i in emblem_fill.due(prog, items, now)], emblem_fill.waiting(prog, items, now)   # EMBLEM_RETRY_NOW=1 なら待たない


def _emblem_why(todo, wait, tz="Asia/Tokyo"):
    parts = []
    if todo:
        parts.append(f"足りない {len(todo)} 版面（Actions で Python が埋める）")
    if wait:
        first = min((t for _, t in wait if t), default="")
        when = dt.datetime.fromisoformat(first).astimezone(zoneinfo.ZoneInfo(tz)).strftime("%H:%M") if first else "?"
        parts.append(f"失敗 {len(wait)} 版面は再挑戦待ち（新しい記事が来たらすぐ、来なくても {when} から）")
    return "・".join(parts) or "全部そろっている"


def check(tz="Asia/Shanghai", path=None):
    """→ {job: {need, claude, why, items, sig}}。state/gate.json に書く。"""
    edit = edit_work(tz=tz)
    photos = photo_work()
    emblem, emblem_wait = emblem_work()
    jobs = {
        "emblem": {"need": bool(emblem), "claude": False, "items": emblem[:20], "waiting": [n for n, _ in emblem_wait],
                   "why": _emblem_why(emblem, emblem_wait)},
        "edit": {"need": bool(edit), "claude": True, "items": sorted(edit),
                 "why": f"整理待ちの記事 {sum(edit.values())} 件（{len(edit)} 版面・AI 編集まで版面に載らない）" if edit else "今日の新着はすべて AI 編集済み"},
        "photos": {"need": bool(photos), "claude": True, "items": photos,
                   "why": f"写真 {len(photos)} 枚" if photos else "受付の写真なし"},
    }
    for k, j in jobs.items():
        j["sig"] = _sig([k, edit if k == "edit" else photos if k == "photos" else emblem])
    # 進み具合の目印（prog：大きくなれば進んだ）。起こしたあとに増えていなければ Claude は動いていない（work_state）
    jobs["edit"]["prog"] = edit_done(tz=tz)
    jobs["photos"]["prog"] = -len(photos)
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


def work_state(j, now=None):
    """ゲートが Claude を起こしたあとの様子（API が 200 を返しただけでは「やった」ことにしない）。→ (状態, 説明)
      none      まだ起こしていない / 仕事がない
      running   起こして MIN_GAP_MIN 分以内：編集中かもしれない
      progress  起こしたあと編集済みの数（prog）が増えた（動いている）
      stalled   起こして MIN_GAP_MIN 分たったのに prog が増えていない（Claude が動いていない）→ 起こし直す
      gave_up   動かないまま MAX_ATTEMPTS 回起こした：REFIRE_HOURS 待って、管理ページで人に知らせる"""
    last = (j or {}).get("fired") or {}
    if not ((j or {}).get("need") or (j or {}).get("items")) or not last.get("at"):
        return "none", ""
    now = now or _now()
    try:
        ago = now - dt.datetime.fromisoformat(last["at"])
    except (ValueError, TypeError):
        return "none", ""
    prog, was = j.get("prog"), last.get("prog")
    mins = int(ago.total_seconds() // 60)
    if was is not None and prog is not None and prog > was:
        return "progress", f"{mins} 分前に起こして、編集済みが {was} → {prog} 件に進んだ"
    if ago < dt.timedelta(minutes=MIN_GAP_MIN):
        return "running", f"{mins} 分前に起こした（編集中のはず）"
    n = int(last.get("attempts") or 1)
    if n >= MAX_ATTEMPTS:
        return "gave_up", f"{n} 回起こしたが仕事が減らない（{mins} 分前が最後）"
    return "stalled", f"{mins} 分前に起こしたが仕事が減っていない"


def _post(url, token):
    req = urllib.request.Request(url, data=b"{}", method="POST", headers={
        "Authorization": f"Bearer {token}", "anthropic-beta": "experimental-cc-routine-2026-04-01",
        "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read(2000).decode("utf-8", "replace")   # 本文に会話の id などが入る：記録して、動いたか調べる手がかりにする


def edit_mode(env=None):
    """管理ページの AI 編集の開関（Supabase edit_control_get()）の mode：run / step / pause。読めなければ run。
    テストや手元では env の EDIT_MODE を優先（ネットに出ない）。"""
    env = os.environ if env is None else env
    if env.get("EDIT_MODE"):
        return env["EDIT_MODE"]
    try:
        import livestatus
        url, key = livestatus._db()
        if not (url and key) or env is not os.environ:
            return "run"
        req = urllib.request.Request(f"{url}/rest/v1/rpc/edit_control_get", method="POST",
                                     data=json.dumps({"p_account": sitedir.NAME}).encode("utf-8"),
                                     headers={"apikey": key, "Content-Type": "application/json"})
        return (json.loads(urllib.request.urlopen(req, timeout=15).read() or b"{}") or {}).get("mode") or "run"
    except Exception:  # noqa: BLE001
        return "run"


def enabled_jobs(flag):
    """GATE_FIRE の値 → 起こしてよい仕事の集合。'1' / 'all' = 全部、'edit' や 'edit,photos' = その仕事だけ、'' / '0' = なし。"""
    flag = str(flag or "").strip().lower()
    if flag in ("", "0", "false", "off", "no"):
        return set()
    if flag in ("1", "true", "all", "on", "yes"):
        return set(ROUTINES)
    return {x.strip() for x in flag.split(",") if x.strip() in ROUTINES}


def _resp(out):
    """_post の返り値（テストでは int のこともある）→ 記録用の短い文字列。"""
    body = out[1] if isinstance(out, tuple) and len(out) > 1 else ""
    try:
        d = json.loads(body)
        return str(d.get("claude_code_session_id") or d.get("session_id") or d.get("id") or d.get("session_url") or "")[:80]
    except (ValueError, AttributeError):
        return str(body)[:80]


def fire(path=None, post=_post, env=None):
    """AI が要る仕事があるとき、Claude の定時タスクを起こす。起こしたあとに仕事が減ったかを次の回で見て（work_state）、
    減っていなければ「停滞」として MIN_GAP_MIN 分あけて起こし直す（最大 MAX_ATTEMPTS 回。そのあとは REFIRE_HOURS 待つ）。
    → {job: 結果の文}。GATE_FIRE で許されていない仕事は起こさない（GATE_FORCE に名前があれば別：管理ページの「もう一度起こす」で、
    間隔・停滞の判断を飛ばして今すぐ起こす）。トークンがなければ起こさず「トークン未設定」と残す（定時のほうで拾われる）。"""
    env = os.environ if env is None else env
    force = {x.strip() for x in str(env.get("GATE_FORCE", "")).split(",") if x.strip() in ROUTINES}
    allowed = enabled_jobs(env.get("GATE_FIRE", "1")) | force
    data = load(path)
    now = _now()
    results = {}
    for job, (rid, var, name) in ROUTINES.items():
        j = (data.get("jobs") or {}).get(job) or {}
        if not j.get("need") and job not in force:   # ボタン（GATE_FORCE）は整理待ちがなくても起こす（やり直しだけのときもある）
            results[job] = "仕事なし（起こさない）"
            continue
        if job == "edit" and job not in force and edit_mode(env) == "pause":
            results[job] = "管理ページで一時停止中（起こさない）"
            continue
        if job not in allowed:
            results[job] = "GATE_FIRE で止めている（定時を待つ）"
            continue
        last = j.get("fired") or {}
        state, why = work_state(j, now)
        attempts = 1
        if job in force:
            pass
        elif state == "running" or (state == "progress" and (now - dt.datetime.fromisoformat(last["at"])) < dt.timedelta(minutes=MIN_GAP_MIN)):
            results[job] = f"{MIN_GAP_MIN} 分以内に起こし済み（編集中かもしれないので待つ）"
            continue
        elif state == "stalled":
            attempts = int(last.get("attempts") or 1) + 1   # 動いていない：もう一度
        elif state == "gave_up":
            try:
                ago = now - dt.datetime.fromisoformat(last["at"])
            except (KeyError, ValueError, TypeError):
                ago = dt.timedelta(0)
            if ago < dt.timedelta(hours=REFIRE_HOURS):
                results[job] = f"停滞：{why}（{REFIRE_HOURS} 時間待つ・管理ページで確認）"
                continue
        if job not in force and state in ("progress", "none") and job in SLOTS:
            try:
                at = dt.datetime.fromisoformat(last["at"]) if last.get("at") else None
            except (ValueError, TypeError):
                at = None
            if at is not None and at >= last_slot(job, now):   # この回（9:00 / 18:00）はもう起こした
                nxt = next_slot(job, now).astimezone(zoneinfo.ZoneInfo(SLOT_TZ)).strftime("%H:%M")
                results[job] = f"1 日 2 回（{' と '.join(f'{h}:{m:02d}' for h, m in SLOTS[job])}）。次は {nxt}"
                continue
        # progress（60 分たって、進んだがまだ残りがある）→ 新しい状況として attempts=1 で起こす
        token = env.get(var)
        if not token:
            results[job] = "トークン未設定（定時を待つ）"
            continue
        try:
            out = post(f"https://api.anthropic.com/v1/claude_code/routines/{rid}/fire", token)
            j["fired"] = {"at": now.isoformat(timespec="seconds"), "sig": j.get("sig"), "prog": j.get("prog"),
                          "attempts": attempts, "resp": _resp(out), **({"forced": True} if job in force else {})}
            results[job] = "Claude を起こした" + (f"（{attempts} 回目：前は動かなかった）" if attempts > 1 else "")
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
