"""偽の 402 を相手に Actions の入口を通しで走らせ、docs/・state/ が縮まない・入口が落ちないことを見る（harness/fake402_check.py）。
2026-11-04：11/5 以降は全部の回が 402 に当たる。部品単体ではなく入口ごとに、名簿（ALLOW）に無い縮みが 0。"""
import os
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import fake402_check  # noqa: E402


class Fake402(unittest.TestCase):
    # 重い（全入口を通しで走らせる）。ci.yml の全試験に入れると 25 分を超えたので、.github/workflows/fake402.yml が WL_FAKE402=1 で別に回す
    @unittest.skipUnless(os.environ.get("WL_FAKE402") == "1", "重い通し点検は fake402.yml が回す（手元は WL_FAKE402=1）")
    def test_entries_do_not_shrink_under_402(self):
        bad = fake402_check.run()
        self.assertEqual(bad, [], "\n".join(bad))

    def test_fake_clock_skips_sleep(self):
        """偽の時計：PYTHONPATH に足すと time.sleep が 0.02 秒に縮む（再試行の待ちで入口が長くならない）。"""
        import subprocess
        env = {**os.environ, "PYTHONPATH": str(ROOT / "harness" / "fake_clock")}
        r = subprocess.run([sys.executable, "-c", "import time;t=time.time();time.sleep(30);print(time.time()-t<2)"],
                           env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.strip(), "True", r.stderr)

    def test_allowlist_has_reasons(self):
        for f, why in fake402_check.ALLOW.items():
            self.assertTrue(why.strip(), f)

    def test_every_workflow_entry_is_counted(self):
        """workflow が走らせる scripts/・harness/ の入口を全部数え、ENTRIES か NOT_COVERED に無いものを赤にする（新しい入口の足し忘れ）。"""
        covered = set()
        for _, args, _ in fake402_check.ENTRIES:
            covered.add(" ".join([args[0]] + args[1:2]))
        covered |= set(fake402_check.NOT_COVERED)
        used = {args[0] for _, args, _ in fake402_check.ENTRIES}
        # 引数なしの名簿（scripts/x.py）は、ENTRIES に同じスクリプトが無いときだけ、そのスクリプトの全引数を覆う
        whole = {k for k in fake402_check.NOT_COVERED if " " not in k and k not in used and k != "scripts/digest.py"}
        pat = re.compile(r"python3? +((?:scripts|harness)/\w+\.py)(?: +([^\s\"';|&)<>$]+))?")
        missing = set()
        for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
            for line in wf.read_text(encoding="utf-8").splitlines():
                if line.lstrip().startswith("#"):
                    continue
                for m in pat.finditer(line):
                    s, a = m.group(1), m.group(2)
                    a = a if a and (a.startswith("--") or a[0].isalpha()) and a not in ("then", "fi") else None
                    k = f"{s} {a}" if a else s
                    if k not in covered and s not in whole:
                        missing.add(f"{wf.name}: {k}")
        self.assertEqual(sorted(missing), [], "名簿（ENTRIES / NOT_COVERED）に無い workflow の入口")

    def test_rosters_are_consistent(self):
        names = {n for n, _, _ in fake402_check.ENTRIES}
        self.assertEqual(sorted(set(fake402_check.NO_HITS) - names), [])
        self.assertEqual(sorted(set(fake402_check.RC_OK) - names), [])
        for k, v in {**fake402_check.NO_HITS, **{k: v[1] for k, v in fake402_check.RC_OK.items()}}.items():
            self.assertTrue(v.strip(), k)

    def test_not_covered_has_reasons(self):
        for k, why in fake402_check.NOT_COVERED.items():
            self.assertTrue(why.strip(), k)

    def test_json_one_line_shrink_is_seen(self):
        """1 行 JSON の中身が空になっても行数は 1 消えて 1 足すだけ。バイト・要素の数で拾う。"""
        import subprocess
        import tempfile
        d = pathlib.Path(tempfile.mkdtemp(prefix="shrink_"))
        (d / "state").mkdir()
        f = d / "state" / "x.json"
        f.write_text('{"a":[1,2,3],"b":{"c":1}}\n', encoding="utf-8")
        fake402_check._git(d, "init", "-q")
        fake402_check._git(d, "add", "-A")
        fake402_check._git(d, "commit", "-qm", "b")
        f.write_text('{"a":[],"b":{}}\n', encoding="utf-8")
        self.assertIn("state/x.json", fake402_check.shrunk(d))
        f.write_text('{"a":[1,2,3],"b":{"c":2}}\n', encoding="utf-8")
        self.assertEqual(fake402_check.shrunk(d), {})


if __name__ == "__main__":
    unittest.main()
