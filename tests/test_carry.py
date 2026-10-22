"""前の日の「整理待ち」を今日に持ち越す（2026-10-22 全体の検査 H3）：AI 編集は最新の inbox しか見ないので、
JST 18:00 の回のあと日付が変わるまでに集めた分は、持ち越さないと二度と版面に載らない。

    python -m unittest tests.test_carry
"""

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import gate  # noqa: E402


def entry(n, title, **kw):
    return {"n": n, "title": title, "url": f"https://news.example.jp/{n}-{title}", "source": "example", **kw}


class CarryOver(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.p = mock.patch.object(digest, "INBOX_DIR", self.dir)
        self.p.start()
        self.reports = pathlib.Path(tempfile.mkdtemp())   # 公開済み（reports）は空：本物の reports を読まない
        self.r = mock.patch.object(digest, "REPORTS_DIR", self.reports)
        self.r.start()
        self.s = mock.patch.object(digest, "_carry_caps", lambda: (lambda name: digest.SIZE_STORIES["M"] * digest.CARRY_PER_SIZE))
        self.s.start()
        (self.dir / "2026-10-21.json").write_text(json.dumps({"date": "2026-10-21", "items": [
            {"name": "GTA 6", "facts": [], "entries": [entry(1, "a"), entry(2, "b"), entry(3, "c", urgent=True), entry(4, "d")]},
            {"name": "あつ森", "facts": [], "entries": [entry(1, "x")]},
            {"name": "ILLIT", "facts": [], "entries": [entry(1, "y")]},
        ]}, ensure_ascii=False), encoding="utf-8")
        # GTA 6 は 1 件目まで編集済み・あつ森は edit.json にある（全部編集済み）・ILLIT は edit.json にない（全部まだ）
        (self.dir / "2026-10-21.edit.json").write_text(json.dumps({"_covered": {"GTA 6": 1}, "GTA 6": [], "あつ森": []}), encoding="utf-8")

    def tearDown(self):
        self.p.stop()
        self.r.stop()
        self.s.stop()

    def test_carries_only_unedited_and_not_urgent(self):
        data, n = digest.carry_over({"date": "2026-10-22", "items": [
            {"name": "GTA 6", "facts": [], "entries": [entry(1, "new")]}]}, "2026-10-22")
        self.assertEqual(n, 3)
        got = {b["name"]: [(e["n"], e["title"], e.get("carried")) for e in b["entries"]] for b in data["items"]}
        self.assertEqual(got["GTA 6"], [(1, "new", None), (2, "b", "2026-10-21"), (3, "d", "2026-10-21")])   # 番号は今日の続き
        self.assertEqual(got["ILLIT"], [(1, "y", "2026-10-21")])
        self.assertNotIn("あつ森", got)
        self.assertEqual(data["_carried"], "2026-10-21")

    def test_only_once_a_day(self):
        data, n = digest.carry_over({"date": "2026-10-22", "items": []}, "2026-10-22")
        again, m = digest.carry_over(data, "2026-10-22")
        self.assertEqual((n, m), (3, 0))
        self.assertEqual(sum(len(b["entries"]) for b in again["items"]), 3)

    def test_too_old_is_left(self):
        data, n = digest.carry_over({"date": "2026-10-25", "items": []}, "2026-10-25")
        self.assertEqual((n, data["items"]), (0, []))

    def test_cap_is_size_times_two(self):
        """1 版面の上限は篇幅 × 2（S 6・M 10・L 16）。新しいほう（番号の大きいほう）を残す。篇幅のない版面は M。"""
        (self.dir / "2026-10-21.json").write_text(json.dumps({"date": "2026-10-21", "items": [
            {"name": "三星手机", "facts": [], "entries": [entry(k, f"s{k}") for k in range(1, 31)]},
            {"name": "GTA 6", "facts": [], "entries": [entry(k, f"g{k}") for k in range(1, 31)]},
            {"name": "滑雪", "facts": [], "entries": [entry(k, f"k{k}") for k in range(1, 31)]},
        ]}, ensure_ascii=False), encoding="utf-8")
        (self.dir / "2026-10-21.edit.json").write_text("{}", encoding="utf-8")
        self.s.stop()
        with mock.patch.object(digest, "load_sizes", lambda: {"三星手机": "L"}), \
                mock.patch.object(digest, "load_config", lambda: ({}, [{"name": "滑雪", "size": "s"}])):   # 数据库 → items.yaml の size
            data, n = digest.carry_over({"date": "2026-10-22", "items": []}, "2026-10-22")
        self.s.start()
        got = {b["name"]: [e["title"] for e in b["entries"]] for b in data["items"]}
        self.assertEqual({k: len(v) for k, v in got.items()}, {"三星手机": 16, "GTA 6": 10, "滑雪": 6})
        self.assertEqual(got["GTA 6"][0], "g21")   # 30 件のうち新しい 10 件
        self.assertEqual(n, 32)

    def test_already_published_is_not_carried(self):
        """今日と前の 3 日（4 号）の reports にもう載った記事（同じ網址・同じ見出し）は持ち越さない。それより前の号・別の版面は数えない。"""
        def report(day, name, stories):
            (self.reports / f"{day}.json").write_text(json.dumps({"date": day, "items": [{"name": name, "stories": stories}]},
                                                                 ensure_ascii=False), encoding="utf-8")
        b = entry(2, "b")
        report("2026-10-21", "GTA 6", [{"url": b["url"], "headline": "別の見出し"}])            # 同じ網址
        report("2026-10-20", "GTA 6", [{"url": "https://other.example/x", "headline": "Y - Example News"}])   # 別の版面の同じ見出しは数えない
        report("2026-10-18", "ILLIT", [{"url": "https://x.example/1", "headline": "y"}])          # 4 日前：数えない
        (self.dir / "2026-10-21.json").write_text(json.dumps({"date": "2026-10-21", "items": [
            {"name": "GTA 6", "facts": [], "entries": [entry(1, "a"), b, entry(3, "GTA 6 新トレーラーの公開日が発表された｜Infoseekニュース"), entry(4, "e")]},
            {"name": "ILLIT", "facts": [], "entries": [entry(1, "y")]},
        ]}, ensure_ascii=False), encoding="utf-8")
        report("2026-10-19", "GTA 6", [{"url": "https://other.example/d", "headline": "GTA 6 新トレーラーの公開日が発表された"}])   # 末尾の媒体名を除けば同じ見出し
        (self.dir / "2026-10-21.edit.json").write_text(json.dumps({"_covered": {"GTA 6": 1}, "GTA 6": []}), encoding="utf-8")
        data, n = digest.carry_over({"date": "2026-10-22", "items": []}, "2026-10-22")
        got = {b["name"]: [e["title"] for e in b["entries"]] for b in data["items"]}
        self.assertEqual(got, {"GTA 6": ["e"], "ILLIT": ["y"]})
        self.assertEqual(n, 2)

    def test_same_head_different_story_is_carried(self):
        """媒体名・頭が同じでも本文が違えば別の話：持ち越す（2026-10-22 検査：_clean_title で本文ごと消して頭だけで比べ、別の話を落としていた）。"""
        (self.reports / "2026-10-21.json").write_text(json.dumps({"date": "2026-10-21", "items": [
            {"name": "周杰伦", "stories": [{"url": "https://a.example/1", "headline": "討論牆 | 影音／周杰倫演唱會遇74歲阿嬤歌迷 她喊「聽你歌長大」"}]},
            {"name": "漫威", "stories": [{"url": "https://a.example/2", "headline": "Spider-Man: Brand New Day trailer drops"}]},
            {"name": "滑雪", "stories": [{"url": "https://a.example/3", "headline": "八千穂高原スキー場、2026-27シーズンの早割リフト券を発売"},
                                       {"url": "https://a.example/4", "headline": "Bataleon - Evil Twin 2027 Snowboard"}]},
        ]}, ensure_ascii=False), encoding="utf-8")
        (self.dir / "2026-10-21.json").write_text(json.dumps({"date": "2026-10-21", "items": [
            {"name": "周杰伦", "facts": [], "entries": [entry(1, "討論牆 | 周杰倫驚傳進軍房地產 欲賣與昆凌的豪宅")]},
            {"name": "漫威", "facts": [], "entries": [entry(1, "Spider-Man 4 delayed to 2027"), entry(2, "Spider-Man: Brand New Day box office record")]},
            {"name": "滑雪", "facts": [], "entries": [entry(1, "八千穂高原スキー場、2026-27シーズンは12月13日オープン"),
                                                    entry(2, "Bataleon - Thunder 2027 Snowboard")]},
        ]}, ensure_ascii=False), encoding="utf-8")
        (self.dir / "2026-10-21.edit.json").write_text("{}", encoding="utf-8")
        data, n = digest.carry_over({"date": "2026-10-22", "items": []}, "2026-10-22")
        self.assertEqual(n, 5)
        self.assertFalse(digest._title_keys("討論牆 | 周杰倫驚傳進軍房地產") & digest._title_keys("討論牆 | 周杰倫演唱會遇阿嬤歌迷"))

    def test_same_head_different_item_is_carried(self):
        """「長い共通の頭 | 品目」の別の記事：末尾を切った鍵どうしは同じになるが、載った見出しは生の鍵とだけ比べるので持ち越す（2026-10-22 検査）。"""
        (self.reports / "2026-10-21.json").write_text(json.dumps({"date": "2026-10-21", "items": [
            {"name": "ちいかわ", "stories": [{"url": "https://a.example/1", "headline": "ちいかわマーケット 新商品のお知らせ | ぬいぐるみ"}]},
        ]}, ensure_ascii=False), encoding="utf-8")
        (self.dir / "2026-10-21.json").write_text(json.dumps({"date": "2026-10-21", "items": [
            {"name": "ちいかわ", "facts": [], "entries": [entry(1, "ちいかわマーケット 新商品のお知らせ | キーホルダー")]},
        ]}, ensure_ascii=False), encoding="utf-8")
        (self.dir / "2026-10-21.edit.json").write_text("{}", encoding="utf-8")
        self.assertTrue(digest._title_keys("ちいかわマーケット 新商品のお知らせ | ぬいぐるみ")
                        & digest._title_keys("ちいかわマーケット 新商品のお知らせ | キーホルダー"))   # 切った鍵どうしは同じ
        data, n = digest.carry_over({"date": "2026-10-22", "items": []}, "2026-10-22")
        self.assertEqual(n, 1)

    def test_carried_only_once(self):
        """持ち越した記事（carried）は次の日にもう一度は持ち越さない（1 回だけ）。"""
        (self.dir / "2026-10-22.json").write_text(json.dumps({"date": "2026-10-22", "items": [{"name": "GTA 6", "facts": [], "entries": [
            entry(1, "a", carried="2026-10-21"), entry(2, "new")]}]}, ensure_ascii=False), encoding="utf-8")
        (self.dir / "2026-10-22.edit.json").write_text("{}", encoding="utf-8")
        data, n = digest.carry_over({"date": "2026-10-23", "items": []}, "2026-10-23")
        self.assertEqual([e["title"] for b in data["items"] for e in b["entries"]], ["new"])

    def test_gate_sees_carried_work(self):
        data, _ = digest.carry_over({"date": "2026-10-22", "items": []}, "2026-10-22")
        (self.dir / "2026-10-22.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(gate.edit_work(self.dir, today="2026-10-22"), {"GTA 6": 2, "ILLIT": 1})   # AI 編集が起こされる


class RenderKeepsGoing(unittest.TestCase):
    def test_story_without_headline_is_skipped_not_crash(self):
        import render
        issue = {"date": "2026-10-22", "items": [{"name": "GTA 6", "stories": [
            {"url": "https://a.example/1", "weight": "normal"},                     # 見出しなし（2026-10-21 KeyError で 4 回止まった形）
            {"headline": "GTA 6 trailer", "url": "https://a.example/2", "weight": "lead"}]}]}
        works = render.collect([issue])
        self.assertEqual([x["headline"] for w in works for x in w["stories"]], ["GTA 6 trailer"])

    def test_write_page_soft_in_production_only(self):
        with mock.patch.object(digest, "_write_page", side_effect=KeyError("headline")), mock.patch("runlog.add"):
            with mock.patch.dict(digest.os.environ, {"WL_RENDER_SOFT": "1"}):
                self.assertIsNone(digest.write_page())          # 本番の収集：止めずに push へ
            with mock.patch.dict(digest.os.environ, {"WL_RENDER_SOFT": ""}):
                with self.assertRaises(KeyError):                # CI：今までどおり失敗で止まる
                    digest.write_page()


if __name__ == "__main__":
    unittest.main()
