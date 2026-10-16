"""版面模版（templates/）：AI 编辑按 TEMPLATES.md 新做或合并模版后，这里检查规矩。不访问网络。

    python -m unittest discover tests
"""

import pathlib
import re
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import render  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
TYPES = {"game", "anime", "show", "event", "product", "category"}


class Templates(unittest.TestCase):
    def setUp(self):
        self.index = yaml.safe_load((ROOT / "templates/index.yaml").read_text(encoding="utf-8"))["templates"]

    def test_every_template_has_css_and_is_loaded(self):
        ids = [t["id"] for t in self.index]
        self.assertEqual(len(ids), len(set(ids)), "模版 id 重复")
        for t in self.index:
            self.assertRegex(t["id"], r"^[a-z][a-z0-9-]*$")
            self.assertTrue((ROOT / f"templates/{t['id']}.css").exists(), t["id"])
            self.assertTrue(t.get("name") and t.get("for"), f"{t['id']} 要写 name 和 for")
            self.assertLessEqual(set(t.get("defaults") or []), TYPES, t["id"])
            self.assertIn(f".m-{t['id']}", render.CSS)
        self.assertEqual(sorted(render.MOTIFS), sorted(ids))
        orphans = {p.stem for p in (ROOT / "templates").glob("*.css")} - set(ids)
        self.assertFalse(orphans, f"这些 CSS 没写进 index.yaml：{orphans}")

    def test_css_only_styles_its_own_sections_with_theme_colors(self):
        for t in self.index:
            css = re.sub(r"/\*.*?\*/", "", (ROOT / f"templates/{t['id']}.css").read_text(encoding="utf-8"), flags=re.S)
            for rule in re.findall(r"([^{}]+)\{", css):
                for sel in rule.split(","):
                    self.assertTrue(sel.strip().startswith(f".m-{t['id']}"), f"{t['id']}：选择器 {sel.strip()!r} 要以 .m-{t['id']} 开头")
            # 颜色只用作品的配色变量；#000 / #FFF 只能用在遮罩、混色里
            colors = set(re.findall(r"#[0-9A-Fa-f]{3,8}\b", css)) - {"#000", "#FFF", "#fff"}
            self.assertFalse(colors, f"{t['id']} 写死了颜色 {colors}，改用 --bg/--fg/--acc 等变量")
            for size in re.findall(r"font[^;{}]*?(\d+(?:\.\d+)?)px", css):
                self.assertGreaterEqual(float(size), 10, f"{t['id']} 字号小于 10px")

    def test_items_use_existing_templates(self):
        _, items = digest.load_config()
        for item in items:
            if item.get("motif"):
                self.assertIn(item["motif"], render.MOTIFS, f"{item['name']} 的 motif 不存在")

    def test_new_web_item_borrows_default_until_designed(self):
        web = {"name": "新", "type": "anime", "notes": f"2026-10-16 {digest.WEB_ITEM_MARK}。"}
        self.assertEqual(render.template_for(web), "manga")
        self.assertEqual(render.template_for({**web, "motif": "pop"}), "pop")
        self.assertEqual(render.template_for({**web, "motif": "nope"}), "manga")
        self.assertEqual(render.template_for({"name": "手写", "type": "anime"}), "")  # 手写的没写 motif：普通版面
        self.assertEqual(digest.WEB_ITEM_MARK, render.WEB_ITEM_MARK)

    def test_deco_markup(self):
        self.assertEqual(render.MOTIFS["retro"].count('class="deco'), 2)
        self.assertIn('class="deco d2"', render.MOTIFS["retro"])
        self.assertEqual(render.MOTIFS["film"], "")


if __name__ == "__main__":
    unittest.main()
