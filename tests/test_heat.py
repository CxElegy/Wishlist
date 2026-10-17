"""話題度（scripts/heat.py）の計算ルール。

    python -m unittest discover -s tests
"""

import datetime as dt
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import heat  # noqa: E402

TODAY = "2026-10-30"
D = dt.date.fromisoformat(TODAY)


def day(n):
    return (D - dt.timedelta(days=n)).isoformat()


def entry(n, i=0, source=None, title="News", urgent=False):
    return {"date": day(n) + "T03:00:00+00:00", "source": source or f"site{i}", "title": title,
            "url": f"https://e{i}.com/{n}/{i}/{title}", "urgent": urgent}


class Scales(unittest.TestCase):
    def test_rel_score(self):
        self.assertEqual(heat.rel_score(0, 5), 0)          # 本週ゼロ
        self.assertEqual(heat.rel_score(5, None), 50)      # 比べる平常がない：平常扱い
        self.assertAlmostEqual(heat.rel_score(9, 9), 50)   # 平常並み
        self.assertAlmostEqual(heat.rel_score(39, 9), 100)  # 4 倍
        self.assertLess(heat.rel_score(2, 20), 50)

    def test_abs_score(self):
        self.assertEqual(heat.abs_score(0, 100), 0)
        self.assertAlmostEqual(heat.abs_score(100, 100), 100)
        self.assertEqual(heat.abs_score(10 ** 6, 100), 100)

    def test_region(self):
        self.assertEqual([heat.region(t) for t in ("ゲーム発売", "게임", "遊戲新聞", "Game news")], ["ja", "ko", "zh", "en"])


