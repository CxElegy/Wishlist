"""接続先の直書きを数える：旧 Supabase の ref がコード・設定に残っていない（2026-11-07 自前版へ移行）。
残してよいのは scripts/sbconf.py の OLD_REF と、説明の文書（*.md）・生成物（docs/ の html）だけ。"""
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sbconf  # noqa: E402

CODE = (".py", ".js", ".yml", ".yaml", ".sh")


class SbConf(unittest.TestCase):
    def test_reads_items_yaml(self):
        self.assertTrue(sbconf.url().startswith("https://"))
        self.assertNotIn(sbconf.OLD_REF, sbconf.url())
        self.assertTrue(sbconf.key().startswith("sb_publishable_"))

    def test_no_old_ref_in_code(self):
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.split("\n")
        bad = []
        for f in files:
            if not f.endswith(CODE) or f == "scripts/sbconf.py" or f.startswith(("docs/", "archive/", "tests/")):
                continue
            p = ROOT / f
            if p.is_file() and sbconf.OLD_REF in p.read_text(encoding="utf-8", errors="ignore"):
                bad.append(f)
        self.assertEqual(bad, [], "旧 Supabase の ref を直書き。scripts/sbconf.py から読む: " + ", ".join(bad))

    def test_old_ref_in_testground_only_when_generated(self):
        """見本ページ（docs/testground/*.html）は生成物。作り直せば新しい接続先になる（旧 ref が残る = 作り直し忘れ）。"""
        bad = [p.name for p in (ROOT / "docs/testground").glob("*.html") if sbconf.OLD_REF in p.read_text(encoding="utf-8", errors="ignore")]
        self.assertEqual(bad, [], "見本ページを作り直す: " + ", ".join(bad))


if __name__ == "__main__":
    unittest.main()
