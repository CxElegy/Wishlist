import sys
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import emblem  # noqa: E402


class _R:
    def __init__(self, b):
        self.b = b

    def read(self, n):
        return self.b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FandomGap(unittest.TestCase):
    """Fandom の api.php は wikihttp の道（test_wikihttp）。ここは wikihttp を通らない画像などのホスト（static.wikia.nocookie.net）。"""
    def setUp(self):
        emblem._next.clear()

    def test_429_waits_retry_after_then_succeeds(self):
        sleeps, calls = [], []
        err = urllib.error.HTTPError("u", 429, "x", {"Retry-After": "7"}, None)

        def op(req, timeout=0):
            calls.append(1)
            if len(calls) == 1:
                raise err
            return _R(b"ok")
        with mock.patch.object(emblem.urllib.request, "urlopen", op), mock.patch.object(emblem, "_sleep", sleeps.append):
            self.assertEqual(emblem._get("https://static.wikia.nocookie.net/bleach/a.png"), b"ok")
        self.assertEqual(len(calls), 2)
        self.assertTrue(any(6 < s <= 7.1 for s in sleeps), sleeps)

    def test_one_at_a_time_per_host(self):
        active, peak = [0], [0]

        def op(req, timeout=0):
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            import time
            time.sleep(0.02)
            active[0] -= 1
            return _R(b"ok")
        with mock.patch.object(emblem.urllib.request, "urlopen", op), mock.patch.object(emblem, "_sleep", lambda s: None):
            ts = [threading.Thread(target=emblem._get, args=("https://static.wikia.nocookie.net/dota2/a.png",)) for _ in range(6)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(peak[0], 1)


if __name__ == "__main__":
    unittest.main()
