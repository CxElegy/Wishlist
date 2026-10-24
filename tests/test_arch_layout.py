"""管理ページ「全体の構成（詳しい図）」の崩れを防ぐ（2026-10-25：「そのほか」の枠 grid-area:etc が
grid-template-areas になく、暗黙の列が幅を全部取って 4 列が 24px に潰れた）。"""
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import processes  # noqa: E402


class ArchLayout(unittest.TestCase):
    def test_every_zone_has_area(self):
        areas = re.findall(r'grid-template-areas:((?:"[^"]*"\s*)+)', processes.CSS)
        self.assertEqual(len(areas), 2)   # PC とスマホ
        for a in areas:
            names = set(" ".join(re.findall(r'"([^"]*)"', a)).split())
            for z in [z["id"] for z in processes.ARCH] + ["etc"]:
                self.assertIn(z, names, f"枠 {z} が grid-template-areas にない")

    def test_all_procs_placed(self):
        placed = {n.get("proc") for z in processes.ARCH for n in z["nodes"]} | {
            x for z in processes.ARCH for n in z["nodes"] for x in n.get("subs", [])}
        self.assertEqual([p["id"] for p in processes.PROCESSES if p["id"] not in placed], [])

    def test_css_no_orphan_declarations(self):
        depth, top = 0, []
        buf = ""
        for ch in processes.CSS:
            if ch == "{":
                if depth == 0:
                    top.append(buf)
                buf = ""
                depth += 1
            elif ch == "}":
                depth -= 1
                self.assertGreaterEqual(depth, 0)
                buf = ""
            elif depth == 0:
                buf += ch
            elif ch in ";":
                buf = ""
            else:
                buf += ch
        self.assertEqual(depth, 0)
        for sel in top:
            self.assertNotIn(";", sel, f"宣言が規則の外にある：{sel.strip()[:80]}")


if __name__ == "__main__":
    unittest.main()
