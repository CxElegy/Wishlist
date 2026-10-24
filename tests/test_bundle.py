"""出来事ごとの束（scripts/bundle.py）と、増えた分だけの edit-brief（digest.edit_brief）。例は本番の inbox の見出し。"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import bundle  # noqa: E402
import digest  # noqa: E402


def ents(*titles, date="2026-10-21T01:00:00+00:00"):
    return [{"n": i, "title": t, "source": "x", "date": date} for i, t in enumerate(titles, 1)]


class BundleTest(unittest.TestCase):
    def test_same_story_bundles_across_languages(self):
        es = ents("『ゼンレスゾーンゼロ』Ver.3.3が10月21日配信！ S級フィオニー＆セヴェリアン登場",
                  "Zenless Zone Zero Version 3.3 Update Arrives October 21",
                  "‘젠레스 존 제로’, 21일 3.3 버전 업데이트…신규 에이전트·메카 전투 추가",
                  "『ゼンレスゾーンゼロ』新しい水着イベントの告知")
        self.assertEqual(bundle.bundles({"name": "绝区零", "keywords": ["ゼンレスゾーンゼロ", "Zenless Zone Zero", "젠레스 존 제로"]}, es),
                         [[1, 2, 3], [4]])

    def test_same_story_same_language(self):
        es = ents("A2O LITE、デビュー1週間で音楽番組1位！ アンコールライブで披露した安定の歌唱力にも称賛続く",
                  "イ・スマン氏プロデュースのA2O LITE デビュー1週間で音楽番組1位獲得",
                  "A2O LITE、新しいファンクラブの開設を発表")
        self.assertEqual(bundle.bundles({"name": "A2O LITE"}, es), [[1, 2], [3]])

    def test_different_rounds_not_bundled(self):
        # 別の試合（勝ち上がりの回が違う）はまとめない
        es = ents("加藤未唯ペア 日本勢対決制しジャパンOP初戦突破、穂積絵莉ペアにストレート勝ち＜女子テニス＞（tennis365.net）",
                  "加藤未唯ペア 日本勢対決制しジャパンOP4強、激闘の末に準決勝進出＜女子テニス＞（tennis365.net）")
        self.assertEqual(bundle.bundles({"name": "日本顶级网球赛事"}, es), [[1], [2]])

    def test_different_scores_and_versions_not_bundled(self):
        self.assertTrue(bundle.conflict(bundle.facts("Liquid beat Spirit 2-0 in the upper bracket"),
                                        bundle.facts("Liquid beat Spirit 2-1 in the grand final")))
        self.assertTrue(bundle.conflict(bundle.facts("Ver.3.3 の新キャラ"), bundle.facts("Ver.3.4 の新キャラ")))
        self.assertFalse(bundle.conflict(bundle.facts("Ver.3.3 の新キャラ"), bundle.facts("新キャラの声優が決定")))
        self.assertEqual(bundle.facts("ジャパンOP初戦突破")["round"], {"r1"})   # 「OP」の英字に続いても初戦
        self.assertEqual(bundle.facts("準決勝進出")["round"], {"sf"})          # 「決勝」と数えない

    def test_source_and_tail_brackets_do_not_link(self):
        # 媒体名・大会名の［］（）だけが同じ別の試合
        es = ents("小堀桃子／清水綾乃がリューメラ・キッチュノック／二宮真琴を下して2年連続初戦突破 [木下グループジャパンオープンテニス]（テニスマガジンONLINE）",
                  "ワイルドカードで2年ぶりに出場の本玉真唯／内島萌夏は台湾ペアにストレート負け [木下グループジャパンオープンテニス]（テニスマガジンONLINE）")
        self.assertEqual(bundle.bundles({"name": "日本顶级网球赛事"}, es), [[1], [2]])

    def test_far_dates_not_bundled(self):
        es = ents("A2O LITE 音楽番組1位 デビュー1週間") + [{"n": 2, "title": "A2O LITE 音楽番組1位 デビュー1週間", "source": "y", "date": "2026-10-01"}]
        self.assertEqual(bundle.bundles({"name": "x"}, es), [[1], [2]])


class BriefTest(unittest.TestCase):
    def brief(self, entries, edit, ctl=None):
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "2026-10-21.json").write_text(json.dumps({"items": [{"name": "A2O LITE", "entries": entries}]}), encoding="utf-8")
        (d / "2026-10-21.edit.json").write_text(json.dumps(edit), encoding="utf-8")
        with mock.patch.object(digest, "INBOX_DIR", d), mock.patch.object(digest, "load_config", lambda: ({}, [{"name": "A2O LITE"}])):
            return digest.edit_brief(ctl=ctl or {"mode": "run", "redo": []})

    def test_only_new_and_grown_bundles_after_edit(self):
        es = ents("A2O LITE、デビュー1週間で音楽番組1位！ アンコールライブで披露した安定の歌唱力",
                  "A2O LITE、新しいファンクラブの開設を発表",
                  "イ・スマン氏プロデュースのA2O LITE デビュー1週間で音楽番組1位獲得",
                  "A2O LITE、日本デビューの日程が決まる")
        edit = {"A2O LITE": [{"headline": "A2O LITE 1位", "weight": "lead", "refs": [1]}, {"headline": "ファンクラブ", "refs": [2]}],
                "_covered": {"A2O LITE": 2}}
        out = self.brief(es, edit)
        self.assertIn("新しい束 1・記事が増えた束 1", out)
        self.assertIn("記事 1：[lead] A2O LITE 1位（refs 1）", out)   # 今の記事は 1 行ずつ
        self.assertIn("前に見た 1 → 記事 1 に足す", out)              # 3 は 1 と同じ話
        self.assertIn("\n3 ", out)
        self.assertIn("\n4 ", out)
        self.assertNotIn("ファンクラブの開設", out)                     # 増えていない束は見せない
        full = self.brief(es, edit, ctl={"mode": "run", "redo": ["A2O LITE"]})   # やり直す版面は全部
        self.assertIn("ファンクラブの開設", full)
        self.assertIn("＋ 3 x｜", full)                                 # 束の 2 本目からは題だけ

    def test_first_edit_shows_everything(self):
        out = self.brief(ents("A2O LITE、新しいファンクラブの開設を発表", "A2O LITE、日本デビューの日程が決まる"), {})
        self.assertIn("\n1 ", "\n" + out)
        self.assertIn("\n2 ", out)
        self.assertNotIn("今の記事", out)


if __name__ == "__main__":
    unittest.main()
