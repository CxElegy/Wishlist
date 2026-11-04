"""外の網が落ちた回に repair-images が報道の画像を外さない（2026-11-04）。網エラー・タイムアウト・429・5xx は「この画像はだめ」ではない。"""
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import images  # noqa: E402


class Unusable(unittest.TestCase):
    def _u(self, fetched, n):
        images._checks.clear()
        images._transient.clear()
        with mock.patch.object(images, "_fetch", return_value=fetched):
            return images.unusable(f"https://example.com/{n}.jpg")

    def test_network_trouble_is_not_a_verdict(self):
        for i, f in enumerate([images.Fetched(error="网络错误 gaierror"), images.Fetched(error="超时"),
                               images.Fetched(status=429), images.Fetched(status=503)]):
            self.assertFalse(self._u(f, i), f)

    def test_real_failures_are_a_verdict(self):
        for i, f in enumerate([images.Fetched(status=404), images.Fetched(status=403),
                               images.Fetched(status=200, headers={"content-type": "text/html"}, body=b"<html>")]):
            self.assertTrue(self._u(f, 10 + i), f)


if __name__ == "__main__":
    unittest.main()
