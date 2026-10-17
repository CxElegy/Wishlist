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

ITEMS = yaml.safe_load((pathlib.Path(__file__).resolve().parent.parent / "items.yaml").read_text(encoding="utf-8"))["items"]


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

    def test_render_uses_the_table(self):
        self.assertEqual(render._sec_name("时尚"), "ファッション")
        self.assertEqual(render._sec_en("宠物"), "PETS")
        self.assertEqual(render._sec_color("数码"), taxonomy.SECTIONS["数码"]["color"])
        self.assertIn("书刊", render.SECTION_ICON)
        self.assertEqual(list(render.SECTIONS)[:5], ["游戏", "影视", "运动", "演出", "好物"])   # 以前からの並びは変えない

    def test_sub_schemes_come_from_the_table(self):
        settings, _ = digest.load_config()
        self.assertEqual(settings["sub_schemes"]["游戏"], [{"id": "status", "label": "状態"}, {"id": "platform", "label": "プラットフォーム"}])


class Classify(unittest.TestCase):
    def test_examples(self):
        cases = [
            ("日本のファッション雑誌", "时尚", {"kind": "雑誌", "origin": "日本"}),
            ("Japanese fashion magazine", "时尚", {"kind": "雑誌", "origin": "日本"}),
            ("韩国三星电子推出的智能手机系列", "数码", {"kind": "スマホ"}),
            ("猫用品", "宠物", {"animal": "猫", "kind": "用品"}),
            ("dog food brand", "宠物", {"animal": "犬", "kind": "フード"}),       # food でもグルメにしない
            ("韓国のガールズグループ", "演出", {"scene": "K-POP", "form": "グループ"}),
            ("theme park in Osaka, Japan", "出行", {"kind": "テーマパーク", "area": "関西"}),
            ("American television series", "影视", {"kind": "ドラマ", "origin": "海外"}),
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
        self.assertEqual(taxonomy.guess_subs("数码", "said the AI"), {"kind": "AI・ソフト", "owner": "ブランド"})
        self.assertEqual(taxonomy.guess_subs("数码", "Thailand")["kind"], "スマホ")   # AI が単語の途中に入っても拾わない


class Items(unittest.TestCase):
    def test_items_use_known_sections_and_fill_every_scheme(self):
        for it in ITEMS:
            sec = digest.section_of(it)
            self.assertIn(sec, taxonomy.SECTIONS, it["name"])
            for x in taxonomy.SECTIONS[sec]["schemes"]:
                self.assertTrue((it.get("subs") or {}).get(x["id"]), f"{it['name']} の subs に {x['id']} がない")

    def test_moved_items(self):
        by = {i["name"]: digest.section_of(i) for i in ITEMS}
        self.assertEqual(by["猫用品"], "宠物")
        self.assertEqual(by["三星手机"], "数码")
        self.assertEqual(by["gelato pique"], "时尚")


class WebRequests(unittest.TestCase):
    def test_section_must_be_in_the_table(self):
        self.assertEqual(digest.clean_item_config({"section": "书刊"}), {"section": "书刊"})
        with self.assertRaises(ValueError):
            digest.clean_item_config({"section": "新板块"})

    def test_subs_written_as_flow_mapping(self):
        subs = digest.clean_item_config({"subs": {"kind": " 雑誌 ", "origin": "日本"}})["subs"]
        self.assertEqual(subs, {"kind": "雑誌", "origin": "日本"})
        text = "items:\n" + digest.item_entry_yaml("VOGUE JAPAN", {"type": "product", "section": "时尚", "subs": subs})
        self.assertIn('    subs: {kind: "雑誌", origin: "日本"}', text)
        self.assertEqual(yaml.safe_load(text)["items"][0]["subs"], subs)
        for bad in ({"Kind": "x"}, {"kind": ""}, {"kind": "x" * 21}, ["雑誌"]):
            with self.assertRaises(ValueError):
                digest.clean_item_config({"subs": bad})


if __name__ == "__main__":
    unittest.main()
