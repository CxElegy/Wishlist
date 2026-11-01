"""店長のページとお客さまのページの違いの点検（harness/diff_admin.py）と、その根の直し。"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import diff_admin  # noqa: E402


class Diff(unittest.TestCase):
    def test_only_missing_parts_count(self):
        admin = {"a": 3, "b": 1, "c": 0, "__admin_link": 1}
        self.assertEqual(diff_admin.diff(admin, {"a": 1, "b": 0, "c": 0}), ["b"])   # 店長に見えてお客さまにない部品だけ

    def test_admin_only_is_not_counted(self):
        k = next(iter(diff_admin.ADMIN_ONLY))
        self.assertEqual(diff_admin.diff({k: 1}, {k: 0}), [])

    def test_admin_only_has_reason(self):
        self.assertTrue(all(v for v in diff_admin.ADMIN_ONLY.values()))   # 「管理なので無し」は理由を名前で書く


class Waits(unittest.TestCase):
    def test_data_wait_is_not_a_failure_but_must_is(self):
        admin = {"これからの予定": 1, "気になるかも？の棚": 1}
        self.assertEqual(diff_admin.diff(admin, {}, who="test-b"), [])                 # 材料がない人はデータ待ち
        self.assertEqual(diff_admin.diff(admin, {}, who="test-b", wait=True), ["これからの予定", "気になるかも？の棚"])
        self.assertEqual(diff_admin.diff(admin, {}, who="test-a"), ["気になるかも？の棚"])   # test-a は材料が十分：出なければ ✗

    def test_empty_account_skips_board_parts_only(self):
        admin = {"版面": 1, "目次：ロゴ": 1}
        self.assertEqual(diff_admin.diff(admin, {}, empty=True), ["目次：ロゴ"])         # 枠組みは版面 0 個でも比べる

    def test_agenda_comes_from_past_issues_too(self):
        import render
        import user_pages
        st = {"headline": "発売日", "url": "https://e.com/a", "event": {"date": "2026-11-20", "label": "発売"}}
        old = {"date": "2026-10-30", "no": 1, "items": [{"name": "X", "section": "游戏", "stories": [st]}]}
        p = user_pages.prev_issue([{"name": "X", "_shop": True, "size": "L", "section": "游戏"}], old)   # 過去の号の分も本人のページに渡る
        self.assertEqual(p["items"][0]["stories"][0]["event"]["label"], "発売")
        self.assertIn('class="agenda"', render._agenda(p["items"], "2026-11-02"))   # 日程が付けば、本人のページでも同じ部品で出る
        self.assertIsNone(user_pages.prev_issue([{"name": "Y", "_shop": True}], old))   # 追っていない版面だけの号は渡さない


class Roots(unittest.TestCase):
    SRC = (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")

    def test_heat_number_not_hidden_for_customers(self):
        line = self.SRC.split('html[data-mine="2"] .mastwish', 1)[1].split("\n", 1)[0]
        self.assertNotIn(".hm", line)   # 今日の最高（話題度）は店長と同じに出す

    def test_votes_and_picks_not_hidden_for_customers(self):
        line = self.SRC.split('html[data-mine="2"] .mastwish', 1)[1].split("\n", 1)[0]
        for k in (".vt", ".vote", "[data-vote]", ".picks"):
            self.assertNotIn(k, line)   # 👍👎・気になるかも？は店長と同じに出す（本人の票で）

    def test_own_votes_go_to_own_rpc(self):
        js = self.SRC.split('VOTE_JS = """', 1)[1].split('"""', 1)[0]
        for k in ("my_vote_add", "my_votes_own", "wl-own", "wishlist-votes-own"):
            self.assertIn(k, js)   # お客さまの票は本人の account の関数へ。店長の記憶（wishlist-votes）とも混ぜない

    def test_next_step_only_wishlist(self):
        self.assertEqual(set(diff_admin.NEXT_STEP), {"目次：欲しい物へのリンク", "見出し：欲しい物リストのボタン"})

    def test_nav_one_per_section_level(self):
        self.assertIn("①b", self.SRC)   # 板块が多くても各板块の駅が 1 つは見える


if __name__ == "__main__":
    unittest.main()