class Compute(unittest.TestCase):
    def run_compute(self, items, inbox, issues=(), signals=None):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for date, data in inbox.items():
                p = pathlib.Path(tmp) / f"{date}.json"
                p.write_text(json.dumps({"date": date, "items": data}), encoding="utf-8")
                paths.append(p)
            return heat.compute(items, sorted(paths), list(issues), signals or {}, TODAY)

    def test_spike_against_own_normal(self):
        """平常は週 3 件の作品が今週 30 件 → 平常が週 30 件の作品が今週 30 件より上。"""
        quiet = [entry(n, i) for n in range(8, 36, 3) for i in range(1)]       # 平常：ぽつぽつ
        quiet += [entry(n % 6 + 1, i) for n, i in zip(range(30), range(100, 130))]  # 今週：急に 30 件
        busy = [entry(n % 35 + 1, i) for n, i in zip(range(180), range(200, 380))]  # いつも多い
        inbox = {day(40): [{"name": "Q", "entries": quiet}, {"name": "B", "entries": busy}]}
        r = self.run_compute([{"name": "Q", "use": ["google"]}, {"name": "B", "use": ["google"]}], inbox)
        vq = next(d for d in r["Q"]["dims"] if d["key"] == "volume")
        vb = next(d for d in r["B"]["dims"] if d["key"] == "volume")
        self.assertGreater(vq["score"], vb["score"])
        self.assertIn("平常の", vq["note"])

    def test_no_baseline_yet(self):
        inbox = {day(2): [{"name": "A", "entries": [entry(1, i) for i in range(5)]}]}
        r = self.run_compute([{"name": "A"}], inbox)["A"]
        self.assertIn("平常のデータを集め中", r["dims"][0]["note"])
        self.assertIsNone(r["delta"])                     # 7 日前と比べられない

    def test_missing_dims_are_not_zero(self):
        """Wikipedia も Reddit もない：その 2 つは除いて計算し、missing に書く。"""
        inbox = {day(2): [{"name": "A", "entries": [entry(1, i) for i in range(5)]}]}
        r = self.run_compute([{"name": "A"}], inbox)["A"]
        keys = [d["key"] for d in r["dims"]]
        self.assertNotIn("public", keys)
        self.assertNotIn("fandom", keys)
        self.assertEqual(r["missing"], ["一般の関心", "ファンの反応"])
        self.assertGreater(r["score"], 0)

    def test_breadth_counts_outlets_and_regions(self):
        one = [entry(1, i, source="same", title="News") for i in range(6)]
        wide = [entry(1, i, source=f"s{i}", title=t) for i, t in enumerate(["News", "ニュース", "新聞", "뉴스", "News", "ニュース"])]
        inbox = {day(2): [{"name": "One", "entries": one}, {"name": "Wide", "entries": wide}]}
        r = self.run_compute([{"name": "One"}, {"name": "Wide"}], inbox)
        b = {n: next(d for d in r[n]["dims"] if d["key"] == "breadth") for n in r}
        self.assertGreater(b["Wide"]["score"], b["One"]["score"])
        self.assertEqual(b["Wide"]["note"], "6 媒体・4 地域")

    def test_event_dimension(self):
        inbox = {day(2): [{"name": "A", "facts": [{"changed": True}], "entries": [entry(1, 0, urgent=True), entry(1, 1)]}]}
        issues = [{"date": day(1), "items": [{"name": "A", "stories": [
            {"url": "u1", "date": day(1), "weight": "hero", "event": {"date": day(-3), "label": "発売"}}]}]}]
        r = self.run_compute([{"name": "A"}], inbox, issues)["A"]
        ev = next(d for d in r["dims"] if d["key"] == "event")
        self.assertIn("重要ニュース 1 件", ev["note"])
        self.assertIn("状態に変化", ev["note"])
        self.assertIn("あと 3 日で予定", ev["note"])
        self.assertGreaterEqual(ev["score"], 90)

    def test_momentum_ignores_today(self):
        """今日の分（まだ途中）は勢いに入れない：昨日・おととい ÷ その前 5 日。"""
        rising = [entry(n, i) for n, i in [(1, 0), (1, 1), (1, 2), (2, 3), (2, 4), (2, 5), (5, 6)]]
        today_only = [entry(0, i) for i in range(10)]
        inbox = {day(1): [{"name": "R", "entries": rising}, {"name": "T", "entries": today_only}]}
        r = self.run_compute([{"name": "R"}, {"name": "T"}], inbox)
        m = {n: next(d for d in r[n]["dims"] if d["key"] == "momentum")["score"] for n in r}
        self.assertGreater(m["R"], 75)
        self.assertEqual(m["T"], 0)

    def test_wiki_and_fandom_signals(self):
        wiki = {day(n): (5000 if n <= 7 else 1000) for n in range(1, 40)}
        wiki["_at"] = TODAY
        signals = {"wiki": {"A": wiki}, "anilist": {"A": {day(0): {"trending": 80, "popularity": 1000}}}}
        inbox = {day(2): [{"name": "A", "entries": [entry(1, 0)]}]}
        r = self.run_compute([{"name": "A", "type": "anime", "use": ["google"]}], inbox, signals=signals)["A"]
        pub = next(d for d in r["dims"] if d["key"] == "public")
        self.assertIn("平常の 5.0 倍", pub["note"])
        fan = next(d for d in r["dims"] if d["key"] == "fandom")
        self.assertIn("AniList トレンド 80", fan["note"])

    def test_reddit_only_counts_when_ever_posted(self):
        inbox = {day(2): [{"name": "A", "entries": [entry(1, 0)]},
                          {"name": "B", "entries": [entry(1, 0), entry(1, 1, source="r/test")]}]}
        r = self.run_compute([{"name": "A"}, {"name": "B"}], inbox)
        self.assertIn("ファンの反応", r["A"]["missing"])
        self.assertNotIn("ファンの反応", r["B"]["missing"])

    def test_bad_data_is_skipped(self):
        inbox = {day(2): [{"name": "A", "entries": [{"url": "x", "date": "??"}, {"date": day(1)}, entry(1, 0)]}]}
        r = self.run_compute([{"name": "A"}, {"name": "Empty"}], inbox)
        self.assertIn("7 日で 2 件", r["A"]["dims"][0]["note"])   # 日付が壊れた条目は収集日で数える、URL のないものは除く
        self.assertEqual(r["Empty"]["score"], 0)


