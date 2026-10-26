"""ライブラリの版面の小元素（scripts/library_emblem.py）：店長と同じ emblem_fill を一時の items.yaml で、画像は公開の箱へ。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emblem  # noqa: E402
import emblem_fill  # noqa: E402
import library_emblem as le  # noqa: E402
import render  # noqa: E402
import sitedir  # noqa: E402
import user_pages  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://x.supabase.co"


def wd(_params):
    return {"entities": {"Q1": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]},
                                "sitelinks": {"enwiki": {"title": "Shohei Ohtani"}, "jawiki": {"title": "大谷翔平"}, "frwiki": {"title": "x"}}}}}


class Kind(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(le.kind_for("演出", {"form": "グループ"}), "group")
        self.assertEqual(le.kind_for("运动", {"sport": "野球"}, human=True), "person")
        self.assertEqual(le.kind_for("演出", {"form": "ソロ"}), "person")
        self.assertEqual(le.kind_for("影视", {"kind": "アニメ"}), "character")
        self.assertEqual(le.kind_for("游戏", {}), "character")
        self.assertEqual(le.kind_for("好物", {}), "brand")
        self.assertEqual(le.kind_for("生活", {"kind": "グルメ"}), "topic")

    def test_board_item(self):
        b = {"id": 154, "name": "大谷翔平", "wd": "Q1", "config": {"type": "product", "keywords": ["大谷翔平"], "emblem_who": ["a"],
                                                                 "emblem_state": {"state": "failed", "v": le.RULES}, "match": ["大谷翔平"]}}
        it = le.board_item(b, {"section": "运动", "subs": {}}, wd)
        self.assertEqual(it["emblem_kind"], "person")
        self.assertEqual(it["type"], "category")                  # 板块から（config の product ではない）
        self.assertEqual(it["wiki"], ["en:Shohei Ohtani", "ja:大谷翔平"])
        self.assertEqual(it["emblem_who"], ["a"])                 # 前の回の手がかりは続ける
        self.assertNotIn("emblem_state", it)
        self.assertNotIn("match", it)


    def test_group_members_from_wikidata(self):
        """グループの版面（ライブラリ）は emblem_who がなく写真が「何人も」で 0 枚だった：Wikidata のメンバー（P527・P463、人だけ）を who に。"""
        def ent(label, human=True):
            return {"labels": {"en": {"value": label}}, "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5" if human else "Q2"}}}}]}}

        def get(p):
            if p["action"] == "query":
                return {"query": {"search": [{"title": "Q3"}, {"title": "Q4"}]}}
            if p["ids"] == "Q9":
                return {"entities": {"Q9": {"claims": {"P527": [{"mainsnak": {"datavalue": {"value": {"id": "Q2"}}}}]}}}}
            return {"entities": {"Q2": ent("Jin"), "Q3": ent("Suga"), "Q4": ent("BTS album", human=False)}}
        self.assertEqual(le.group_members("Q9", get), ["Jin", "Suga"])
        b = {"id": 1, "name": "BTS", "wd": "Q9", "config": {}}
        it = le.board_item(b, {"section": "演出", "subs": {"form": "グループ"}}, get)
        self.assertEqual(it["emblem_who"], ["Jin", "Suga"])
        b["config"] = {"emblem_who": ["x"], "emblem_state": {"v": le.RULES}}   # 前の回の手がかりが先
        self.assertEqual(le.board_item(b, {"section": "演出", "subs": {"form": "グループ"}}, get)["emblem_who"], ["x"])

    def test_roster_hints_from_wikidata(self):
        """キャラの版面：AniList（アニメ → 漫画）と Fandom（項目 → シリーズ）の番号を Wikidata から。"""
        ents = {"Q10": {"claims": {"P8731": [{"mainsnak": {"datavalue": {"value": "108556"}}}],
                                   "P179": [{"mainsnak": {"datavalue": {"value": {"id": "Q11"}}}}]}},
                "Q11": {"claims": {"P4073": [{"mainsnak": {"datavalue": {"value": "de.spy"}}},
                                             {"mainsnak": {"datavalue": {"value": "spy-x-family"}}}]}}}
        get = lambda p: {"entities": {p["ids"]: ents[p["ids"]]}}  # noqa: E731
        it = le.board_item({"id": 142, "name": "SPY×FAMILY", "wd": "Q10", "config": {}}, {"section": "影视"}, get)
        self.assertEqual((it["anilist_id"], it["emblem_fandom"]), (108556, "spy-x-family"))
        it = le.board_item({"id": 142, "name": "x", "wd": "Q10", "config": {"emblem_fandom": "mine"}}, {"section": "影视"}, get)
        self.assertEqual(it["emblem_fandom"], "mine")              # 前の回に書いたものが先
        it = le.board_item({"id": 1, "name": "x", "wd": "Q10", "config": {}}, {"section": "好物"}, get)
        self.assertNotIn("anilist_id", it)                         # キャラの版面だけ


    def test_fandom_slug_guess(self):
        """名前からの Fandom：ハイフンの形・「:」のあと・転送先の本当の名前。"""
        seen = []

        def fake(url, limit=0):
            seen.append(url.split("//")[1].split(".")[0])
            if seen[-1] in ("spy-x-family", "kimetsunoyaiba"):
                return {"query": {"general": {"sitename": "Spy x Family Wiki" if "spy" in seen[-1] else "Kimetsu no Yaiba Wiki",
                                              "server": "https://" + ("spy-x-family" if "spy" in seen[-1] else "kimetsu-no-yaiba") + ".fandom.com"}}}
            raise OSError
        old = emblem_fill._json
        emblem_fill._json = fake
        try:
            self.assertEqual(emblem_fill.fandom_api({"name": "SPY×FAMILY", "wiki": ["en:Spy × Family"]}, strict=True),
                             "https://spy-x-family.fandom.com/api.php")
            self.assertEqual(emblem_fill.fandom_api({"name": "鬼滅の刃", "wiki": ["en:Demon Slayer: Kimetsu no Yaiba"]}, strict=True),
                             "https://kimetsu-no-yaiba.fandom.com/api.php")
        finally:
            emblem_fill._json = old


class TopicIcons(unittest.TestCase):
    """題材の版面（店長の滑雪の emblem_icon を規則で）：名前・小分類の言葉 → 記号、当たらなければ板块の記号。"""
    def test_icons(self):
        self.assertEqual(le.icons_for("サッカー日本代表", "运动", {"sport": "サッカー"}), "1f1ef-1f1f5 26bd")
        self.assertEqual(le.icons_for("台風・天気", "其他", {"kind": "その他"}), "1f300 26c5")
        self.assertEqual(le.icons_for("広島旅行", "生活", {"kind": "アウトドア・旅行"}), "1f5fa 26fa")
        self.assertEqual(le.icons_for("なにか", "出行", {}), "1f9f3")   # 板块の記号

    def test_board_item_topic_only(self):
        item = le.board_item({"id": 1, "name": "将棋", "config": {}}, {"section": "其他", "subs": {}}, wd)
        self.assertEqual(item["emblem_icon"], "265f")
        item = le.board_item({"id": 2, "name": "BTS", "config": {}}, {"section": "演出", "subs": {"form": "グループ"}}, wd)
        self.assertNotIn("emblem_icon", item)

    def test_wikidata_by_qid(self):
        seen = []
        saved = emblem_fill._json
        emblem_fill._json = lambda url, *a: seen.append(url) or {"entities": {"Q131375": {"claims": {"P18": [
            {"mainsnak": {"datavalue": {"value": "Shogi.jpg"}}}]}}}}
        try:
            rows = emblem_fill.wikidata_images("Q131375", ("P18",))
        finally:
            emblem_fill._json = saved
        self.assertEqual([r["title"] for r in rows], ["Shogi.jpg"])
        self.assertFalse(any("wbsearchentities" in u for u in seen))   # 番号なら名前で検索しない


class Fill(unittest.TestCase):
    def test_sandbox_upload_and_restore(self):
        roots = (emblem.ROOT, emblem_fill.ROOT, sitedir.SITE_DIR, emblem.EMB_DIR)
        ups = {}

        def fake_fill(item, log=print):
            print("名前を出す print")   # 公開のログに出ないこと（stdout も stderr も）
            print("名前を出す stderr", file=sys.stderr)
            self.assertNotEqual(sys.stderr, sys.__stderr__)
            self.assertNotEqual(emblem.ROOT, roots[0])   # 本物の items.yaml ではない
            got = emblem_fill.load_items()
            self.assertEqual(got[0]["name"], item["name"])
            emblem.EMB_DIR.mkdir(parents=True, exist_ok=True)
            (emblem.EMB_DIR / "x-1.webp").write_bytes(b"img")
            emblem.write_item(item["name"], [{"subject": "A", "image": "emblems/x-1.webp", "shape": "cutout"},
                                             {"subject": "B", "image": "https://e.org/b.png", "shape": "badge"}], None)
            return {"state": "ok", "note": "2 枚"}

        b = {"id": 168, "name": "筋トレ: x", "wd": None, "config": {"keywords": ["筋トレ"]}}
        add = le.fill_board(b, {"section": "生活"}, lambda n, d: ups.__setitem__(n, d), BASE, fill=fake_fill, now=100)
        self.assertEqual((emblem.ROOT, emblem_fill.ROOT, sitedir.SITE_DIR, emblem.EMB_DIR), roots)
        self.assertEqual(len(ups), 1)
        name = next(iter(ups))
        self.assertRegex(name, r"^b168-[0-9a-f]{10}\.webp$")        # 名前は番号だけ
        self.assertEqual(add["emblem"][0]["image"], f"{BASE}/storage/v1/object/public/emblems/{name}")
        self.assertEqual(add["emblem"][1]["image"], "https://e.org/b.png")
        self.assertNotIn("emblem_kind", add)          # 種類は毎回規則から（config に残さない）
        self.assertEqual(add["emblem_state"], {"state": "ok", "have": 2, "at": 100, "note": "2 枚", "v": le.RULES,
                                               "nv": emblem_fill.NAMES_V, "bv": emblem_fill.BROKEN_V})

    def test_note_uses_library_retry(self):
        b = {"id": 9, "name": "x", "wd": None, "config": {}}
        r = {"state": "failed", "note": "0 枚足した（a）。外した理由：b。新しい記事が来たらすぐ、来なくても 1 時間後にもう一度"}
        add = le.fill_board(b, {}, None, BASE, fill=lambda item, log=None: r, now=1)
        self.assertEqual(add["emblem_state"]["note"], f"0 枚足した（a）。外した理由：b。{le.RETRY_HOURS} 時間後にもう一度")

    def test_quote_name_skipped(self):
        add = le.fill_board({"id": 1, "name": 'a"b', "config": {}}, {}, None, BASE, fill=lambda *a, **k: 1 / 0, now=5)
        self.assertEqual(add["emblem_state"]["state"], "failed")

    def test_due(self):
        now = 10 ** 6
        nv = emblem_fill.NAMES_V
        bs = [{"id": 1, "config": {"emblem_state": {"state": "ok", "at": 0, "v": le.RULES, "nv": nv}}},   # 済み・今の規則 → 飛ばす
              {"id": 9, "config": {"emblem_state": {"state": "ok", "at": 0, "v": le.RULES, "nv": nv - 1}}},   # 済みでも名簿の規則が前の版 → 途中より先に数え直す
              {"id": 8, "config": {"emblem_state": {"state": "ok", "at": 0, "have": 3}}},   # 済みでも前の版の規則 → 作り直し
              {"id": 2, "config": {"emblem_state": {"state": "failed", "at": now - 3600, "v": le.RULES}}},
              {"id": 6, "config": {"emblem_state": {"state": "failed", "at": now - 3600, "have": 2}}},   # 前の版の規則 → すぐ
              {"id": 3, "config": {"emblem_state": {"state": "failed", "at": 0}}},   # 0 枚 → 途中より先
              {"id": 4, "config": {"emblem_state": {"state": "running", "at": now, "have": 5}}},
              {"id": 7, "config": {"emblem_state": {"state": "running", "at": now, "have": 0}}},
              {"id": 5, "config": {}},
              {"id": 10, "config": {"emblem_fandom": "jjk", "emblem_state": {"state": "failed", "at": now - 3600, "have": 2, "v": le.RULES}}},   # 届かなかったキャラの版面も名簿の版で
              {"id": 11, "config": {"emblem_state": {"state": "failed", "at": now - 3600, "have": 2, "v": le.RULES, "bv": emblem_fill.BROKEN_V}}},   # 手がかりなし → 24 時間待つ
              {"id": 12, "config": {"emblem_state": {"state": "failed", "at": now - 60, "have": 49, "v": le.RULES, "nv": nv}}}]   # 公開の箱の小元素を今の壊れ方の規則で見ていない → 待たない
        self.assertEqual([b["id"] for b in le.due(bs, now)], [5, 3, 7, 10, 12, 9, 4, 8, 6])

    def test_unbroken_drops_cut_public_emblems(self):
        """公開の箱の小元素は emblem_fill.broken_cuts が見ない → 同じ規則（broken_image）で外す。ほかの網址・ロゴ・読めないものは残す。"""
        import io
        from PIL import Image

        def png(cut):
            im = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
            if cut:
                im.paste((200, 150, 120, 255), (30, 0, 70, 120))
            else:   # 丸い人物（左右の端の直線の切り口がない）
                from PIL import ImageDraw
                ImageDraw.Draw(im).ellipse((20, 15, 80, 119), fill=(200, 150, 120, 255))
            b = io.BytesIO()
            im.save(b, "PNG")
            return b.getvalue()
        pub = f"{BASE}/storage/v1/object/public/emblems/"
        data = {pub + "cut.webp": png(True), pub + "ok.webp": png(False)}

        def fetch(u):
            if u not in data:
                raise OSError("404")
            return data[u]
        xs = [{"subject": "cut", "image": pub + "cut.webp"}, {"subject": "ok", "image": pub + "ok.webp"},
              {"subject": "gone", "image": pub + "gone.webp"}, {"subject": "logo", "image": pub + "cut.webp", "shape": "logo"},
              {"subject": "wd", "image": "https://e.org/cut.webp"}]
        self.assertEqual([x["subject"] for x in le.unbroken(xs, False, fetch=fetch)], ["ok", "gone", "logo", "wd"])

    def test_rebuild_on_new_rules(self):
        """版が上がった版面は前の規則のもの（名簿・分類・小元素）を捨てて作り直す。キャラも、新しい規則で取れた分があれば前の小元素は残さない
        （名簿は分類の全員なので「名簿にいる人」では字の順の脇役が残る）。新しい規則が書いた名簿は前と同じでも null にしない。"""
        seen = {}

        def fake_fill(item, log=print):
            seen.update(item)
            emblem_fill._set_field(item["name"], "emblem_who", '["Character", "Amber"]')   # roster が数え直した名簿（前と同じ）
            emblem.write_item(item["name"], [{"subject": "Albedo", "image": "https://e.org/new.png"}, {"subject": "Agent 8", "image": "https://e.org/new.png"},
                                             {"subject": "Player", "image": "https://e.org/p.png"}], None)
            return {"state": "running"}
        old = [{"subject": "Character", "image": "https://e.org/c.png"}, {"subject": "Amber", "image": "https://e.org/a.png"},
               {"subject": "Albedo", "image": "https://e.org/old.png"}, {"subject": "Aloy", "image": "https://e.org/l.png"}]
        cfg = {"emblem": old, "emblem_who": ["Character", "Amber"], "emblem_pool": 200, "emblem_category": "Characters",
               "emblem_fandom": "genshinimpact", "emblem_reject": ["x"], "emblem_state": {"state": "running", "v": le.RULES - 1}}
        b = {"id": 147, "name": "原神", "wd": None, "config": cfg}
        add = le.fill_board(b, {"section": "游戏"}, None, BASE, fill=fake_fill, now=1)
        self.assertNotIn("emblem_category", seen)   # 前の分類・名簿は渡さない（規則でまた探して数える）
        self.assertNotIn("emblem_who", seen)
        self.assertEqual(add["emblem_category"], None)
        self.assertEqual(add["emblem_pool"], None)
        self.assertNotIn("emblem_fandom", add)
        self.assertNotIn("emblem_who", add)   # 新しい名簿は前と同じ：書き換えない（null にしない）
        # 前の小元素（Amber・Aloy…）は残さない・同じ画像は 1 枚・Player はキャラでない
        self.assertEqual([x["subject"] for x in add["emblem"]], ["Albedo"])
        self.assertEqual(add["emblem_state"]["have"], 1)

    def test_not_character(self):
        for n in ("Player", "Pokémon Trainer (Super Smash Bros.)", "MHD: FV: Felyne List", "Monster Hunter (Marvel vs. Capcom: Infinite)", "Secondary Characters", "Special character", "Parents"):
            self.assertTrue(emblem.not_character(n), n)
        for n in ("Ash Ketchum", "Red (Adventures)", "May (anime)", "Agent 8", "Li'l Judd"):
            self.assertFalse(emblem.not_character(n), n)

    def test_rebuild_keeps_old_when_new_rules_find_none(self):
        """キャラでない版面で新しい規則が 1 枚も取れなければ、前の小元素を残す（字だけ・図・古い写真は外す）。"""
        old = [{"subject": "BTS", "image": "https://x/Q1-a.webp"},
               {"subject": "大相撲 1", "image": "https://commons.wikimedia.org/wiki/Special:FilePath/Wrestling%20at%20Tokyo%201890s.jpg"}]
        b = {"id": 153, "name": "BTS", "wd": None, "config": {"emblem": old, "emblem_state": {"state": "ok", "v": le.RULES - 1}}}
        add = le.fill_board(b, {"section": "演出", "subs": {"form": "グループ"}}, None, BASE,
                            fill=lambda item, log=None: {"state": "failed"}, now=1)
        self.assertEqual([x["subject"] for x in add["emblem"]], ["BTS"])
        self.assertEqual(add["emblem_state"]["have"], 1)


class Requests(unittest.TestCase):
    """管理ページの 替える・固定・外す（boards.config.emblem_requests）→ apply_requests。"""
    def cfg(self):
        return {"emblem": [{"image": "https://x/a.webp", "source": "https://s/a.jpg", "subject": "A"},
                           {"image": "https://x/b.webp", "source": "https://s/b.jpg", "subject": "B"},
                           {"image": "https://x/c.webp", "subject": "C"}],
                "emblem_state": {"state": "ok", "have": 3, "v": le.RULES},
                "emblem_requests": [{"_emblem_swap": [{"image": "https://x/a.webp", "reason": "misc"}],
                                     "_emblem_lock": [{"image": "https://x/b.webp", "on": True}],
                                     "_emblem_reject": [{"image": "https://x/c.webp", "reason": "misc"}]}]}

    def test_apply(self):
        add = le.apply_requests(self.cfg())
        self.assertEqual([x["subject"] for x in add["emblem"]], ["B"])
        self.assertTrue(add["emblem"][0]["lock"])
        self.assertEqual(add["emblem_reject"], ["https://s/a.jpg", "https://x/a.webp", "https://x/c.webp"])
        self.assertEqual(add["emblem_redo"], ["A"])               # 替えるだけ人を残す（外すは残さない）
        self.assertEqual(add["emblem_requests"], [])
        self.assertEqual((add["emblem_state"]["state"], add["emblem_state"]["have"]), ("running", 1))

    def test_nothing_and_unlock(self):
        self.assertEqual(le.apply_requests({"emblem": []}), {})
        c = {"emblem": [{"image": "https://x/a.webp", "lock": True}], "emblem_requests": [{"_emblem_lock": [{"image": "https://x/a.webp", "on": False}]}]}
        add = le.apply_requests(c)
        self.assertNotIn("lock", add["emblem"][0])
        self.assertNotIn("emblem_state", add)                      # 固定だけなら探し直さない

    def test_lock_survives_rebuild(self):
        b = {"id": 1, "name": "X", "config": {"emblem": [{"image": "https://x/a.webp", "lock": True}, {"image": "https://x/b.webp"}],
                                              "emblem_state": {"state": "ok", "v": le.RULES - 1}}}
        it = le.board_item(b, {"section": "运动", "subs": {}}, lambda p: {"entities": {}})
        self.assertEqual([x["image"] for x in it["emblem"]], ["https://x/a.webp"])


class UserPage(unittest.TestCase):
    def test_library_emblem_on_user_board(self):
        em = [{"subject": "A", "image": f"{BASE}/storage/v1/object/public/emblems/Q1-abc.webp", "shape": "cutout"}]
        fol = [{"pos": 0, "section": "运动", "subs": {}, "boards": {"name": "大谷翔平", "config": {"emblem": em, "match": ["x"]}}}]
        items = user_pages.user_items(user_pages.own_picks(fol, [{"name": "大谷翔平", "sec": "运动"}]), [])
        self.assertEqual(items[0]["emblem"], em)
        self.assertNotIn("Q1-abc", render._emblem([]))
        self.assertIn("Q1-abc.webp", render._emblem(items[0]["emblem"]))


if __name__ == "__main__":
    unittest.main()
