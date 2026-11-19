"""新しい人のページ（登録した直後・版面を足した直後：版面が少ない・記事が少ない・整理待ちだけ）の見本（2026-11-19，店長：
test-b の非公開ページを不合格にした 8 つ）。本物のお客さまのページと同じ道（user_pages.build → render.render）に作り物のデータを入れる。
本物のお客さまの名前・データは使わない（版面の名前・記事は作り物。写真は PIL でその場に描く）。

    python harness/new_user_sample.py OUT        # OUT/a.html・b.html・c.html と OUT/img/*.jpg
  a  版面 1 つ（広島旅行）・AI 編集済みの記事 3 本＋整理待ち 4 件・予定と欲しい物なし（test-b の形）
  b  版面 1 つ・整理待ちだけ（AI 編集がまだ）
  c  版面 3 つ・うち 2 つは記事 0〜1 本
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# (名前, 幅, 高さ, 色)：縦長・横長・極端な比を混ぜる
PHOTOS = [("wide", 1200, 675, (40, 90, 140)), ("tall", 600, 900, (150, 60, 50)), ("pano", 1500, 420, (60, 120, 70)),
          ("square", 800, 800, (120, 100, 40)), ("tall2", 500, 1000, (90, 50, 120)), ("wide2", 1280, 720, (30, 110, 120)),
          ("std", 1000, 750, (140, 90, 30)), ("std2", 1024, 683, (70, 70, 150))]
# 最後の行が 1 字になりやすい長さの見出し（日本語）を混ぜる
HEADS = ["宮島の紅葉が見頃に　厳島神社の夜間ライトアップは今週末から始",
         "広島駅の新しい駅ビルが来春開業へ　路面電車が二階に乗り入れる計画が正式に決まり工事が始",
         "お好み焼きの老舗が新店舗　平和公園の近くで十一月から営業開始",
         "瀬戸内の島めぐりフェリーに新航路　大久野島と鞆の浦を一日で結ぶ便が週末限定で運航を始",
         "原爆ドームの保存工事が完了　周辺の遊歩道も夜間照明を新しくして公開が始"]
PEND = ["呉の大和ミュージアム　リニューアル後の入館者が百万人に",
        "尾道の坂道を歩くガイドツアー　秋の特別コースの予約受付が始まる",
        "広島城の天守閣　木造復元の計画について市が説明会を開く予定",
        "しまなみ海道のサイクリング　レンタル自転車の乗り捨て場所が増える",
        "牡蠣小屋が今年も開店　宇品の港の近くで来月から始まる予定です",
        "安芸の宮島　鹿との付き合い方を伝える新しい案内板ができた"]


def photos(out):
    from PIL import Image, ImageDraw
    d = out / "img"
    d.mkdir(parents=True, exist_ok=True)
    for name, w, h, c in PHOTOS:
        im = Image.new("RGB", (w, h), c)
        g = ImageDraw.Draw(im)
        for k in range(0, max(w, h), 60):   # 帯と分かる単色の端を作らない（全面に模様）
            g.line([(k, 0), (0, k)], fill=tuple(min(255, v + 50) for v in c), width=14)
        g.ellipse([w * 0.35, h * 0.2, w * 0.65, h * 0.2 + min(w, h) * 0.3], fill=(230, 210, 180))   # 顔の代わりの丸
        im.save(d / f"{name}.jpg", quality=70)
    return [f"img/{n}.jpg" for n, *_ in PHOTOS]


def story(i, head, img, weight):
    return {"headline": head, "url": f"https://example.com/news/{i}", "image": img, "date": f"2026-11-{18 - i % 5:02d}",
            "blurb": "作り物の要約。" + head[:20], "highlight": "", "weight": weight, "source": "例の新聞"}


def pend(i, title, img=None):
    """整理待ち（board_stories.pending・user_boards の記事の形）。写真のある物とない物を混ぜる。"""
    return {"title": title, "url": f"https://example.com/pending/{i}", "source": "例の新聞", "date": f"2026-11-{19 - i % 4:02d}",
            **({"image": img} if img else {})}


def shapes(imgs):
    """{形: (prefs, rows, follows)}。rows は user_pages.board_rows の返す形（{そろえた名前: {stories, edited, pending}}）。"""
    import user_pages
    n = user_pages.norm
    fol = lambda names: [{"pos": k, "section": s, "subs": {}, "size": None, "boards": {"id": k + 1, "name": nm, "config": {}}}
                         for k, (nm, s) in enumerate(names)]
    one = [("広島旅行", "出行")]
    a_rows = {n("広島旅行"): {"edited": True, "stories": [story(k, HEADS[k], imgs[k], "hero" if k == 0 else "normal") for k in range(3)],
                             "pending": [pend(k, PEND[k], imgs[k + 3] if k < 3 else None) for k in range(4)]}}
    b_rows = {n("広島旅行"): {"edited": False, "stories": [{"title": PEND[k], "url": f"https://example.com/raw/{k}", "image": imgs[k + 1],
                                                          "date": "2026-11-19", "source": "例の新聞"} for k in range(5)]}}
    three = [("広島旅行", "出行"), ("京都の紅葉", "出行"), ("ゼルダの伝説", "游戏")]
    c_rows = {n("広島旅行"): {"edited": True, "stories": [story(k, HEADS[k], imgs[k], "hero" if k == 0 else "normal") for k in range(4)],
                             "pending": [pend(k, PEND[k], imgs[k + 5]) for k in range(3)]},
              n("京都の紅葉"): {"edited": True, "stories": [story(10, HEADS[4], imgs[4], "hero")], "pending": [pend(10, PEND[4], imgs[1]), pend(11, PEND[5])]},
              n("ゼルダの伝説"): {"edited": False, "stories": []}}
    pk = lambda names: {"picks": [{"name": nm, "sec": s} for nm, s in names], "sizes": {}}
    return {"a": (pk(one), a_rows, fol(one)), "b": (pk(one), b_rows, fol(one)), "c": (pk(three), c_rows, fol(three))}


def build(out):
    """OUT に 3 形のページを書く。返す：{形: パス}。"""
    import yaml
    import user_pages
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    imgs = photos(out)
    settings = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    settings = {**settings, "supabase_url": "", "supabase_key": ""}   # 本番 DB に触らない
    res = {}
    for k, (prefs, rows, follows) in shapes(imgs).items():
        h = user_pages.build("new-user@example.com", prefs, rows, [], {"date": "2026-11-19", "no": 1}, settings, 0, {}, follows, {})
        (out / f"{k}.html").write_text(h, encoding="utf-8")
        res[k] = out / f"{k}.html"
    return res


if __name__ == "__main__":
    for k, p in build(sys.argv[1] if len(sys.argv) > 1 else ROOT / "state" / "new_user_sample").items():
        print(k, p)
