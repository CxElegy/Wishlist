"""render.py の *_JS（網页に入れる JS の部品）が node で読めるか。Python の普通の文字列に '\\n' を書くと JS の文字列の中が本当の改行になり、
ページの JS が全部止まる（2026-11-05 EMB_JS の split('\\n')：全員の全ページで「Invalid or unexpected token」）。"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import render  # noqa: E402


@unittest.skipUnless(shutil.which("node"), "node がない")
class JsSyntax(unittest.TestCase):
    def test_render_js_parts_parse(self):
        bad = []
        for n in sorted(dir(render)):
            v = getattr(render, n)
            if not (n.endswith("_JS") and isinstance(v, str)) or "%s" in v or v.lstrip().startswith("http"):
                continue   # 差し込みの型（%s）・網址は JS そのものではない
            s = re.sub(r"^\s*<script[^>]*>|</script>\s*$", "", v.strip())
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
                f.write(s)
            r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
            if r.returncode:
                bad.append(f"{n}: {r.stderr.splitlines()[1:2]}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
