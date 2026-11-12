"""sparse-checkout で一部のフォルダだけ取る workflow が、走らせる .py の import を取り出した木で解けるか数える。

2026-11-05：ask_remind.yml は `sparse-checkout: harness` だけ。#900 で harness/browser.py が scripts/nostorage.py を
import するようになり、ModuleNotFoundError で 4 回赤になった。import の先のフォルダが sparse に入っているかを CI で拦める。

    python -m unittest tests.test_sparse_imports
"""
import ast
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
CODE_DIRS = ("scripts", "harness")


def sparse_dirs(text):
    """`sparse-checkout:` の値（同じ行・または次の行からの字下げ付きの行）のフォルダ名の集まり。無ければ None。"""
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        m = re.match(r"(\s*)sparse-checkout:\s*(.*)$", ln)
        if not m:
            continue
        base, rest = len(m.group(1)), m.group(2).split("#")[0].strip()
        vals = [] if rest in ("", "|", ">") else rest.split()
        for nx in lines[i + 1:]:
            if not nx.strip() or nx.strip().startswith("#"):
                continue
            if len(nx) - len(nx.lstrip()) <= base:
                break
            vals += nx.split("#")[0].split()
        return {v.strip("/") for v in vals}
    return None


def local_imports(path):
    """path の中で、リポジトリの scripts/・harness/ にある .py を指す import の (名前, ファイル)。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            names.add(n.module.split(".")[0])
    out = []
    for nm in sorted(names):
        for d in CODE_DIRS:
            f = ROOT / d / (nm + ".py")
            if f.exists():
                out.append((nm, f))
    return out


class SparseImports(unittest.TestCase):
    def test_imports_resolve_in_sparse_tree(self):
        bad = []
        for wf in sorted(WF.glob("*.yml")):
            text = wf.read_text(encoding="utf-8")
            dirs = sparse_dirs(text)
            if dirs is None:
                continue
            for script in sorted(set(re.findall(r"python3?\s+((?:scripts|harness)/[\w./-]+\.py)", text))):
                seen, todo = set(), [ROOT / script]
                if (ROOT / script).parent.name not in dirs:
                    bad.append(f"{wf.name}: {script} 自体のフォルダが sparse-checkout に無い")
                while todo:
                    p = todo.pop()
                    if p in seen:
                        continue
                    seen.add(p)
                    for nm, f in local_imports(p):
                        if f.parent.name not in dirs:
                            bad.append(f"{wf.name}: {p.relative_to(ROOT).as_posix()} が import する {f.relative_to(ROOT).as_posix()} のフォルダが sparse-checkout {sorted(dirs)} に無い")
                        else:
                            todo.append(f)
        self.assertEqual(bad, [], "\n".join(bad))

    def test_parser_reads_block_and_inline(self):
        blk = "        with:\n          sparse-checkout: |\n            harness\n            scripts\n      - uses: x"
        self.assertEqual(sparse_dirs(blk), {"harness", "scripts"})
        self.assertEqual(sparse_dirs("        with:\n          sparse-checkout: harness\n      - uses: x"), {"harness"})
        self.assertIsNone(sparse_dirs("with:\n  ref: main"))


if __name__ == "__main__":
    unittest.main()
