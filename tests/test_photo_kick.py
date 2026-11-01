"""render を発布する workflow は全部、そのあと写真の一時保管を起こす段（photo_store.py --kick）を持つ。
2026-11-01：render.yml だけに足して、収集の回（digest.yml・background.yml）で入った新しい記事の写真が次の定時まで原寸のままだった。"""
import pathlib
import unittest

WF = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"


class PhotoKick(unittest.TestCase):
    def test_every_render_workflow_kicks_photo_store(self):
        pub = [f for f in sorted(WF.glob("*.yml")) if "digest.py render" in f.read_text(encoding="utf-8") and "git push" in f.read_text(encoding="utf-8")]   # 発布する（push する）ものだけ。ci.yml は作れるか見るだけ
        self.assertGreaterEqual(len(pub), 3)   # render・digest・background
        for f in pub:
            t = f.read_text(encoding="utf-8")
            self.assertIn("photo_store.py --kick", t, f"{f.name} は網页を発布するのに写真の一時保管を起こす段がない")
            self.assertRegex(t, r"actions:\s*write", f"{f.name} に actions: write がない（gh workflow run が拒まれる）")


if __name__ == "__main__":
    unittest.main()
