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
                                                                 "emblem_state": {"state": "failed"}, "match": ["大谷翔平"]}}
        it = le.board_item(b, {"section": "运动", "subs": {}}, wd)
        self.assertEqual(it["emblem_kind"], "person")
        self.assertEqual(it["type"], "category")                  # 板块から（config の product ではない）
        self.assertEqual(it["wiki"], ["en:Shohei Ohtani", "ja:大谷翔平"])
        self.assertEqual(it["emblem_who"], ["a"])                 # 前の回の手がかりは続ける
        self.assertNotIn("emblem_state", it)
        self.assertNotIn("match", it)


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
        self.assertEqual(add["emblem_state"], {"state": "ok", "have": 2, "at": 100, "note": "2 枚", "v": le.RULES})

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
        bs = [{"id": 1, "config": {"emblem_state": {"state": "ok", "at": 0}}},
              {"id": 2, "config": {"emblem_state": {"state": "failed", "at": now - 3600, "v": le.RULES}}},
              {"id": 6, "config": {"emblem_state": {"state": "failed", "at": now - 3600}}},   # 前の版の規則 → すぐ
              {"id": 3, "config": {"emblem_state": {"state": "failed", "at": 0}}},
              {"id": 4, "config": {"emblem_state": {"state": "running", "at": now}}},
              {"id": 5, "config": {}}]
        self.assertEqual([b["id"] for b in le.due(bs, now)], [5, 4, 3, 6])


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
