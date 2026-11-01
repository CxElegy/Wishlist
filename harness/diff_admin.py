"""店長のページ（ログインなしで見える /home/）と、お客さま（test-a〜e）の同じ日のページを、部品の有無で比べて違いを 1 行ずつ出す
（2026-11-02，ユーザー：「ユーザーのページは店長のページに従う。管理機能はないだけで、他は全く同じロジック」）。
  python harness/ux_check.py --diff-admin [--who test-a,test-b] [--widths 1400,390]
違い = 店長に見えてお客さまに見えない部品。ADMIN_ONLY（「管理なので無し」と理由を名前で書いたもの）は数えない。残りが 1 件でもあれば ✗。
部品は中身（記事の数）ではなく「画面に見えるか」だけで比べる。ページは index.html（トップ）と settings.html。"""
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

# 部品の名前 → CSS（画面に見えるもの）。名前は違いの 1 行にそのまま出る
PARTS_INDEX = {
    "目次：ロゴ": ".nav .logo", "目次：今日の最高（話題度の数字）": ".nav .logo .hm", "目次：トップの札": ".nav .nhead .pill[data-for='__front']",
    "目次：気になるかも？の札": ".nav .nhead .pill:not([data-for='__front']):not([data-for^='__top'])", "目次：板块の札": ".nav .nslot .nsec",
    "目次：駅（作品の札）": ".nav .nslot .pill:not(.x)", "目次：欲しい物へのリンク": ".nav .navwish", "目次：上の板块の帯（狭い幅）": ".nav .mtabs a",
    "見出し：欲しい物リストのボタン": ".mastwish", "見出し：更新の時刻": ".mast .upd,.upd", "見出し：設定へのボタン": "a[href='settings.html']",
    "トップのポスター": "#front article.top", "ポスター：重大の札": "#front .burst", "ポスター：👍👎": "#front [data-vote]",
    "ほかの注目ニュース": "#front .sidebar,.xtra,.others,#also", "気になるかも？の棚": "#picks", "気になるかも？の 1 枚": "#picks .pk",
    "これからの予定": ".agenda", "版面": "section.sec[data-k]", "版面：主題の飾り（m- class）": "section.sec[class*='m-']",
    "版面：小元素": "section.sec .emb,section.sec .emblem,section.sec [data-emb]", "版面：記事の 👍👎": "section.sec [data-vote]",
    "版面：札（重大・新着など）": "section.sec .fresh-tag,section.sec .burst", "版面：「もっと見る」の過去のニュース": "details.older",
    "版面：小分類の見出し": ".subhead", "版面：写真": "section.sec .pic img", "版面：更新中の帯": ".busy,.wl-busy,.upbar",
    "版面：話題度の数字": "section.sec .heat,section.sec .hm,section.sec [data-heat]",
}
PARTS_SETTINGS = {
    "設定：見出し": "h1,.mast", "設定：言語": "[data-lang],#lang,.lang", "設定：板块ごとの篇幅": "[data-size],.sizes,.size", "設定：関注項の一覧": ".items,.item,[data-item]",
    "設定：追加の入口": "a[href*='add'],.add,#add", "設定：ログインの札": ".wl-auth",
}
# 管理なので無し（名前 → 理由）。ここに無いものは「直す」。管理ページへの入口・ほかの人のデータ・今すぐ実行など、管理の機能だけ
ADMIN_ONLY = {
    "管理ページへの入口": "管理ページは店長だけ（docs/rules/admin.md）",
    "見出し：店長のページ・見るだけの札": "訪問者向けの札。ログインした本人には出さない",
}
# 「直す」だが次の段で直すもの（△ で出し、✗ には数えない）。その段が終わったら空にする。
# 残り：欲しい物は本人の分の置き場（表）が要る＝本番のデータベースの形を変える決めごと。BACKLOG の [?] でユーザーに聞いている
NEXT_STEP = {
    "目次：欲しい物へのリンク": "欲しい物は本人の分が要る（BACKLOG [?]：置き場の表を足すかどうか）",
    "見出し：欲しい物リストのボタン": "同上",
}
# 版面が 1 つもない人（test-c）は、版面から出る部品を持たなくてよい（最初の画面は「最初の 1 つを選ぶ」の別の主役、DESIGN）。枠組み（目次・ロゴ・見出し）は比べる
BOARD_ONLY = {"トップのポスター", "ポスター：重大の札", "ポスター：👍👎", "ほかの注目ニュース", "気になるかも？の棚", "気になるかも？の 1 枚", "これからの予定", "版面",
              "版面：主題の飾り（m- class）", "版面：小元素", "版面：記事の 👍👎", "版面：札（重大・新着など）", "版面：「もっと見る」の過去のニュース",
              "版面：小分類の見出し", "版面：写真", "版面：話題度の数字", "目次：板块の札", "目次：駅（作品の札）", "設定：関注項の一覧"}
