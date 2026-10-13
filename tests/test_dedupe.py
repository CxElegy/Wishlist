"""不用 AI 时的编排（fallback_stories）：不同语言写的同一件事合成一条。

    python -m unittest discover tests
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import sources  # noqa: E402

ITEM = {"name": "Astrae Oratio", "type": "game", "keywords": ["Astrae Oratio", "アストラエ・オラティオ"], "match": ["Astrae"]}


def entry(title, n):
    return sources.Entry(title=title, url=f"https://example.com/{n}", source=f"媒体{n}", summary="", image="", published=None)


class EventMergeTest(unittest.TestCase):
    def test_same_event_in_three_languages_is_one_story(self):
        es = [entry("【アストラエ・オラティオ】NCが「AGF 2026」に出展決定！KINTEXで開催", 1),
              entry("아스트라에 오라티오, AGF 2026 메인 스폰서 맡는다", 2),
              entry("Astrae Oratio 宣布參加韓國 AGF 2026 活動", 3),
              entry("Astrae Oratio CBT review: combat thoughts", 4)]
        stories = digest.fallback_stories(es, ITEM)
        self.assertEqual(len(stories), 2)
        agf = next(s for s in stories if 1 in s["refs"] or 2 in s["refs"])
        self.assertEqual(sorted(agf["refs"]), [1, 2, 3])
        self.assertNotIn("_events", agf)

    def test_rare_or_common_tokens_do_not_merge(self):
        # 只出现两次的专有词、常见缩写（CBT、PC）、短型号都不当成同一件事
        es = [entry("Astrae Oratio CBT 後記", 1), entry("Astrae Oratio CBT 戦闘まとめ", 2), entry("Astrae Oratio CBT 感想", 3),
              entry("TGS2026 Astrae Oratio ステージ", 4), entry("TGS2026 物販情報", 5)]
        stories = digest.fallback_stories(es, ITEM)
        self.assertTrue(all(len(s["refs"]) == 1 for s in stories))


if __name__ == "__main__":
    unittest.main()
