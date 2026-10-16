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
            self.assertTrue(t.get("name") and t.get("for") and t.get("ja"), f"{t['id']} 要写 name、ja 和 for")
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

    def test_like_fx(self):
        # 20 种演出：likefx.FX（名字）和 FX_JS 里的定义一一对应；每个模版的 fx 都是其中之一
        import likefx
        js_ids = re.findall(r"^    (\w+): \['", likefx.FX_JS.split("const FX = {", 1)[1].split("};", 1)[0], flags=re.M)
        self.assertEqual(js_ids, list(likefx.FX))
        self.assertEqual(len(likefx.FX), 20)
        for t in self.index:
            self.assertIn(t.get("fx"), likefx.FX, f"{t['id']} 的 fx")
        self.assertEqual(len(self.index), 30)
        # 版面带 data-fx，网页里有演出脚本
        # items.yaml の like_fx はテーマの fx より優先、知らない名前ならテーマの fx
        _, items = digest.load_config()
        for item in items:
            if item.get("like_fx"):
                self.assertIn(item["like_fx"], likefx.FX, f"{item['name']} 的 like_fx")
        render._FX_OF["测试"] = "stamp"
        self.assertEqual(render._fx("测试"), ' data-fx="stamp"')
        self.assertIn("window.likeFx", render.LIKEFX_JS)
        self.assertNotIn("__THUMB__", render.LIKEFX_JS)

    def test_like_fx_uses_libraries(self):
        # 粒は canvas-confetti、擬音は Dela Gothic One（使う文字だけ読む）。どちらも演出のあるページの <head> に入る
        import likefx
        self.assertIn("canvas-confetti@", likefx.CONFETTI_JS)
        self.assertIn("family=Dela+Gothic+One", likefx.SFX_FONT)
        for ch in "ドン！イイネナス+1いね":
            self.assertIn("".join(f"%{b:02X}" for b in ch.encode()), likefx.SFX_FONT)
        self.assertIn(likefx.CONFETTI_JS, render.LIKEFX_HEAD)
        self.assertIn("burstPath", likefx.FX_JS)

    def test_emblems(self):
        # 作品の小元素：既存の画像の網址（http(s)）だけ。何枚でもよく、網页で 1 枚をランダムに。色のフチは emblem_ring
        _, items = digest.load_config()
        for item in items:
            for x in item.get("emblem") or []:
                self.assertRegex(x.get("image", ""), r"^(https://|emblems/[a-z0-9-]+\.webp$)", item["name"])
                if x["image"].startswith("emblems/"):
                    self.assertTrue((ROOT / "docs" / x["image"]).exists(), x["image"])
                self.assertIn(x.get("shape"), ("cutout", "badge"), item["name"])
                self.assertTrue(x.get("why") and x.get("subject"), item["name"])
        html_ = render._emblem([{"image": "https://a/1.png", "shape": "cutout"}, {"image": "javascript:x", "shape": "badge"},
                                {"image": "https://a/2.png", "shape": "badge"}], "accent")
        self.assertIn('class="emb ring-accent"', html_)
        self.assertIn('src="https://a/1.png"', html_)
        self.assertNotIn("javascript", html_)
        self.assertIn("https://a/2.png", html_)   # 候補（data-alts）
        self.assertEqual(render._emblem([]), "")
        self.assertIn('ring-accent', render._emblem([{"image": "https://a/1.png"}], "nope"))
        self.assertIn("Math.random()", render.EMB_JS)

    def test_emblem_palette(self):
        # 小元素の代表色 → 配色：地は米白、強調は代表色（読める濃さ）、どれも 4.5:1 以上
        import emblem, theme
        for tone in ("light", "dark"):
            th = emblem.palette(theme._rgb("#D97441"), tone)   # ポチタのオレンジ
            for a, b in (("fg", "bg"), ("accent", "bg"), ("alt_fg", "alt_bg"), ("alt_accent", "alt_bg")):
                self.assertGreaterEqual(theme.contrast(theme._rgb(th[a]), theme._rgb(th[b])), 4.5, (tone, a, b))
        self.assertLess(theme._lum(theme._rgb(emblem.palette(theme._rgb("#D97441"), "dark")["bg"])), 0.05)   # 暗い地
        th = emblem.palette(theme._rgb("#D97441"))
        h = lambda c: __import__("colorsys").rgb_to_hls(*(v / 255 for v in theme._rgb(c)))[0]
        self.assertLess(abs(h(th["accent"]) - h("#D97441")), 0.04)   # 強調色は代表色と同じ色相


    def test_functional_text_not_faded(self):
        # 読ませる小さな文字（出典・日付・件数・注記）は透明度で薄くしない（配色によっては 4.5:1 を割る）
        for sel in (".from{", ".when{", ".older summary span{", ".sbox h4 small{"):
            rule = render.CSS.split("\n" + sel, 1)[1].split("}", 1)[0]
            self.assertNotIn("opacity", rule, sel)
            self.assertNotIn("transparent", rule, sel)

    def test_emblem_card_crop(self):
        # 立ち絵がない写真はカード：crop があれば 4:5 の窓に顔の範囲だけ。おかしな値は無視（ふつうのカード）
        html_ = render._emblem([{"image": "https://a/p.jpg", "shape": "badge", "crop": [0.1, 0.05, 0.6], "ar": 1.4}])
        self.assertIn('<span class="crop" style="--cx:0.1;--cy:0.05;--cw:0.6;--ar:1.4">', html_)
        bad = render._emblem([{"image": "https://a/p.jpg", "shape": "badge", "crop": [2, "x", 0]}])
        self.assertNotIn('class="crop"', bad)
        self.assertIn('class="badge"', bad)
        self.assertNotIn("border-radius:50%", render.CSS.split(".emb img.badge{", 1)[1].split("}", 1)[0])   # 丸くしない
        import emblem
        from PIL import Image
        crop, ar = emblem.face_crop(Image.new("RGBA", (400, 600), (200, 200, 200, 255)))   # 顔がない：上寄りの中央
        self.assertEqual(ar, 1.5)
        self.assertAlmostEqual(crop[2] * 400 / (crop[2] * 400 / 0.8), 0.8)

    def test_cutout_check(self):
        # 抠图的检查：脸以外切掉可以，身体在左右上部被切掉不行；离开的小碎块去掉；版面里有半身像就去掉全身像
        import emblem
        from PIL import Image, ImageDraw
        def fig(box, extra=None, size=(200, 300)):
            im = Image.new("RGBA", size, (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            d.rectangle(box, fill=(200, 80, 60, 255))
            if extra: d.rectangle(extra, fill=(200, 80, 60, 255))
            return im
        ok = emblem.check_whole(fig((40, 20, 160, 299), extra=(2, 280, 8, 290)))   # 胸像＋左下の小さな切れ端
        self.assertEqual(ok.getchannel("A").getpixel((5, 285)), 0)                 # 切れ端は消える
        self.assertEqual(emblem.framing(ok), "bust")
        with self.assertRaises(ValueError):
            emblem.check_whole(fig((0, 20, 160, 299)))                              # 左の端で体が切れている
        self.assertEqual(emblem.framing(fig((40, 20, 160, 250))), "full")
        self.assertIn('src="emblems/a-b.webp"', render._emblem([{"image": "emblems/a-b.webp", "shape": "cutout"}]))
        self.assertEqual(render._emblem([{"image": "../x.webp", "shape": "cutout"}]), "")
        self.assertIn("classList.add('out')", render.EMB_JS)

if __name__ == "__main__":
    unittest.main()
