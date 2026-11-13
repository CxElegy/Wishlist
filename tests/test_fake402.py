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

    def _rebase_case(self, script):
        """一時の git に 10 行の docs/x.html を置き、入口 ent.py を「土台 → 402」の順で走らせて shrunk を返す（本物の入口は使わない）。"""
        import http.server
        import subprocess
        import tempfile
        import threading
        d = pathlib.Path(tempfile.mkdtemp(prefix="rebase_"))
        (d / "docs").mkdir()
        (d / "docs" / "x.html").write_text("".join(f"{i}\n" for i in range(10)), encoding="utf-8")
        (d / "ent.py").write_text(script, encoding="utf-8")
        (d / "state").mkdir()
        (d / "state" / "sizes.json").write_text('{"a":"M","b":"S","c":"L","d":"M","e":"S"}', encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        os.environ.pop("GIT_DIR", None)
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("GIT_")}
        try:
            fake402_check._git(d, "init", "-q")
            fake402_check._git(d, "add", "-A")
            fake402_check._git(d, "commit", "-qm", "b")
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), fake402_check._H)
            srv.hits = []
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            env["FAKE_URL"] = f"http://127.0.0.1:{srv.server_address[1]}"
            fake402_check.baseline(d, srv, ["ent.py"], env, 60, "ent")
            subprocess.run([sys.executable, "ent.py"], cwd=d, env=env, check=True, timeout=60)
            srv.shutdown()
            return fake402_check.shrunk(d)
        finally:
            os.environ.update(saved)

    _ENT = ("import os, urllib.request, urllib.error\n"
            "try:\n    urllib.request.urlopen(os.environ['FAKE_URL'] + '/x'); ok = True\n"
            "except urllib.error.HTTPError:\n    ok = False\n")

    def test_code_change_shrink_is_not_flagged(self):
        """コードを変えて出力が 10 行 → 5 行に縮んでも、土台（402 でない回）も 5 行なので縮みに数えない（docs/home をコミットし直さなくてよい）。"""
        out = self._rebase_case(self._ENT + "open('docs/x.html','w').write(''.join(f'{i}\\n' for i in range(5)))\n")
        self.assertEqual(out, {})

    def test_402_emptying_is_still_flagged(self):
        """402 のときだけ出力が空になる入口は、土台（5 行）より縮むので赤。"""
        out = self._rebase_case(self._ENT + "open('docs/x.html','w').write(''.join(f'{i}\\n' for i in range(5 if ok else 0)))\n")
        self.assertIn("docs/x.html", out)

    def test_402_emptying_of_supabase_derived_section_is_flagged(self):
        """docs が Supabase の sizes 表から作る節を持つ入口。402 で state/ の写しに戻れず空になる壊れ方は、土台が空の JSON だと
        土台も空で見えなくなる。土台の偽サーバーは state/ の写しを返すので、土台は 5 行・402 の回は 0 行で赤。"""
        ent = ("import os, json, urllib.request, urllib.error\n"
               "try:\n    rows = json.load(urllib.request.urlopen(os.environ['FAKE_URL'] + '/rest/v1/sizes?select=item,size'))\n"
               "except urllib.error.HTTPError:\n    rows = []   # 壊れ方：402 のとき写し（state/sizes.json）に戻らない\n"
               "open('docs/x.html','w').write(''.join(r['item'] + '\\n' for r in rows))\n")
        self.assertIn("docs/x.html", self._rebase_case(ent))

    def test_rebase_entries_exist(self):
        names = {n for n, _, _ in fake402_check.ENTRIES}
        self.assertEqual(sorted(fake402_check.REBASE - names), [])


if __name__ == "__main__":
    unittest.main()
