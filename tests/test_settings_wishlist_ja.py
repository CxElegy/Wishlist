"""店長の設定ページ・欲しい物ページ・向導（additem.js）の画面の文字は日本語（2026-11-13、中国語が混ざっていたのを直した）。
見るだけ（ログインなし）の見え方（薄く＋理由の札）と、写真のないカードの見え方も確かめる。"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402

# 中国語（簡体）にしかない字。日本語の漢字には入らない
SIMPLIFIED = set("设关项删览简报块篇览够这让进为个们动问选换类")
ITEMS = [{"name": "ペン", "section": "作品", "subtitle": "サブ", "size": "M", "fields": {}},
         {"name": "ゲームA", "section": "ゲーム", "subtitle": "", "size": "L", "fields": {}}]
DB = {"url": "https://db.example", "key": "k"}


def visible(h):
    return re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)


class OwnerSettingsJa(unittest.TestCase):
    def setUp(self):
        self.h = render.render_settings(ITEMS, DB, "11.13 10:00", ())

    def test_lang_and_labels_are_japanese(self):
        self.assertIn('<html lang="ja">', self.h)
        body = visible(self.h)
        self.assertEqual(sorted(SIMPLIFIED & set(body)), [])
        for ja in ("変更", "削除", "このジャンルを削除", "追いかけるものを足す"):
            self.assertIn(ja, body)

    def test_js_messages_come_from_table(self):
        m = re.search(r'<script type="application/json" id="wl-cfg">(.*?)</script>', self.h, re.S)
        cfg = m.group(1)
        msgs = json.dumps(json.loads(cfg)["t"], ensure_ascii=False)   # 板块の表（データ）は中国語の別名を持つので、画面の文字（t）だけ見る
        self.assertEqual(sorted(SIMPLIFIED & set(msgs)), [])
        for k in ("js_del_confirm", "js_sec_confirm", "js_sending", "js_del_ok", "js_out_confirm"):
            self.assertIn(k, cfg)

    def test_blocks_for_wide_layout(self):
        self.assertEqual(self.h.count('<div class="blk">'), 2)
        self.assertIn(".cfg{columns:2", self.h.replace("{{", "{"))

    def test_tables_same_keys(self):
        self.assertEqual(set(render.SETTINGS_OWNER) - set(render.SETTINGS_JA), set())
        for k in render.SETTINGS_OWNER:
            self.assertNotRegex(str(render.SETTINGS_OWNER[k]), "[" + "".join(SIMPLIFIED) + "]")


class WishlistJa(unittest.TestCase):
    ROWS = [{"id": 1, "name": "ペン", "status": "纠结", "price": 1200, "currency": "JPY", "image": "data:image/jpeg;base64,/9j/"},
            {"id": 2, "name": "ノート", "status": "想要"}]

    def test_owner_page_is_japanese(self):
        h = render.render_wishlist(self.ROWS, [], "11.13", (), DB)
        self.assertIn('lang="ja"', h)
        body = visible(h)
        self.assertEqual(sorted(SIMPLIFIED & set(body)), [])
        for zh in ("愿望清单", "去看看", "纠结名单", "想要的合计", "拍照加愿望"):
            self.assertNotIn(zh, body)
        for ja in ("欲しい物リスト", "迷っているもの", "写真で足す", "すべて"):
            self.assertIn(ja, body)
        # 状態の値（data-status・data-f・data-v）は DB と同じ（変えない）
        self.assertIn('data-status="纠结"', h)
        self.assertIn('data-f="全部"', h)

    def test_photoless_card_is_a_designed_tile(self):
        h = render.render_wishlist(self.ROWS, [], "11.13", (), DB)
        self.assertEqual(h.count('class="wimg noimg"'), 1)   # 写真のあるカードは noimg にならない
        self.assertIn('<span class="mono" aria-hidden="true">ノ</span>', h)


class ViewOnly(unittest.TestCase):
    def test_lock_css_and_notes(self):
        self.assertIn('html[data-lock="1"][data-page="settings"] .page :is(button,input,select,textarea', render.AUTH_CSS)
        self.assertIn('html[data-lock="1"][data-page="wishlist"] #snap', render.AUTH_CSS)
        self.assertIn("readOnlyNote2", render.AUTH_JS)
        self.assertIn("page!=='settings'&&page!=='wishlist'", render.AUTH_JS)


class AdditemJs(unittest.TestCase):
    _raw = (ROOT / "docs/home/additem.js").read_text(encoding="utf-8")
    JS = "\n".join(l for l in _raw.split("\n") if not l.strip().startswith("//"))   # コメントは数えない

    def test_syntax(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node がない")
        r = subprocess.run([node, "--check", str(ROOT / "docs/home/additem.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ui_text_is_japanese(self):
        for zh in ("新增关注项", "想关注什么", "第 1 问", "提交中", "连不上数据库", "每个面一个版面"):
            self.assertNotIn(zh, self.JS)
        for ja in ("追いかけるものを足す", "何を追いかけますか？", "残りはおまかせ", "送っています…"):
            self.assertIn(ja, self.JS)


if __name__ == "__main__":
    unittest.main()
