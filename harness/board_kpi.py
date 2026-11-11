"""版面を足してから使えるようになるまでの時間（KPI）を測る（2026-11-11 店長：「新規ユーザーが盤面を追加した場合…どのくらいでエンブレムを用意できるとか、KPI 化して改善」）。

店長の PC（自前版 Supabase の docker・supabase-db）で動かす。DB は psql で読むだけ（書くのは add のときの本人の RPC だけ）。

  python harness/board_kpi.py add  --email test-c@example.com --pick "サカナクション:演出" --pick "ILLIT:演出" …
      テスト用アカウントでログインして（localhost の自前版 Supabase）、本人と同じ RPC（my_keywords_set）で版面を足し、
      計測の回（D:/Claude/kpi/runs/<時刻>.json）を作る。
  python harness/board_kpi.py watch <回のファイル> [--every 600] [--hours 18]
      回の版面ごとに、各段（follows・boards・記事・小元素・AI 編集・本人のページ）が初めて見えた時刻を書き足す。全部そろうか時間切れで終わる。
  python harness/board_kpi.py report [<回のファイル> …]
      回ごとの「足してから各段まで」の分と、目標との比較。harness/kpi/latest.json に数字だけ（アカウント・版面名はテスト用だけ）。
  python harness/board_kpi.py tick
      まだ終わっていない回（24 時間以内）を 1 回だけ見て書き足す（ハーネスのループが毎回呼ぶ）。
  python harness/board_kpi.py pages
      テスト用アカウントの本人のページを storage から落として開き、JS の例外・壊れた写真・載っていない版面・字の崩れを数える。
  python harness/board_kpi.py shop
      店長（test1）の固定の版面：直近 7 日の「集めた → AI 編集」の遅れ（git の記録）と、小元素のそろい具合。

経路（店長のページ／ライブラリ）：
  A＝店長と同じ名前（user_pages が店長の号を写す）・B＝ライブラリにもうある版面（follows だけ足す）・C＝まったく新しい名前（全部の段が走る）。
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import browser  # noqa: E402,F401  urlopen の止め（test_browser_guard）。ここが読むのは localhost の自前版 Supabase だけ

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = pathlib.Path("D:/Claude/kpi/runs")   # 本人のデータが入るのでリポジトリの外（公開しない）
OUT = ROOT / "harness" / "kpi" / "latest.json"
LOCAL = "http://localhost:8000"
ENV = pathlib.Path("D:/Claude/SupabaseLocal/stack/.env")
PASSWORD = "0000"   # テスト用アカウント（test-a〜e@example.com）の決まった値。CLAUDE.md・ux_check と同じ
STAGES = [   # (キー, 名前, 目標の分。経路 C のとき)
    ("picked", "本人の picks に入る", 1),
    ("follow", "ライブラリの follows", 60),
    ("board", "ライブラリの boards（C）", 60),
    ("raw", "記事が集まる（user_boards）", 120),
    ("pending", "ライブラリの記事（board_stories.pending）", 180),
    ("emblem", "小元素", 120),
    ("edited", "AI 編集の見出し（board_stories.stories）", 480),
    ("page", "本人のページに載る", 150),
]
TARGET = {k: m for k, _, m in STAGES}


def q(sql):
    """自前版 Supabase の DB を psql で読む（PC だけ）。行ごとに | 区切り。"""
    r = subprocess.run(["docker", "exec", "supabase-db", "psql", "-U", "postgres", "-d", "postgres", "-At", "-F", "\t", "-c", sql],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:300])
    return [ln.split("\t") for ln in r.stdout.splitlines() if ln]


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def acct(email):
    return "u_" + hashlib.md5(email.encode("utf-8")).hexdigest()[:16]


def settings():
    return yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]


def shop_names():
    return {w["name"] for w in yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")).get("items") or [] if w.get("name")}


def now():
    return dt.datetime.now(dt.timezone.utc)


def iso(t):
    return t.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def parse(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def service_key():
    """service_role の鍵は .env からシェルにも画面にも出さずに読む（本人のページの中身を確かめるときだけ）。"""
    for ln in ENV.read_text(encoding="utf-8").splitlines():
        if ln.startswith("SERVICE_ROLE_KEY="):
            return ln.split("=", 1)[1].strip().strip('"')
    return None


def rpc_login(email):
    key = settings()["supabase_key"]
    req = urllib.request.Request(LOCAL + "/auth/v1/token?grant_type=password", data=json.dumps({"email": email, "password": PASSWORD}).encode(),
                                 headers={"apikey": key, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"], key


def rpc(name, body, tok, key):
    req = urllib.request.Request(LOCAL + "/rest/v1/rpc/" + name, data=json.dumps(body).encode(),
                                 headers={"apikey": key, "Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read() or b"null")


def cmd_add(a):
    email = a.email
    if not email.endswith("@example.com"):
        sys.exit("テスト用アカウント（@example.com）だけ")
    adds = []
    for p in a.pick:
        name, _, sec = p.rpartition(":")
        adds.append({"name": name.strip(), "sec": sec.strip()})
    cur = q(f"select coalesce(prefs->'picks','[]'::jsonb) from public.app_users where lower(email)={lit(email.lower())}")
    if not cur:
        sys.exit("アカウントが見つからない：" + email)
    picks = json.loads(cur[0][0])
    tok, key = rpc_login(email)
    if a.reset:   # 空の新しいユーザーとして始める（テスト用だけ）
        rpc("my_keywords_set", {"p_picks": []}, tok, key)
        picks = []
    have = {x.get("name") for x in picks}
    new = [x for x in adds if x["name"] not in have]
    shop = shop_names()
    lib = {r[0] for r in q("select name from public.boards")}
    t0 = now()
    n = rpc("my_keywords_set", {"p_picks": picks + new}, tok, key)
    run = {"t0": iso(t0), "email": email, "account": acct(email), "set": n,
           "boards": [{**x, "path": "A" if x["name"] in shop else "B" if x["name"] in lib else "C", "seen": {}} for x in new]}
    RUNS.mkdir(parents=True, exist_ok=True)
    f = RUNS / (t0.strftime("%Y%m%d-%H%M%S") + "-" + email.split("@")[0] + ".json")
    f.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f, json.dumps([(b["name"], b["path"]) for b in run["boards"]], ensure_ascii=False))


def page_html(account):
    k = service_key()
    if not k:
        return ""
    req = urllib.request.Request(f"{LOCAL}/storage/v1/object/pages/{account}/index.html", headers={"Authorization": "Bearer " + k, "apikey": k})
    try:
        return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    except Exception:
        return ""


def observe(run):
    """今の状態を見て、まだ記録していない段で「できている」ものに今の時刻（DB に時刻があればその時刻）を付ける。"""
    t = now()
    a, email = run["account"], run["email"]
    picks = {x.get("name") for x in json.loads((q(f"select coalesce(prefs->'picks','[]'::jsonb) from public.app_users where lower(email)={lit(email.lower())}") or [["[]"]])[0][0])}
    pg = q(f"select updated_at from storage.objects where bucket_id='pages' and name={lit(a + '/index.html')}")
    page_at = parse(pg[0][0]) if pg else None
    html = None
    for b in run["boards"]:
        s, nm = b["seen"], b["name"]
        if "picked" not in s and nm in picks:
            s["picked"] = run["t0"]
        br = q(f"select id, key, created_at, created_by, coalesce(config->'emblem','null'::jsonb)::text from public.boards where name={lit(nm)} order by id limit 1")
        if br:
            bid, bkey, bcreated, _, emb = br[0]
            b["board_id"], b["key"] = int(bid), bkey
            if "board" not in s:
                s["board"] = iso(max(parse(bcreated), parse(run["t0"]))) if b["path"] == "C" else run["t0"]
            fr = q(f"select created_at from public.follows where account={lit(a)} and board_id={bid}")
            if fr and "follow" not in s:
                s["follow"] = fr[0][0]
            if "emblem" not in s and emb not in ("null", "[]", "{}", ""):
                s["emblem"] = run["t0"] if b["path"] != "C" else iso(t)
            st = q(f"select coalesce(sum(jsonb_array_length(coalesce(pending,'[]'))),0), coalesce(sum(jsonb_array_length(coalesce(stories,'[]'))),0) from public.board_stories where board_id={bid} and day >= current_date - 2")
            if st:
                if "pending" not in s and int(st[0][0] or 0) > 0:
                    s["pending"] = iso(t)
                if "edited" not in s and int(st[0][1] or 0) > 0:
                    s["edited"] = iso(t)
        ub = q(f"select coalesce(jsonb_array_length(stories),0), updated_at from public.user_boards where account={lit(a)} and item={lit(nm)}")
        if ub and "raw" not in s and int(ub[0][0] or 0) > 0:
            s["raw"] = ub[0][1] or iso(t)
        if "page" not in s and page_at and page_at > parse(run["t0"]):
            if html is None:
                html = page_html(a)
            if f'data-k="{nm}"' in html or f'>{nm}<' in html:
                s["page"] = iso(page_at)
        if b["path"] == "A":   # 店長と同じ名前：小元素・AI 編集は店長の号のもの（本人のページに載った時点でそろう）
            for k in ("emblem", "edited", "pending"):
                if k not in s and "page" in s:
                    s[k] = s["page"]
    run["checked"] = iso(t)
    return run


NEED = {"A": ["picked", "page"], "B": ["picked", "follow", "raw", "page"], "C": [k for k, _, _ in STAGES]}   # 経路ごとに走る段


def done(run):
    return all(all(k in b["seen"] for k in NEED[b["path"]]) for b in run["boards"])


def cmd_watch(a):
    f = pathlib.Path(a.run)
    end = time.time() + a.hours * 3600
    while True:
        run = observe(json.loads(f.read_text(encoding="utf-8")))
        f.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
        print(run["checked"], " ".join(f"{b['name']}:{','.join(sorted(b['seen']))}" for b in run["boards"]), flush=True)
        if done(run) or time.time() > end:
            break
        time.sleep(a.every)


def cmd_tick(a):
    """まだ終わっていない計測の回（24 時間以内）を 1 回ずつ見る（ハーネスのループが毎回呼ぶ。後ろで回し続けなくてよい）。"""
    for f in sorted(RUNS.glob("*.json")):
        run = json.loads(f.read_text(encoding="utf-8"))
        if done(run) or now() - parse(run["t0"]) > dt.timedelta(hours=24):
            continue
        run = observe(run)
        f.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f.name, " ".join(f"{b['name']}:{','.join(sorted(b['seen']))}" for b in run["boards"]))


def cmd_pages(a):
    """テスト用アカウントの本人のページ（storage の pages/<u_…>/index.html）を落として開き、壊れていないかを数える。
    数えるもの：JS の例外・読めない写真・picks にあるのにページに無い版面・「undefined」「null」「NaN」の字・横のはみ出し（1333×677・390×844）・
    swallowed＝トップに記事を全部取られて空になった版面（目次は「今週 N 件」なのに版面は静か）・rawdate＝時刻つきの日付がそのまま出ている所。"""
    from playwright.sync_api import sync_playwright
    out, dirp = {}, RUNS.parent / "pages"
    dirp.mkdir(parents=True, exist_ok=True)
    accts = q("select email, coalesce(prefs->'picks','[]'::jsonb) from public.app_users where email like 'test-%@example.com' and left_at is null order by 1")
    with sync_playwright() as pw:
        br = browser.launch(pw)
        for email, picks in accts:
            names = [x.get("name") for x in json.loads(picks)]
            ac = acct(email)
            html = page_html(ac)
            r = {"picks": len(names), "page": bool(html)}
            if html:
                f = dirp / (ac + ".html")
                f.write_text(html, encoding="utf-8")
                r["missing"] = [n for n in names if f'data-k="{n}"' not in html and f">{n}<" not in html]
                for W, H in ((1333, 677), (390, 844)):
                    pg = br.new_page(viewport={"width": W, "height": H})
                    errs = []
                    pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)[:160]))
                    pg.goto(f.resolve().as_uri(), wait_until="load", timeout=120000)
                    pg.wait_for_timeout(5000)
                    m = pg.evaluate("""()=>({broken:[...document.images].filter(i=>i.complete&&!i.naturalWidth&&i.offsetWidth>40).length,
                      words:(document.body.innerText.match(/(undefined|NaN)|null/g)||[]).length,
                      overflow:Math.max(0,document.documentElement.scrollWidth-innerWidth),
                      boards:document.querySelectorAll('section.sec[data-k]').length,
                      swallowed:[...document.querySelectorAll('section.sec.quiet[data-k]')].filter(s=>[...document.querySelectorAll('.front [data-k]')].some(a=>a.dataset.k===s.dataset.k)).length,
                      rawdate:[...document.querySelectorAll('small,em,time,.d,.mono')].filter(n=>/[0-9]T[0-9][0-9]:[0-9][0-9]/.test(n.textContent)).length})""")
                    r[f"{W}"] = {**m, "errors": errs[:5]}
                    pg.close()
            out[email.split("@")[0]] = r
        br.close()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    cur["pages"] = {k: {kk: (len(vv) if kk == "missing" else vv) for kk, vv in v.items()} for k, v in out.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")


def minutes(run, b, k):
    v = b["seen"].get(k)
    return None if not v else round((parse(v) - parse(run["t0"])).total_seconds() / 60, 1)


def cmd_report(a):
    files = [pathlib.Path(x) for x in a.runs] or sorted(RUNS.glob("*.json"))
    rows, agg, late = [], {}, {}
    for f in files:
        run = json.loads(f.read_text(encoding="utf-8"))
        age = (parse(run.get("checked") or run["t0"]) - parse(run["t0"])).total_seconds() / 60
        for b in run["boards"]:
            r = {"run": f.stem, "name": b["name"], "path": b["path"], **{k: minutes(run, b, k) for k, _, _ in STAGES}}
            rows.append(r)
            for k, _, _ in STAGES:
                if r[k] is not None:
                    agg.setdefault((b["path"], k), []).append(r[k])
                elif k in NEED[b["path"]] and age > TARGET[k]:   # まだ見えていないのに目標を過ぎた（見えた分だけ数えると「遅い」が消える）
                    late[(b["path"], k)] = late.get((b["path"], k), 0) + 1
                    r[k] = -age
    print("経路 | 版面 | " + " | ".join(n for _, n, _ in STAGES))
    for r in rows:
        print(f"{r['path']} | {r['name']} | " + " | ".join("—" if r[k] is None else f"まだ（{-r[k]:.0f}分）" if r[k] < 0 else f"{r[k]:.0f}分" for k, _, _ in STAGES))
    summ = {}
    for (p, k), v in sorted(agg.items()):
        v = sorted(v)
        summ.setdefault(p, {})[k] = {"n": len(v), "p50": v[len(v) // 2], "max": v[-1], "target": TARGET[k], "ok": v[-1] <= TARGET[k]}
    for (p, k), n in sorted(late.items()):
        summ.setdefault(p, {}).setdefault(k, {"n": 0, "target": TARGET[k]}).update(late=n, ok=False)
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}   # pages・shop の数字は残す
    OUT.write_text(json.dumps({**cur, "at": iso(now()), "boards": summ, "runs": len(files)}, ensure_ascii=False, indent=1), encoding="utf-8")


def git_time(path):
    r = subprocess.run(["git", "-C", str(ROOT), "log", "--diff-filter=A", "--format=%cI", "--", path], capture_output=True, text=True, encoding="utf-8")
    ts = [x for x in r.stdout.split() if x]
    return parse(ts[-1]) if ts else None


def cmd_shop(a):
    """店長の固定の版面：集めた日の inbox が初めて入った時刻 → その日の edit.json が初めて入った時刻（AI 編集の遅れ）。小元素のそろい具合。"""
    out = {"days": []}
    for i in range(7):
        d = (dt.date.today() - dt.timedelta(days=i)).isoformat()
        c, e = git_time(f"inbox/{d}.json"), git_time(f"inbox/{d}.edit.json")
        out["days"].append({"day": d, "collect": c and iso(c), "edit": e and iso(e), "lag_min": round((e - c).total_seconds() / 60) if c and e else None})
    prog = ROOT / "state" / "emblem_progress.json"
    if prog.exists():
        pj = json.loads(prog.read_text(encoding="utf-8"))
        boards = pj.get("items") or {}   # {版面: {have, target, state…}}
        out["emblem"] = {"boards": len(boards), "ok": sum(1 for v in boards.values() if isinstance(v, dict) and (v.get("have") or 0) >= (v.get("target") or 1))}   # そろった＝目標の枚数
    lib = q("select count(*), count(*) filter (where config ? 'emblem' and jsonb_array_length(coalesce(config->'emblem','[]'))>0) from public.boards")
    out["library_emblem"] = {"boards": int(lib[0][0]), "with_emblem": int(lib[0][1])}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    cur["shop"] = out
    OUT.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("add"); p.add_argument("--email", required=True); p.add_argument("--pick", action="append", required=True); p.add_argument("--reset", action="store_true")
    p = sp.add_parser("watch"); p.add_argument("run"); p.add_argument("--every", type=int, default=600); p.add_argument("--hours", type=float, default=18)
    p = sp.add_parser("report"); p.add_argument("runs", nargs="*")
    sp.add_parser("shop")
    sp.add_parser("tick")
    sp.add_parser("pages")
    a = ap.parse_args()
    {"add": cmd_add, "watch": cmd_watch, "report": cmd_report, "shop": cmd_shop, "tick": cmd_tick, "pages": cmd_pages}[a.cmd](a)


if __name__ == "__main__":
    main()
