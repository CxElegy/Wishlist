"""お客さま本人の欲しい物（2026-11-07）：本人のページだけに操作が出て、店長のページは変わらない。"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402

DB = {"url": "https://db.example", "key": "k"}
ROWS = [{"id": 3, "name": "<b>ペン", "status": "纠结", "price": 1200, "currency": "JPY", "image": "data:image/jpeg;base64,/9j/", "added": "2026-11-07"},
        {"id": 4, "name": "ノート", "status": "想要"}]


class OwnWishes(unittest.TestCase):
    def test_own_page_has_controls_and_japanese(self):
        h = render.render_wishlist(ROWS, [], "11.07", (), DB, own=True)
        self.assertEqual(h.count("data-id="), 2)
        self.assertEqual(h.count('class="wctl"'), 2)
        self.assertIn('lang="ja"', h)
        self.assertIn("&lt;b&gt;ペン", h)
        body = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
        for zh in ("愿望清单", "想要的合计", "去看看", "纠结名单"):
            self.assertNotIn(zh, body)

    def test_owner_page_unchanged(self):
        h = render.render_wishlist(ROWS, [], "11.07", (), DB)
        self.assertNotIn('class="wctl"', h)
        self.assertNotIn("data-id=", h)
        self.assertNotIn("my_wish_add", h)
        self.assertIn("add_photo", h)

    def test_data_photo_is_not_prefixed(self):
        h = render.render_wishlist(ROWS, [], "11.07", (), DB, own=True)
        self.assertNotIn("wishlist/data:", h)
        self.assertIn("data:image/jpeg", render._side([], "2026-11-07", ROWS))

    def test_customer_rpcs_take_no_account(self):
        self.assertNotIn("WL_ACCOUNT", render.OWN_WISH_JS)   # account はログインの鍵から決まる
        self.assertNotIn("p_account", render.OWN_WISH_JS)

    def test_table_is_closed(self):
        sql = (ROOT / "db/wishes.sql").read_text(encoding="utf-8")
        self.assertIn("enable row level security", sql)
        self.assertIn("revoke all on public.wishes from anon, authenticated", sql)
        for fn in ("my_wishes()", "my_photo_inbox()"):
            self.assertIn(f"revoke all on function public.{fn} from public, anon", sql)


if __name__ == "__main__":
    unittest.main()
