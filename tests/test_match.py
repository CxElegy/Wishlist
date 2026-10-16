"""关注项的 match：普通词忽略大小写和空格；「re:」开头的是正则，区分大小写。

    python -m unittest discover tests
"""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import sources  # noqa: E402

# 剧名是常用英文词 from 的关注项（items.yaml 的 FROM 用的就是这种写法）
FROM = {"name": "FROM", "type": "show", "keywords": ["FROM season 5"],
        "match": ["Fromville", "'From'", r"re:\bFROM\b", r"re:^From (Season|season|S)\s?\d"]}
NOW = dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc)


def entry(title, n, source="媒体"):
    return sources.Entry(title=title, url=f"https://example.com/{n}", source=source, summary="", image="", published=NOW)


class MatchTest(unittest.TestCase):
    def kept(self, titles, source="媒体"):
        es = [entry(t, i, source) for i, t in enumerate(titles)]
        return [e.title for e in digest.filter_entries(es, FROM, {}, set(), NOW)]

    def test_show_titles_are_kept(self):
        titles = ["From Season 5: What to Expect in the Final Outing", "FROM Season 5 trailer drops",
                  "'From' is coming to Netflix US", "Theories about Fromville's origin"]
        self.assertEqual(self.kept(titles), titles)

    def test_ordinary_from_season_is_dropped(self):
        titles = ["Top 5 prospects from season 10 of Dana White's Contender Series",
                  "Episode 5 from Season Two of Documentary Series “Knife Edge”",
                  "why did hotd go downhill from season 2 itself"]
        self.assertEqual(self.kept(titles), [])


if __name__ == "__main__":
    unittest.main()
