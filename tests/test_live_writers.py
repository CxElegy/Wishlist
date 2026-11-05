"""live_status／live_log／live_report の書き手を全部数える点検（2026-11-05 f1f2、#908 の続き）。
新しい書き手が scripts/ に増えたら、ここの表に「どの錠・どの重ね書き止めを通るか」を書かないと落ちる。書き手ごとの回数も数える。"""
import pathlib
import re
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import digest  # noqa: E402
import livestatus  # noqa: E402

# 書き手の入口（文字列）→ 使ってよいファイルと、通る止め方。増えたら表に足す（足せないなら止め方がない＝直す）
ENTRIES = {
    "live_mark(": {"digest.py": "指紋_LIVE_SENT・fetch 20 秒遅延・未書込 DELETE 省略・小元素 30 秒・Timer と DELETE は 1 本ずつ",
                   "emblem_fill.py": "digest.live_mark を通る（_live）"},
    "livestatus.report": {"digest.py": "_live_edit_report が同じ回の同一内容を送らない＋report 自身が同一内容を送らない",
                          "emblem_fill.py": "鍵なしの定時だけ（if not keyed）＋report 自身が同一内容を送らない"},
    "livestatus.Lines(": {"userfeed.py": "Lines.FLUSH 8 秒のまとめ送り・制限中は outbox",
                          "emblem_fill.py": "同上（本番のみ send）"},
    "livestatus.clear": {},
    "livestatus.clear_waits": {"live_clear.py": ""},
}
READERS = {"gate.py"}   # livestatus._db() で url・鍵を読むだけ（edit_control_get を sbstate.memo で 60 秒使い回し）。live_* には書かない


class Inventory(unittest.TestCase):
    def test_every_writer_is_listed(self):
        found = {}
        for f in (ROOT / "scripts").glob("*.py"):
            if f.name in ("processes.py", "livestatus.py"):
                continue
            src = f.read_text(encoding="utf-8")
            for ent in ENTRIES:
                for m in re.finditer(re.escape(ent), src):
                    line = src[:m.start()].count("\n")
                    text = src.splitlines()[line].lstrip()
                    if text.startswith("#") or "def " + ent.rstrip("(") in text:
                        continue
                    found.setdefault(ent, set()).add(f.name)
        for ent, files in found.items():
            if ent == "livestatus.clear" or ent == "livestatus.clear_waits":
                continue
            self.assertLessEqual(files, set(ENTRIES[ent]), f"{ent} の新しい書き手：{files - set(ENTRIES[ent])}（ENTRIES に止め方を書く）")

    def test_gate_only_reads(self):
        src = (ROOT / "scripts" / "gate.py").read_text(encoding="utf-8")
        self.assertNotIn("live_status", src)
        self.assertNotIn("live_log", src)
        self.assertNotIn("live_report", src)
        self.assertNotIn("livestatus.report", src)
        self.assertIn("sbstate.memo", src)   # edit_control_get は使い回し


class PerWriterCounts(unittest.TestCase):
    def test_lines_batches_many_adds_into_one_post(self):
        posts = []
        ln = livestatus.Lines("userfeed", send=lambda rows: posts.append(len(rows)))
        ln.stop.set()   # 時計で送らない：flush を手で
        for i in range(200):
            ln.add(f"行 {i}")
        ln.flush()
        ln.flush()
        self.assertEqual(posts, [200])   # 200 行でも POST は 1 回・空の flush は送らない

    def test_report_same_content_sent_once_clear_resets(self):
        sent = []
        with mock.patch.object(livestatus, "_db", return_value=("https://x.supabase.co", "k")), \
                mock.patch.object(livestatus.sbstate, "LIMITED", False), \
                mock.patch.object(livestatus.sbstate, "sb_open", lambda req, t: sent.append(req.data) or mock.Mock(read=lambda: b"")), \
                mock.patch.dict(livestatus._REPORTED, clear=True):
            for eta in (9, 8, 7, 6):
                livestatus.report("B", "emblem", "work", "小元素を集めています", eta)   # 残り時間だけの違い
            livestatus.report("B", "emblem", "wait", "反映待ち", 1)
            livestatus.report("B", "emblem", "clear")
            livestatus.report("B", "emblem", "clear")
            livestatus.report("B", "emblem", "work", "小元素を集めています", 9)   # 消したあとの同じ内容は、また書く
        self.assertEqual(len(sent), 4)   # work・wait・clear・work

    def test_emblem_unkeyed_live_not_doubled_by_keyed_path(self):
        src = (ROOT / "scripts" / "emblem_fill.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("live(name, \"emblem\", \"work\""), 1)
        self.assertIn("if not keyed:", src)

    def test_budget_constants(self):
        self.assertGreaterEqual(livestatus.Lines.FLUSH, 8)
        self.assertGreaterEqual(digest.LIVE_FETCH_SHOW_SEC, 20)
        self.assertGreaterEqual(digest.LIVE_EMBLEM_GAP_SEC, 30)


if __name__ == "__main__":
    unittest.main()
