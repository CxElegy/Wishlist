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

    def test_mentions_and_roster(self):
        stories = [("Game Reveals 18-Character Launch Roster\nRukia Kuchiki and Renji Abarai join", "d"), ("Other news\nRenji wins", "d")]
        n, roster = ef.mentions(["Rukia Kuchiki", "Renji Abarai", "Kon"], stories)
        self.assertEqual(n, {"Rukia Kuchiki": 1, "Renji Abarai": 2, "Kon": 0})
        self.assertEqual(roster, {"Rukia Kuchiki", "Renji Abarai"})

    def test_bonus(self):
        self.assertAlmostEqual(ef.bonus("A", {}, set(), {"a": 1}), 1.2)
        self.assertEqual(ef.bonus("A", {}, {"A"}, {}), 1.5)
        self.assertEqual(ef.bonus("A", {"A": 99}, set(), {}), 1.0)

    def test_rank_total_uses_bonus(self):
        s = {"A": 3.0, "B": 2.0}
        with mock.patch.object(ef, "score", lambda n, w, c, live=False: {"score": s[n]}):
            self.assertEqual([n for n, _ in ef.rank(["A", "B"], "w", {}, ctx=({}, {"B"}, {}))], ["B", "A"])


if __name__ == "__main__":
    unittest.main()