# 中身（データ）がないと出ない部品：部品は同じで、本人の版面にその材料がまだない。△ で出し ✗ には数えない。
#   これからの予定 = 記事に日程（event）が付いてから＝お客さまの版面の AI 編集はまだ（BACKLOG「お客さま専用の編集待ち」）
#   もっと見る = 過去の号がある版面だけ ／ 気になるかも？ = 版面に載らなかった記事があるときだけ（MUST の人では必ず出す）
DATA_WAIT = {"これからの予定": "日程は AI 編集で付く（お客さまの版面の編集は未対応）",
             "版面：「もっと見る」の過去のニュース": "過去の号がまだない版面",
             "気になるかも？の棚": "版面に載らなかった記事がまだない", "気になるかも？の 1 枚": "同上"}
# 材料が十分あるはずの人は、データ待ちにしない（出なければ ✗）：test-a は版面 40 個・記事 400 本超
MUST = {"test-a": {"気になるかも？の棚", "気になるかも？の 1 枚"}}
PROBE = """(parts)=>{const vis=x=>x.offsetParent||x.getClientRects().length;const o={};
for(const [k,s] of Object.entries(parts)){try{o[k]=[...document.querySelectorAll(s)].filter(vis).length}catch(e){o[k]=-1}}
o.__admin_link=[...document.querySelectorAll('a[href*="admin"]')].filter(vis).length;return o}"""


def probe(pw, base, who, width, page, session, who_map):
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    pg = b.new_page(viewport={"width": width, "height": 900})
    pg.goto(base, wait_until="domcontentloaded", timeout=60000)
    if who_map.get(who):
        pg.evaluate("s=>{localStorage.setItem('wl-auth',JSON.stringify(s));localStorage.setItem('wl-user',JSON.stringify({name:s.user.email}));}", session(who_map[who]))
    pg.goto(base + page, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(18000)
    parts = PARTS_SETTINGS if page == "settings.html" else PARTS_INDEX
    r = pg.evaluate(PROBE, parts)
    b.close()
    return r


def diff(admin, user, later=False, who="", empty=False, wait=False):
    """店長にあってお客さまにない部品（ADMIN_ONLY を除く）。later=True なら次の段で直すもの（NEXT_STEP）だけ、False ならそれを除く。
    empty = 版面が 1 つもない人（BOARD_ONLY は比べない）。wait=True なら DATA_WAIT（データ待ち）だけを返す。MUST の人は DATA_WAIT でも ✗。"""
    out = []
    for k, n in admin.items():
        if k.startswith("__") or n <= 0 or user.get(k, 0) != 0 or k in ADMIN_ONLY or (k in NEXT_STEP) != later:
            continue
        if empty and k in BOARD_ONLY:
            continue
        if (k in DATA_WAIT and k not in MUST.get(who, ())) != wait:
            continue
        out.append(k)
    return out


def run(pw, base, who_list, widths, session, who_map):
    fails = 0
    empty = {}   # (人, 幅) → 版面が 1 つもない（index を先に比べる）
    for page in ("", "settings.html"):
        for w in widths:
            admin = probe(pw, base, "guest", w, page, session, who_map)
            for who in who_list:
                if who == "guest":
                    continue
                u = probe(pw, base, who, w, page, session, who_map)
                if page == "":
                    empty[(who, w)] = u.get("版面", 0) == 0
                e0 = empty.get((who, w), False)
                d, nx, dw = diff(admin, u, False, who, e0), diff(admin, u, True, who, e0), diff(admin, u, False, who, e0, True)
                fails += len(d)
                tag = f"{who} {page.split('.')[0] or 'index'} {w}px"
                print(("✗ " if d else "✓ ") + f"店長との違い {tag}：" + ("、".join(d) if d else "なし（管理なしを除く）"))
                if nx:
                    print(f"△ 次の段で直す {tag}：" + "、".join(nx))
                if dw:
                    print(f"△ データ待ち（部品は同じ・材料がまだない） {tag}：" + "、".join(dw))
    print(f"店長との違い：✗ {fails} 件")
    return 1 if fails else 0
