"""写しが空＝「測れず」であって「壊れている」ではない（2026-11-02）。ux_check が空の写しで ✗ を偽造しないことを数える。"""
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import ux_check  # noqa: E402

SRC = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
URL = "https://abc.supabase.co/storage/v1/object/public/photos/x.webp"


class Blind(unittest.TestCase):
    def test_server_opens_is_none_not_false_without_cache(self):
        old = ux_check.storage_bytes
        try:
            ux_check.storage_bytes = lambda u, h=None, t=0: None
            self.assertIsNone(ux_check.server_opens(URL))
            ux_check.storage_bytes = lambda u, h=None, t=0: b"IMG"
            self.assertIs(ux_check.server_opens(URL), True)
        finally:
            ux_check.storage_bytes = old

    def test_nohead_real_skips_unmeasurable_but_keeps_real_breakage(self):
        fails = [("A", "u1"), ("B", "u2"), ("C", "u3"), ("C", "u4")]
        opens = {"u1": None, "u2": False, "u3": True, "u4": None}.get
        # A=測れず（外す）・B=開かない（残す）・C=開く＋測れず（外す）・D=写真なし（残す）
        self.assertEqual(ux_check.nohead_real(["A", "B", "C", "D"], fails, opens), ["B", "D"])

    def test_cache_blind_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            self.assertTrue(ux_check.cache_blind(d))
            for i in range(ux_check.CACHE_MIN - 1):
                (d / f"{i}.webp").write_bytes(b"x")
            self.assertTrue(ux_check.cache_blind(d))
            (d / "last.webp").write_bytes(b"x")
            self.assertFalse(ux_check.cache_blind(d))
        self.assertTrue(ux_check.cache_blind(pathlib.Path("/nonexistent/wl_cache")))

    def test_every_gray_sensitive_check_is_gated(self):
        """灰色の 8x8 で狂う点検（measured_bad・pkcut・pkv・余白・loose・tiny）は blind のとき ✗ にならない。1 つでも外れたら数えて落とす。"""
        for needle in ('[] if blind else measured_bad(meas)', 'st.get("pkcut") and not blind', 'st.get("pkv") and not blind',
                       'gp["bad"] and not blind', 'gp["unread"] > gp["n"] * 0.25 and not blind',
                       'st["loose"] and not blind', 'st.get("tiny") and not blind',
                       '[] if blind else dom_lead', 'not page and not blind and st["ph"][0]', 'if heads and not blind', 'if nohead and not blind'):
            self.assertEqual(SRC.count(needle), 1, needle)


if __name__ == "__main__":
    unittest.main()
