"""板块一览（sections.yaml + scripts/taxonomy.py）：事先定全、对号入座的规则、关注项的小分类都写全。"""
import pathlib
import re
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import digest  # noqa: E402
import render  # noqa: E402
import taxonomy  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parent.parent
ITEMS = yaml.safe_load((_ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]   # いまのアカウント（2026-10-21 から test1 = 店長）


class Table(unittest.TestCase):
    def test_every_section_is_complete(self):
        for key, r in taxonomy.SECTIONS.items():
            for f in ("ja", "en", "color", "icon", "kind", "schemes"):
                self.assertTrue(r.get(f), f"{key} に {f} がない")
            self.assertRegex(r["color"], r"^#[0-9A-F]{6}$")
            ids = [x["id"] for x in r["schemes"]]
            self.assertEqual(len(ids), len(set(ids)), key)
            for x in r["schemes"]:
                self.assertRegex(x["id"], r"^[a-z_]+$")
                self.assertTrue(taxonomy.values(x), f"{key}/{x['id']} に常用の値がない")
            if r.get("words"):
                re.compile(r["words"])

    def test_eight_sections(self):
        """2026-10-19：17 → 8 大類（用户定的）。並びは 作品・ゲーム・音楽・スポーツ・ショッピング・暮らし・おでかけ・その他。"""
        self.assertEqual(list(taxonomy.SECTIONS), ["影视", "游戏", "演出", "运动", "好物", "生活", "出行", "其他"])
        self.assertEqual(render._sec_name("影视"), "作品")
        self.assertEqual(render._sec_en("生活"), "LIFE")
        self.assertEqual(render._sec_color("好物"), taxonomy.SECTIONS["好物"]["color"])
        self.assertIn("生活", render.SECTION_ICON)
        self.assertIn("シリーズ", taxonomy.values(taxonomy.SECTIONS["影视"]["schemes"][0]))   # 方法 4

    def test_legacy_keys(self):
        for old, new in {"时尚": "好物", "数码": "好物", "汽车": "好物", "书刊": "影视", "宠物": "生活", "美食": "生活",
                         "爱好": "生活", "家居": "生活", "健康": "生活", "艺术": "出行", "游戏": "游戏"}.items():
            self.assertEqual(taxonomy.canonical(old), new)
            self.assertEqual(digest.section_of({"section": old}), new)

    def test_sub_schemes_come_from_the_table(self):
        settings, _ = digest.load_config()
        self.assertEqual(settings["sub_schemes"]["游戏"], [{"id": "status", "label": "状態"}, {"id": "platform", "label": "プラットフォーム"}])


class Classify(unittest.TestCase):
    def test_examples(self):
        cases = [
            ("日本のファッション雑誌", "好物", {"kind": "ファッション・コスメ"}),                 # 雑誌でも作品にしない
            ("韩国三星电子推出的智能手机系列", "好物", {"kind": "ガジェット・家電"}),
            ("Hello Kitty character", "好物", {"kind": "キャラグッズ", "owner": "キャラクター"}),
            ("猫用品", "生活", {"kind": "ペット"}),
            ("dog food brand", "生活", {"kind": "ペット"}),
            ("咖啡连锁店", "生活", {"kind": "グルメ"}),
            ("韓国のガールズグループ", "演出", {"scene": "K-POP", "form": "グループ"}),
            ("theme park in Osaka, Japan", "出行", {"kind": "テーマパーク", "area": "関西"}),
            ("museum in Tokyo", "出行", {"kind": "展覧会・美術館", "area": "関東"}),
            ("American television series", "影视", {"kind": "ドラマ", "origin": "海外"}),
            ("Chiikawa Japanese anime television series", "影视", {"kind": "アニメ", "origin": "日本"}),
            ("Japanese manga series", "影视", {"kind": "マンガ"}),                             # 「series」でもドラマにしない
            ("ちいかわ 劇場版", "影视", {"kind": "映画"}),
            ("Spider-Man media franchise", "影视", {"kind": "シリーズ"}),
            ("漫画原作のゲーム video game", "游戏", {}),                                        # ゲームを先に見る（prio）
            ("Nintendo Switch game", "游戏", {"platform": "家庭用ゲーム機"}),
        ]
        for text, sec, subs in cases:
            self.assertEqual(taxonomy.classify(text), sec, text)
            got = taxonomy.guess_subs(sec, text)
            self.assertEqual({k: got[k] for k in subs}, subs, text)

    def test_fallbacks(self):
        self.assertEqual(taxonomy.classify("Japanese public figure", "event"), "演出")   # 词没命中 → type
        self.assertEqual(taxonomy.classify("Japanese public figure"), "其他")
        self.assertEqual(taxonomy.guess_subs("其他"), {"kind": "その他"})
        self.assertEqual(taxonomy.guess_subs("好物", "Thailand")["kind"], "キャラグッズ")   # 何も当たらなければ最初の値


class Items(unittest.TestCase):
    def test_items_use_known_sections_and_fill_every_scheme(self):
        for it in ITEMS:
            sec = digest.section_of(it)
            self.assertIn(sec, taxonomy.SECTIONS, it["name"])
            for x in taxonomy.SECTIONS[sec]["schemes"]:
                self.assertTrue((it.get("subs") or {}).get(x["id"]), f"{it['name']} の subs に {x['id']} がない")

    def test_moved_items(self):
        # 旧い板块名から移した実例は test1 の関注項（archive/test1）にある
        ITEMS = yaml.safe_load((_ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]
        by = {i["name"]: digest.section_of(i) for i in ITEMS}
        self.assertEqual(by["猫用品"], "生活")
        self.assertEqual(by["三星手机"], "好物")
        self.assertEqual(by["gelato pique"], "好物")
        subs = {i["name"]: i.get("subs") for i in ITEMS}
        self.assertEqual(subs["漫威电影"]["kind"], "シリーズ")            # 方法 4：映画＋ドラマ
        self.assertEqual(subs["チェーンソーマン"]["kind"], "シリーズ")      # 漫画＋アニメ＋劇場版
        self.assertEqual(subs["FROM"]["kind"], "ドラマ")


class WebRequests(unittest.TestCase):
    def test_section_must_be_in_the_table(self):
        self.assertEqual(digest.clean_item_config({"section": "书刊"}), {"section": "影视"})   # 旧い名前は今の大類に
        with self.assertRaises(ValueError):
            digest.clean_item_config({"section": "新板块"})

    def test_subs_written_as_flow_mapping(self):
        subs = digest.clean_item_config({"subs": {"kind": " 雑誌 ", "origin": "日本"}})["subs"]
        self.assertEqual(subs, {"kind": "雑誌", "origin": "日本"})
        text = "items:\n" + digest.item_entry_yaml("VOGUE JAPAN", {"type": "product", "section": "好物", "subs": subs})
        self.assertIn('    subs: {kind: "雑誌", origin: "日本"}', text)
        self.assertEqual(yaml.safe_load(text)["items"][0]["subs"], subs)
        for bad in ({"Kind": "x"}, {"kind": ""}, {"kind": "x" * 21}, ["雑誌"]):
            with self.assertRaises(ValueError):
                digest.clean_item_config({"subs": bad})


if __name__ == "__main__":
    unittest.main()


class AlsoSections(unittest.TestCase):
    """also：版面は本来の板块に 1 つ、ほかの板块の目次には乗換の駅（ちいかわ：グッズ ＋ 映像）。"""

    def test_clean_and_write(self):
        also = digest.clean_item_config({"also": {"影视": {"kind": "アニメ", "origin": "日本"}, "宠物": {}}})["also"]
        self.assertEqual(also["影视"], {"kind": "アニメ", "origin": "日本"})
        self.assertEqual(also["生活"], {"kind": "ペット"})                      # 旧い名前は大類に、空なら最初の分け方の最初の値
        text = "items:\n" + digest.item_entry_yaml("ちいかわ", {"type": "category", "section": "好物", "also": also})
        self.assertIn('    also: {影视: {kind: "アニメ", origin: "日本"}, 生活: {kind: "ペット"}}', text)
        self.assertEqual(yaml.safe_load(text)["items"][0]["also"], also)
        with self.assertRaises(ValueError):
            digest.clean_item_config({"also": {"新板块": {}}})
        self.assertIsNone(digest.clean_item_config({"also": {}})["also"])

    def test_also_map_uses_chosen_scheme(self):
        items = [{"name": "ちいかわ", "section": "好物", "also": {"影视": {"kind": "アニメ", "origin": "日本"}, "好物": {}}}]
        self.assertEqual(digest.also_map(items, {"影视": "origin"}), {"ちいかわ": [("影视", "日本")]})   # 本来の板块は除く
        self.assertEqual(digest.also_map(items, {}), {"ちいかわ": [("影视", "アニメ")]})

    def test_nav_has_transfer_station(self):
        w = {"name": "ちいかわ", "section": "好物", "stories": [], "_heat": {}}
        g = {"name": "FROM", "section": "影视", "stories": [], "_heat": {}}
        html = render._nav([g, w], "2026-10-18", subs={"ちいかわ": "キャラクター", "FROM": "ドラマ"},
                           also={"ちいかわ": [("影视", "アニメ")]})
        self.assertEqual(html.count('data-for="ちいかわ"'), 1)                 # 版面への本来の駅は 1 つ
        self.assertIn('class="pill xfer"', html)
        self.assertIn("⇄ ショッピング", html)
        screen = html[html.index('data-sec="影视"><a class="nsec"'):html.index('data-sec="好物"><a class="nsec"')]
        self.assertIn('data-x="ちいかわ"', screen)                             # 映像の目次にちいかわの乗換駅
        self.assertIn('data-sub="アニメ"', screen)


class Facets(unittest.TestCase):
    """题材型（「猫」）の「面」：sections.yaml の facets[第一の分け方の値]、なければ GENERIC_FACETS。"""

    def test_pet_facets_written(self):
        fs = taxonomy.facets("生活", "ペット")
        self.assertEqual([f["id"] for f in fs][:2], ["goods", "food"])
        self.assertTrue(all(f["sec"] in taxonomy.SECTIONS and f.get("kw") and f.get("re") for f in fs))
        self.assertIn("出行", {f["sec"] for f in fs})                 # 猫カフェはおでかけ
        self.assertIn("好物", {f["sec"] for f in fs})                 # 猫モチーフのコラボ商品はショッピング
        for f in fs:
            re.compile(f["re"])

    def test_generic_fallback(self):
        fs = taxonomy.facets("生活", "グルメ")                         # グルメ用の面は書いていない → 共通の面
        self.assertEqual([f["id"] for f in fs], [f["id"] for f in taxonomy.GENERIC_FACETS])
        self.assertEqual(fs[0]["subs"], {"kind": "グルメ"})
        self.assertEqual(fs[2]["sec"], "出行")
        page = {x["key"]: x for x in taxonomy.for_page()}
        self.assertEqual(len(page), len(taxonomy.SECTIONS))
        self.assertIn("ペット", page["生活"]["facets"])
        self.assertTrue(page["运动"]["facets_any"])


class SeriesInNav(unittest.TestCase):
    """シリーズの中身（items.yaml の media）を目次の枝に、たたんだ板块の空きに作品名、本文に小分類の区切り。"""

    def works(self):
        st = lambda h: {"url": h, "headline": h, "blurb": "", "_issue": "2026-10-18"}
        return [{"name": "チェーンソーマン", "section": "影视", "stories": [st("劇場版 レゼ篇 興行収入"), st("最新刊 発売")], "_heat": {}},
                {"name": "FROM", "section": "影视", "stories": [], "_heat": {}},
                {"name": "猫用品", "section": "生活", "stories": [], "_heat": {}}]

    def test_media_branches(self):
        html = render._nav(self.works(), "2026-10-18", subs={"チェーンソーマン": "シリーズ", "FROM": "ドラマ", "猫用品": "ペット"},
                           media={"チェーンソーマン": ["マンガ", "アニメ", "映画"]})
        self.assertEqual(html.count('class="pill kid media"'), 3)
        self.assertEqual(html.count('data-for="チェーンソーマン"'), 1)          # 読んでいる印は作品の駅だけ
        self.assertIn('data-hot="1" data-sub="シリーズ" href="#', html)        # 映画の記事 1 件
        self.assertIn('<small>1</small>', html)                                 # 小分類の件数に枝は数えない
        self.assertIn('<div class="nsum x">', html)

    def test_sub_heads(self):
        ws = self.works()
        from unittest import mock
        with mock.patch.object(render, "_section", lambda w, wid: f'<section id="{wid}"></section>'):
            out = render._sub_heads([ws[1], ws[2], ws[0]], {"チェーンソーマン": "シリーズ", "FROM": "ドラマ", "猫用品": "ペット"}, {})
        heads = re.findall(r'<div class="subhead"[^>]*>(.*?)</div>', out)
        self.assertEqual(len(heads), 3)
        self.assertIn("作品", heads[0])                                          # 板块が変わる所だけ板块の札
        self.assertNotIn('class="tg"', heads[1])
        self.assertLess(out.index('id="' + render._wid("FROM")), out.index('id="' + render._wid("猫用品")))   # 同じ板块はまとまる


class MediaFacetsMECE(unittest.TestCase):
    """向导の「面」（docs/additem.js の MEDIA）は MECE：層（作品／展開）に漏れなく 1 つずつ、各面の代表語はほかの面の語に当たらない。"""

    def facets(self):
        js = (pathlib.Path(__file__).resolve().parent.parent / "docs" / "test1" / "additem.js").read_text(encoding="utf-8")
        block = js[js.index("  const MEDIA = {"):js.index("\n  };", js.index("  const MEDIA = {"))]
        out = {}
        for m in re.finditer(r'^    (\w+): \{label: "([^"]+)".*?kw: \[([^\]]*)\], re: "([^"]+)"', block, re.M | re.S):
            out[m.group(1)] = {"label": m.group(2), "kw": re.findall(r'"([^"]+)"', m.group(3)), "re": m.group(4)}
        layer = dict(re.findall(r'(\w+): "(作品|展開)"', js[js.index("const LAYER = {"):js.index("};", js.index("const LAYER = {"))]))
        return out, layer

    def test_every_facet_in_exactly_one_layer(self):
        fs, layer = self.facets()
        self.assertEqual(len(fs), 8)
        self.assertEqual(set(fs), set(layer))                                   # 漏れなく・余りなく
        self.assertEqual(set(layer.values()), {"作品", "展開"})

    def test_keywords_do_not_overlap(self):
        fs, _ = self.facets()
        for k, f in fs.items():
            for w in f["kw"]:
                self.assertRegex(w, re.compile(f["re"], re.I), f"{k}: {w}")
                for o, g in fs.items():
                    if o != k:
                        self.assertIsNone(re.search(g["re"], w, re.I), f"「{w}」（{k}）が {o} にも当たる")
        for text, only in {"コラボカフェ": "event", "コラボグッズ": "goods", "アニメ映画": "movie", "TVドラマ": "drama"}.items():
            self.assertEqual([k for k, f in fs.items() if re.search(f["re"], text, re.I)], [only], text)


class ShopSite(unittest.TestCase):
    """2026-10-21〜：店長のページ = test1（公開ページは docs/test1/）。test2 は 10-19〜10-21 の試験の写し（docs/test2/ 凍結・archive/test2/）。
    向导は 1 つの名前 = 1 つの版面（乗換なし・面は目次の枝）。"""

    def test_pages_go_to_test1(self):
        import sitedir
        self.assertEqual(sitedir.NAME, "test1")
        self.assertEqual(sitedir.SITE_DIR, _ROOT / "docs" / "test1")
        self.assertTrue((_ROOT / "archive" / "test2" / "items.yaml").exists())   # 試験の版は残す

    def test_wizard_one_panel_rule(self):
        js = (_ROOT / "docs" / "test1" / "additem.js").read_text(encoding="utf-8")
        self.assertIn('S.ans.arrange = S.ans.splitExtras && multiSec() ? "split" : "merge"', js)   # 既定は 1 つの版面
        self.assertIn('S.ans.also = {};', js)                                                      # 乗換駅は置かない
        self.assertRegex(js, r'const KEYS = \[[^\]]*"media"')                                      # 目次の枝を送る
