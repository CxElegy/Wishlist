import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emblem_fame as ef  # noqa: E402


class Fame(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(ef._norm("Tōshirō  Hitsugaya"), "toshiro hitsugaya")

    def test_rank_by_score_stable(self):
        s = {"A": 1.0, "B": 3.0, "C": 3.0}
        with mock.patch.object(ef, "score", lambda n, w, c, live=False: {"score": s[n]}):
            self.assertEqual([n for n, _ in ef.rank(["A", "B", "C"], "w", {})], ["B", "C", "A"])

    def test_score_uses_best_source_and_cache(self):
        with mock.patch.object(ef, "anilist", return_value=(999, "X")), mock.patch.object(ef, "wikipedia", return_value=(3000, "X")), \
                mock.patch.object(ef.time, "sleep"):
            cache = {}
            r = ef.score("X", "w", cache)
            self.assertEqual(r["src"], "AniList")   # 999 未満の AniList は Wikipedia も引き、高いほうを取る
            self.assertAlmostEqual(r["score"], 3.0, 1)
            self.assertIs(ef.score("X", "w", cache), r)


if __name__ == "__main__":
    unittest.main()