class Fetch(unittest.TestCase):
    def test_fetch_keeps_daily_max_and_prunes(self):
        signals = {"steam": {"G": {TODAY: 300, "2026-01-01": 5}, "Gone": {TODAY: 1}}}
        with mock.patch.object(heat, "steam_players", return_value=120):
            heat.fetch_signals([{"name": "G", "steam_appid": 1}], signals, TODAY, log=io.StringIO())
        self.assertEqual(signals["steam"]["G"], {TODAY: 300})   # 1 日の最大値を残し、古い日は消す
        self.assertNotIn("Gone", signals["steam"])                # ウォッチリストから消えたものは消す

    def test_fetch_failure_keeps_old_data(self):
        signals = {"wiki": {"A": {"_at": "2026-10-29", day(1): 10}}}
        log = io.StringIO()
        with mock.patch.object(heat, "wiki_views", side_effect=OSError("429")):
            heat.fetch_signals([{"name": "A", "wiki": ["en:A"]}], signals, TODAY, log=log)
        self.assertIn("429", log.getvalue())
        self.assertEqual(signals["wiki"]["A"][day(1)], 10)

    def test_partial_wiki_keeps_old_and_retries(self):
        """日本語だけ取れなかった：前の（全言語の合計）データを残し、取得済みの印も付けない。"""
        old = {"_at": "2026-10-29", day(1): 500}
        signals = {"wiki": {"A": dict(old)}}
        got = ({"en:A": {day(1): 100}, "en:B": {day(1): 40}}, {"ja"})
        with mock.patch.object(heat, "wiki_views", return_value=got):
            heat.fetch_signals([{"name": "A", "wiki": ["en:A", "ja:A"]}, {"name": "B", "wiki": ["en:B", "ja:B"]}],
                               signals, TODAY, log=io.StringIO())
        self.assertEqual(signals["wiki"]["A"], old)                 # 古い完全なデータのまま
        self.assertEqual(signals["wiki"]["B"], {day(1): 40})       # 初めて：取れた分だけ入れる、_at なし＝次回もう一度


if __name__ == "__main__":
    unittest.main()


class GroupOrder(unittest.TestCase):
    """小分類の話題度（材料をまとめて測る）と、板块の中の並び（小分類の話題度 → 作品の話題度、下級は上級のすぐ後ろ）。"""

    def test_order(self):
        items = [{"name": "a", "section": "S", "sub": "x"}, {"name": "b", "section": "S", "sub": "y"},
                 {"name": "c", "section": "S", "sub": "y"}, {"name": "k", "section": "S", "sub": "x", "parent": "a"},
                 {"name": "z", "section": "T", "sub": "q"}]
        scores = {"a": {"score": 10}, "b": {"score": 20}, "c": {"score": 50}, "k": {"score": 99}, "z": {"score": 1}}
        sub = {("S", "x"): {"score": 30}, ("S", "y"): {"score": 60}, ("T", "q"): {"score": 5}}
        self.assertEqual(heat.heat_order(items, scores, sub, ["T", "S"]), ["z", "c", "b", "a", "k"])

    def test_group_is_not_a_sum(self):
        d = "2026-10-16"
        inbox = self.tmp_inbox(d, {"a": ["u1", "u2"], "b": ["u2", "u3"]})
        items = [{"name": "a"}, {"name": "b"}]
        g = heat.group_scores(items, [inbox], [], {}, d, {("S", "x"): ["a", "b"]})[("S", "x")]
        self.assertIn("7 日で 3 件", g["dims"][0]["note"])         # 同じ記事（u2）は 1 回だけ
        self.assertLessEqual(g["score"], 100)

    def tmp_inbox(self, d, by):
        import json, tempfile
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump({"date": d, "items": [{"name": n, "entries": [{"url": u, "date": d, "title": u, "source": "x.com"} for u in us]}
                                        for n, us in by.items()]}, f)
        f.close()
        return f.name
