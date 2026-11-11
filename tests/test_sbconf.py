"""接続先の直書きを数える：旧 Supabase の ref がコード・設定に残っていない（2026-11-07 自前版へ移行）。
残してよいのは scripts/sbconf.py の OLD_REF と、説明の文書（*.md）・生成物（docs/ の html）だけ。"""
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sbconf  # noqa: E402

OLD_KEY = "sb_publishable_EJunmcNeSQJOm2bnzc4JWA_u48iV4NC"   # 旧プロジェクトの publishable key
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

    def test_no_old_ref_in_published_or_archive(self):
        """公開物（docs/ の html・js・json）と控え（archive/ の yaml）にも旧 ref・旧 publishable key を残さない（2026-11-11：docs/test2 の古い写し 7 枚と archive/test2 が残っていた）。
        見本ページ・凍結ページは生成物か写し：作り直す／新しい接続先に直す。"""
        files = subprocess.run(["git", "ls-files", "docs", "archive"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
        bad, n = [], 0
        for f in files:
            if not f.endswith((".html", ".js", ".json", ".yaml", ".yml", ".css")):
                continue
            n += 1
            s = (ROOT / f).read_text(encoding="utf-8", errors="ignore")
            if sbconf.OLD_REF in s or OLD_KEY in s:
                bad.append(f)
        self.assertGreater(n, 50, "点検の対象が空")
        self.assertEqual(bad, [], "旧 Supabase の ref／鍵が残る。新しい接続先（sbconf）に直す: " + ", ".join(bad))


if __name__ == "__main__":
    unittest.main()
