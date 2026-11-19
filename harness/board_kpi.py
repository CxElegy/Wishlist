"""版面を足してから使えるようになるまでの時間（KPI）を測る（2026-11-11 店長：「新規ユーザーが盤面を追加した場合…どのくらいでエンブレムを用意できるとか、KPI 化して改善」）。

店長の PC（自前版 Supabase の docker・supabase-db）で動かす。DB は psql で読むだけ（書くのは add のときの本人の RPC だけ）。

  python harness/board_kpi.py add  --email test-c@example.com --pick "サカナクション:演出" --pick "ILLIT:演出" …
      テスト用アカウントでログインして（localhost の自前版 Supabase）、本人と同じ RPC（my_keywords_set）で版面を足し、
      計測の回（D:/Claude/kpi/runs/<時刻>.json）を作る。
  python harness/board_kpi.py watch <回のファイル> [--every 600] [--hours 18]
      回の版面ごとに、各段（follows・boards・記事・小元素・AI 編集・本人のページ）が初めて見えた時刻を書き足す。全部そろうか時間切れで終わる。
  python harness/board_kpi.py report [<回のファイル> …] [--no-fail] [--days 3]
      回ごとの「足してから各段まで」の分と、目標（経路別。「未満」）との比較。harness/kpi/latest.json に数字と red の一覧（アカウント・版面名はテスト用だけ）。
      目標を割った段・出ないままの段があれば 1 行ずつ出して終了コード 1（--no-fail で 0）。
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
# 目標（2026-11-19 店長：「新しい版面を足したら小元素が出るまでは 5 分未満を保つ」）。
# 根拠：DB の my_keywords_set が足したその場で board_added.yml を起こす（follows・boards は 2 分以内、小元素は別 job で最初に取って 5 分未満、
# 記事 15 分、本人のページ 1 回目 15 分、小元素の後の作り直しは数分）。AI 編集だけは今までどおり gate 待ち。
# 比べ方は「未満」：目標ちょうど（5.0 分）は赤（judge）。全部、足した時刻（t0）からの分。
STAGES = [   # (キー, 名前, 目標の分。経路 C のとき)
    ("picked", "本人の picks に入る", 1),
    ("follow", "ライブラリの follows", 5),
    ("board", "ライブラリの boards（C）", 5),
    ("raw", "記事が集まる（user_boards）", 20),
    ("pending", "ライブラリの記事（board_stories.pending）", 30),
    ("emblem", "小元素", 5),
    ("edited", "AI 編集の見出し（board_stories.stories）", 480),
    ("page", "本人のページに載る", 20),
    ("page_emblem", "小元素が本人のページに載る", 10),   # 小元素が出たあとの作り直し（数分）。ページの版面の中に絵がある
    ("photo", "本物の写真が版面に載る", 20),   # 2026-11-19 店長「点検は、本物の写真が取れるかどうかを含めること」：版面の中に記事自身の写真（data-o="1"）が min(3, カード数) 枚
]
TARGET = {k: m for k, _, m in STAGES}
# 経路ごとの目標（分）と、赤かどうかを見る段。A は店長の号の写し、B はライブラリにある版面（follows と記事だけ新しい）なので、
# 小元素は足した時点で既にある（B は 1 分未満。A は店長の号の写しで page と同時に揃うので小元素の段は見ない）。
TARGETS = {
    "C": dict(TARGET),
    "B": {"picked": 1, "follow": 5, "raw": 20, "emblem": 1, "page": 20, "photo": 20},
    "A": {"picked": 1, "page": 15},
}
RED_AFTER_MIN = 24 * 60   # これだけたっても見えない段は「出ないまま」


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


def page_has_emblem(html, name):
    """本人のページの、この版面の <section> の中に小元素（render._emblem の <div class="emb …">）があるか。"""
    i = html.find(f'data-k="{name}"')
    if i < 0:
        return False
    j = html.find("<section", i)
    return 'class="emb ' in html[i:j if j > 0 else len(html)]


PHOTO_MIN = 3   # 版面に本物の写真がこの枚数（カードがそれより少なければカードの数）載れば photo の段


def section_of(html, name):
    """本人のページの、この版面の <section> の中身（無ければ ""）。"""
    i = html.find(f'data-k="{name}"')
    if i < 0:
        return ""
    j = html.find("<section", i)
    return html[i:j if j > 0 else len(html)]


def page_photos(html, name):
    """版面の (カード数, 記事自身の写真の数)。写真は render._pic の img[data-e="s"][data-o="1"]（備えの絵・作品の表紙は data-o="0"）。"""
    import re
    sec = section_of(html, name)
    cards = sec.count('<article class="card')
    real = len(re.findall(r'<img\b(?=[^>]*\bdata-e="s")(?=[^>]*\bdata-o="1")[^>]*>', sec))
    return cards, real


def photo_ok(html, name):
    cards, real = page_photos(html, name)
    return cards > 0 and real >= min(PHOTO_MIN, cards)


def photo_mix(bid):
    """ライブラリの版面のいちばん新しい日の整理待ち（board_stories.pending）の写真の内訳（DB は PC の psql で読むだけ）：
    {n 記事, img 写真あり, wrapped 包みのまま, waiting 写真なしで探し中（img_why の印＝間をあけて試し直す。回数で諦めないので「諦めた」は無い）}"""
    r = q(f"select count(*), count(*) filter (where coalesce(e->>'image','')<>''), count(*) filter (where e->>'url' like '%news.google.com%'), "
          f"count(*) filter (where coalesce(e->>'image','')='' and e ? 'img_why') from public.board_stories s, jsonb_array_elements(coalesce(s.pending,'[]')) e "
          f"where s.board_id={int(bid)} and s.day=(select max(day) from public.board_stories where board_id={int(bid)})")
    n, img, w, wait = (int(x or 0) for x in (r[0] if r else (0, 0, 0, 0)))
    return {"n": n, "img": img, "wrapped": w, "waiting": wait}


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
        if page_at and page_at > parse(run["t0"]) and ("page" not in s or ("page_emblem" not in s and "emblem" in s) or "photo" not in s):
            if html is None:
                html = page_html(a)
            if f'data-k="{nm}"' in html or f'>{nm}<' in html:
                s.setdefault("page", iso(page_at))
                if "emblem" in s and page_has_emblem(html, nm):
                    s["page_emblem"] = iso(page_at)
                if "photo" not in s and photo_ok(html, nm):
                    s["photo"] = iso(page_at)
        if b.get("board_id") and b["path"] != "A":
            b["photos"] = photo_mix(b["board_id"])
        if b["path"] == "A":   # 店長と同じ名前：小元素・AI 編集・写真は店長の号のもの（本人のページに載った時点でそろう）
            for k in ("emblem", "edited", "pending", "photo"):
                if k not in s and "page" in s:
                    s[k] = s["page"]
    run["checked"] = iso(t)
    return run


def done(run):
    need = {"A": ["picked", "page"], "B": ["picked", "follow", "raw", "page", "photo"], "C": [k for k, _, _ in STAGES]}
    return all(all(k in b["seen"] for k in need[b["path"]]) for b in run["boards"])


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
    数えるもの：JS の例外・読めない写真・picks にあるのにページに無い版面・「undefined」「null」「NaN」の字・横のはみ出し（1333×677・390×844）。"""
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
                      boards:document.querySelectorAll('section.sec[data-k]').length})""")
                    r[f"{W}"] = {**m, "errors": errs[:5]}
                    pg.close()
            out[email.split("@")[0]] = r
        br.close()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    cur["pages"] = {k: {kk: (len(vv) if kk == "missing" else vv) for kk, vv in v.items()} for k, v in out.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")


def minutes(run, b, k, nd=1):
    v = b["seen"].get(k)
    if not v:
        return None
    m = (parse(v) - parse(run["t0"])).total_seconds() / 60
    return m if nd is None else round(m, nd)


def judge(run, t=None):
    """目標を割った段・出ないままの段の一覧（赤）。目標は「未満」：目標ちょうども赤。
    まだ見えない段は、足してからの経過が目標以上なら「まだ出ない」、24 時間以上なら「出ないまま」で赤。"""
    t = t or now()
    age = (t - parse(run["t0"])).total_seconds() / 60
    red = []
    for b in run["boards"]:
        for k, target in TARGETS.get(b["path"], {}).items():
            m = minutes(run, b, k, None)
            if m is None:
                why = "出ないまま" if age >= RED_AFTER_MIN else "まだ出ない" if age >= target else None
                m = round(age, 1)
            else:
                why = "遅い" if m >= target else None
                m = round(m, 1)
            if why:
                red.append({"path": b["path"], "name": b["name"], "stage": k, "minutes": m, "target": target, "why": why})
    return red


def photo_summary(files):
    """整理待ちの写真の内訳（observe が DB から数えた最後の値）を経路ごとに足して割合に：写真あり／包みのまま／探し中（回数で諦めない）。"""
    mix = {}
    for f in files:
        for b in json.loads(f.read_text(encoding="utf-8"))["boards"]:
            for k, v in (b.get("photos") or {}).items():
                mix.setdefault(b["path"], {}).setdefault(k, 0)
                mix[b["path"]][k] += int(v or 0)
    out = {}
    for p, m in mix.items():
        n = m.get("n") or 0
        if n:
            out[p] = {"n": n, **{f"{k}_pct": round(100 * m.get(k, 0) / n) for k in ("img", "wrapped", "waiting")}}
    return out


def cmd_report(a):
    """各段の分と目標の比べ。目標を割った段・出ないままの段があれば 1 行ずつ出して終了コード 1（--no-fail で 0）。
    引数なしは直近 --days 日（既定 3）の回だけ（前の仕組みのときの遅い回で赤のままにしない）。"""
    files = [pathlib.Path(x) for x in a.runs] or [f for f in sorted(RUNS.glob("*.json"))
                                                  if now() - parse(json.loads(f.read_text(encoding="utf-8"))["t0"]) <= dt.timedelta(days=a.days)]
    rows, agg, red = [], {}, []
    for f in files:
        run = json.loads(f.read_text(encoding="utf-8"))
        red += [{"run": f.stem, **x} for x in judge(run)]
        for b in run["boards"]:
            r = {"run": f.stem, "name": b["name"], "path": b["path"], **{k: minutes(run, b, k) for k, _, _ in STAGES}}
            rows.append(r)
            for k, _, _ in STAGES:
                if r[k] is not None:
                    agg.setdefault((b["path"], k), []).append(r[k])
    print("経路 | 版面 | " + " | ".join(n for _, n, _ in STAGES))
    for r in rows:
        print(f"{r['path']} | {r['name']} | " + " | ".join("—" if r[k] is None else f"{r[k]:.0f}分" for k, _, _ in STAGES))
    summ = {}
    for (p, k), v in sorted(agg.items()):
        v = sorted(v)
        tg = TARGETS.get(p, {}).get(k)
        summ.setdefault(p, {})[k] = {"n": len(v), "p50": v[len(v) // 2], "max": v[-1], "target": tg if tg is not None else TARGET[k],
                                    "ok": v[-1] < tg if tg is not None else None}   # None＝この経路では目標を置かない段
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    mix = photo_summary(files)
    for p, m in sorted(mix.items()):
        print(f"写真 経路 {p}：記事 {m['n']} 本・写真あり {m['img_pct']}%・包みのまま {m['wrapped_pct']}%・探し中 {m['waiting_pct']}%")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"at": iso(now()), "boards": summ, "runs": len(files), "red": red, "photos": mix}, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in red:
        print(f"赤 経路 {x['path']} {x['run']} {x['name']} {x['stage']}：{x['why']} {x['minutes']:g} 分（目標 {x['target']} 分未満）")
    if red and not a.no_fail:
        sys.exit(1)


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
        boards = pj.get("boards") or pj
        if isinstance(boards, dict):
            out["emblem"] = {"boards": len(boards), "ok": sum(1 for v in boards.values() if isinstance(v, dict) and (v.get("have") or v.get("ok")))}
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
    p = sp.add_parser("report"); p.add_argument("runs", nargs="*"); p.add_argument("--no-fail", action="store_true", help="赤でも終了コード 0"); p.add_argument("--days", type=float, default=3, help="引数なしのとき見る回の新しさ（日）")
    sp.add_parser("shop")
    sp.add_parser("tick")
    sp.add_parser("pages")
    a = ap.parse_args()
    {"add": cmd_add, "watch": cmd_watch, "report": cmd_report, "shop": cmd_shop, "tick": cmd_tick, "pages": cmd_pages}[a.cmd](a)


if __name__ == "__main__":
    main()
