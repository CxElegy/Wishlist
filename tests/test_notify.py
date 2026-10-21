"""Discord の通知（2026-10-22 全体の検査 H5）：週報は上限（1 通 embed 10 個・合計 6,000 字）に収まるよう分けて送り、
送れなかったら「送った」にしない。ネットには出ない（send を差し替える）。

    python -m unittest tests.test_notify
"""

import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import notify  # noqa: E402


def size(part):
    return sum(len(em.get("title") or "") + len(em.get("description") or "") for em in part)


class SplitEmbeds(unittest.TestCase):
    def test_parts_fit_discord_limits(self):
        embeds = [{"title": f"作品{i}", "description": "あ" * 900} for i in range(12)]   # 7,000 字・12 個
        parts = notify.split_embeds(embeds)
        self.assertGreater(len(parts), 1)
        self.assertEqual(sum(len(p) for p in parts), 12)   # 1 つも落とさない
        for p in parts:
            self.assertLessEqual(len(p), 10)
            self.assertLessEqual(size(p), 6000)

    def test_long_description_is_cut(self):
        part, = notify.split_embeds([{"title": "x", "description": "あ" * 5000}])
        self.assertLessEqual(len(part[0]["description"]), 4096)

    def test_empty(self):
        self.assertEqual(notify.split_embeds([]), [])


class Weekly(unittest.TestCase):
    def test_real_reports_are_sent_in_fitting_parts_and_failure_is_reported(self):
        sent = []
        with mock.patch.object(notify, "send", lambda payload: sent.append(payload) or True):
            self.assertTrue(notify.weekly("https://cxelegy.github.io/Wishlist/home/"))
        for p in sent:
            self.assertLessEqual(len(p.get("embeds") or []), 10)
            self.assertLessEqual(size(p.get("embeds") or []), 6000)
        with mock.patch.object(notify, "send", lambda payload: False):
            self.assertFalse(notify.weekly("https://cxelegy.github.io/Wishlist/home/"))   # 送れなかった = False（心拍に「已发送」と書かない）


if __name__ == "__main__":
    unittest.main()
