"""言語違いの同じニュース（scripts/lang.py）：主言語の 1 本だけ残す。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import lang  # noqa: E402
import render  # noqa: E402

LANGS = ["ja", "en", "zh", "ko"]
EN = {"headline": "Zenless Zone Zero v3.3 “Journey to the Sky” update revealed", "date": "2026-10-17",
      "event": {"date": "2026-10-21", "label": "配信日"}, "weight": "lead", "_issue": "2026-10-17", "url": "https://e/1"}
JA = {"headline": "10/9 『ゼンレスゾーンゼロ』Ver.3.3が10月21日(水)にリリース", "date": "2026-10-09",
      "event": {"date": "2026-10-21", "label": "配信日"}, "weight": "normal", "_issue": "2026-10-16", "url": "https://j/1"}
KO = {"headline": "10/12 '젠존제', 3.3 버전 '다시 하늘을 향해' 21일 업데이트…11월 ’지스타 2026' 참가", "date": "2026-10-12",
      "weight": "normal", "_issue": "2026-10-16", "url": "https://k/1"}
ZH = {"headline": "库克到访米哈游，亲测折叠屏iPhone体验游戏《绝区零》", "date": "2026-10-15", "weight": "normal",
      "_issue": "2026-10-16", "url": "https://z/1"}


class DetectTest(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(lang.detect(JA["headline"]), "ja")
        self.assertEqual(lang.detect(EN["headline"]), "en")
        self.assertEqual(lang.detect(KO["headline"]), "ko")
        self.assertEqual(lang.detect(ZH["headline"]), "zh")
        self.assertEqual(lang.detect("台北の新店開幕"), "zh")   # 「の」1 字では日本語にしない
        self.assertEqual(lang.detect("3.3"), "")

    def test_keys(self):
        self.assertEqual(lang.keys(EN["headline"]), {"v3.3"})
        self.assertEqual(lang.keys(JA["headline"]), {"v3.3", "m10-21"})   # 先頭の「10/9 」は記事の日付なので鍵にしない
        self.assertIn("m10-21", lang.keys("New banner arrives October 21"))
        self.assertEqual(lang.keys("蒂姆·库克收到绝区零手办，这 1/7 比例细节有点东西"), set())

    def test_order(self):
        self.assertEqual(lang.order({"languages": {"primary": "ja", "secondary": ["en", "ja", "zh"]}}), ["ja", "en", "zh"])
        self.assertEqual(lang.order({})[0], "ja")


class DedupeTest(unittest.TestCase):
    def test_keeps_primary_and_inherits(self):
        out = lang.dedupe([EN, ZH, JA, KO], LANGS)
        self.assertEqual([x["url"] for x in out], ["https://j/1", "https://z/1"])
        self.assertEqual(out[0]["weight"], "lead")          # 消した英語版の頭条を引き継ぐ
        self.assertEqual(out[0]["_issue"], "2026-10-17")    # 新しい号に出た扱い
        self.assertEqual(out[0]["headline"], JA["headline"])

    def test_secondary_when_no_primary(self):
        out = lang.dedupe([KO, EN], LANGS)
        self.assertEqual([x["url"] for x in out], ["https://e/1"])

    def test_same_language_and_far_apart_untouched(self):
        en2 = {**EN, "headline": "Zenless Zone Zero v3.3 banners leak", "url": "https://e/2"}
        self.assertEqual(len(lang.dedupe([EN, en2], LANGS)), 2)
        old = {**JA, "date": "2026-09-01"}
        self.assertEqual(len(lang.dedupe([EN, old], LANGS)), 2)

    def test_unlisted_language_dropped(self):
        self.assertEqual([x["url"] for x in lang.dedupe([KO, ZH], ["ja", "en"])], [])

    def test_refs_merged(self):
        a, b = {**EN, "refs": [3, 4]}, {**JA, "refs": [1]}
        self.assertEqual(lang.dedupe([a, b], LANGS)[0]["refs"], [1, 3, 4])

    def test_prefer_ref(self):
        titles = {1: "Zenless Zone Zero v3.3 update revealed - Gaming Age", 2: "『ゼンゼロ』Ver.3.3が10月21日にリリース - GameWith"}
        s = lang.prefer_ref({"headline": "Zenless Zone Zero v3.3 update revealed", "highlight": "v3.3", "blurb": "Arrives Oct 21.",
                             "refs": [1, 2]}, titles, LANGS)
        self.assertEqual(s["headline"], "『ゼンゼロ』Ver.3.3が10月21日にリリース")
        self.assertEqual(s["refs"], [2, 1])
        self.assertEqual(s["blurb"], "")   # 英語の blurb は日本語の見出しと合わないので消す（翻訳しない）


class RenderTest(unittest.TestCase):
    def test_collect_and_agenda(self):
        issues = [{"date": "2026-10-17", "items": [{"name": "绝区零", "stories": [EN]}]},
                  {"date": "2026-10-16", "items": [{"name": "绝区零", "stories": [JA, KO, ZH]}]}]
        works = render.collect(issues, ["绝区零"], LANGS)
        self.assertEqual([x["url"] for x in works[0]["stories"]], ["https://z/1", "https://j/1"])
        html = render._agenda(works, "2026-10-17")
        self.assertEqual(html.count("<li"), 1)
        self.assertIn("ゼンレスゾーンゼロ", html)

    def test_agenda_same_day_label_once(self):
        a = {**EN, "headline": "Something totally different", "event": {"date": "2026-10-21", "label": "配信日"}}
        works = [{"name": "绝区零", "section": "ゲーム", "stories": [a, {**JA, "url": "https://j/9"}], "_langs": LANGS}]
        html = render._agenda(works, "2026-10-17")
        self.assertEqual(html.count("<li"), 1)
        self.assertIn("ゼンレスゾーンゼロ", html)   # 主言語の方


if __name__ == "__main__":
    unittest.main()
