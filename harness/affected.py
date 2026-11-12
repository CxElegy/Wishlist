"""変わったファイルから「必ず流す試験の組」を機械で決める（2026-11-13，店長「どこに時間がかかっているのか、縮めて」）。

    python harness/affected.py origin/main..HEAD          # 人が読む形
    python harness/affected.py --base origin/main --json  # {"all": .., "fast": [..], "browser": [..], "why": {..}}
    python harness/affected.py --base origin/main --names # bash 用：ALL か、空白区切りの試験の名前（空なら何も出さない）
    python harness/affected.py --files scripts/render.py --json   # git を使わず、ファイルを名指し

対応の表は手で書かない。毎回ソースから作る：
  ① import の関係（scripts/・harness/・tests/ の .py を ast で読み、間接の import もたどる。"scripts/x.py" を名指しして走らせるのも import と同じ）
  ② 試験（と、それが import する物）が書いているファイルの名前（"items.yaml"・ROOT / ".github" / "workflows" の .glob("*.yml") など）
  ③ scripts/processes.py の files（同じ仕組みの .py に当たる試験を、yml・json・sql の変更にも流す）
  ④ pre-push ② と同じ名前の決まり（scripts/x.py → tests/test_x*.py）
分からない時は全部（安全側）：どの試験にも当たらないファイル（.md と画像を除く）・harness/・.githooks/・requirements・Dockerfile・ci.yml・
読めない .py。全部の試験はどのみち GitHub の CI が PR の合併の前に流す。
browser＝playwright か harness/browser.py を直に import する試験（Playwright の鍵・負荷で落ちやすい）、fast＝それ以外。
標準ライブラリだけ（pre-push の python に yaml・lxml が無くても動く）。
"""
import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
CODE_DIRS = ("scripts", "harness", "tests")
MOD_ROOTS = ("", "scripts", "harness", "tests")
# これが変わったら全部：試験の流し方・入れ物そのもの
ALL_RE = re.compile(r"^(harness/|\.githooks/|requirements[^/]*\.txt$|(.*/)?[^/]*Dockerfile[^/]*$|\.github/workflows/ci\.yml$|tests/__init__\.py$)")
# どの試験にも当たらなくてよい物（文章と絵）。それ以外で当たらない物は「分からない」＝全部
QUIET_RE = re.compile(r"\.(md|png|jpe?g|webp|gif|svg|ico|avif)$", re.I)
SCAN_FUNCS = {"glob", "rglob", "iterdir", "listdir", "walk", "scandir"}
IMPORT_IN_STR = re.compile(r"\b(?:from|import)\s+([A-Za-z_][\w.]*)")


def code_files(root):
    """scripts/・harness/・tests/ の .py（相対の posix パス）。"""
    out = []
    for d in CODE_DIRS:
        for dp, dns, fns in os.walk(root / d):
            dns[:] = [n for n in dns if n not in ("__pycache__", "node_modules", ".venv")]
            out += [PurePosixPath(Path(dp, f).relative_to(root)).as_posix() for f in fns if f.endswith(".py")]
    return sorted(out)


def _chain(node):
    """ROOT / ".github" / "workflows" や Path("docs/home") の文字の部分を "a/b" にする（分からなければ None）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        a, b = _chain(node.left), _chain(node.right)
        if b is None:
            return None
        return b if a is None else f"{a}/{b}"
    if isinstance(node, ast.Call) and node.args and getattr(node.func, "id", getattr(node.func, "attr", "")) in ("Path", "PurePath", "join"):
        parts = [_chain(a) for a in node.args]
        parts = [p for p in parts if p]
        return "/".join(parts) if parts else None
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        return None
    return None


def _norm(s):
    """"./.github//workflows/" → ".github/workflows"。"""
    return "/".join(p for p in s.replace("\\", "/").split("/") if p not in ("", "."))


class Facts:
    """1 つの .py から読み取った事：import する名前・書いてある文字・覗くディレクトリ。"""

    def __init__(self, path, src):
        self.path = path
        self.imports = set()     # "render"・"scripts.render"・"playwright.sync_api" など
        self.strings = set()     # 文字の定数と、/ で繋いだ道
        self.scans = []          # (ディレクトリ, 形, 下まで)
        self.str_imports = set()
        tree = ast.parse(src, filename=path)
        names, calls = {}, []
        for node in ast.walk(tree):   # 1 回だけ歩く（大きい digest.py・render.py で 2 回歩くと倍かかる）
            if isinstance(node, ast.Assign):
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    c = _chain(node.value)
                    if c:
                        names[node.targets[0].id] = c
            elif isinstance(node, ast.Import):
                self.imports |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                self.imports.add(node.module)
                self.imports |= {f"{node.module}.{a.name}" for a in node.names}
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value
                if len(s) < 300:
                    self.strings.add(s)
                if "import " in s:   # python -c "import browser" など（試験の中だけ数える）
                    self.str_imports |= set(IMPORT_IN_STR.findall(s))
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                c = _chain(node)
                if c:
                    self.strings.add(c)
            elif isinstance(node, ast.Call):
                calls.append(node)
        for node in calls:   # 覗くディレクトリは、名前の割り当てを全部見てから解く
            f = node.func
            fname = getattr(f, "attr", getattr(f, "id", ""))
            if fname in ("import_module", "__import__") and node.args and isinstance(node.args[0], ast.Constant):
                self.imports.add(str(node.args[0].value))
            if fname not in SCAN_FUNCS:
                continue
            mod_call = isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in ("os", "glob")
            if isinstance(f, ast.Attribute) and not mod_call and fname not in ("listdir", "walk", "scandir"):
                recv, pat = f.value, (_chain(node.args[0]) if node.args else None) or "*"   # Path(..).glob("*.yml")
            else:
                recv, pat = (node.args[0] if node.args else None), "*"                      # os.listdir(d)・glob.glob("d/*.py")
            d = names.get(recv.id) if isinstance(recv, ast.Name) else _chain(recv) if recv is not None else None
            if d is None:
                continue
            d = _norm(d)
            if fname == "glob" and mod_call:
                d, _, pat = d.rpartition("/")
            self.scans.append((d, pat, fname in ("rglob", "walk") or "**" in pat))


class Graph:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.files = code_files(self.root)
        self.fileset = set(self.files)
        self.facts, self.broken = {}, []
        for f in self.files:
            try:
                self.facts[f] = Facts(f, (self.root / f).read_text(encoding="utf-8", errors="replace"))
            except (SyntaxError, ValueError) as e:
                self.broken.append(f"{f}（{type(e).__name__}）")
        self.tests = sorted(f for f in self.files if re.match(r"^tests/test_[^/]+\.py$", f))
        self.edges = {f: self._edges(x) for f, x in self.facts.items()}
        self.closure = {t: self._close(t) for t in self.tests}
        self.procs = self._processes()

    def _resolve(self, mod):
        parts = mod.split(".")
        for n in range(len(parts), 0, -1):
            rel = "/".join(parts[:n])
            for r in MOD_ROOTS:
                for cand in (f"{r}/{rel}.py".lstrip("/"), f"{r}/{rel}/__init__.py".lstrip("/")):
                    if cand in self.fileset:
                        return cand
        return None

    def _edges(self, facts):
        test = facts.path.startswith("tests/")
        out = {self._resolve(m) for m in facts.imports | (facts.str_imports if test else set())}
        if test:   # 試験が "scripts/digest.py" を名指しで走らせる（processes.py などの名簿の文字は import に数えない）
            out |= {s for s in facts.strings if s in self.fileset}
        out.discard(None)
        out.discard(facts.path)
        return out

    def _close(self, start):
        seen, todo = {start}, [start]
        while todo:
            for n in self.edges.get(todo.pop(), ()):
                if n not in seen:
                    seen.add(n)
                    todo.append(n)
        return seen

    def _processes(self):
        """scripts/processes.py の PROCESSES の files（ast で読むだけ。import しない）。"""
        p = self.root / "scripts" / "processes.py"
        out = []
        try:
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Dict):
                    for k, v in zip(node.keys, node.values):
                        if isinstance(k, ast.Constant) and k.value == "files" and isinstance(v, ast.List):
                            out.append({e.value for e in v.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)})
        except (OSError, SyntaxError):
            pass
        return out

    def is_browser(self, test):
        imps = self.facts[test].imports
        return any(m == "playwright" or m.startswith("playwright.") for m in imps) or any(
            self._resolve(m) == "harness/browser.py" for m in imps)

    def _reads(self, facts, path):
        """facts の .py が path（変わったファイル）を名指しで読むか、覗くディレクトリに入っているか。"""
        base = path.rsplit("/", 1)[-1]
        for s in facts.strings:
            s2 = _norm(s)
            if not s2:
                continue
            if s2 == path or ("/" in s2 and (path.endswith("/" + s2) or path.startswith(s2 + "/"))):
                return True
            if "/" not in s2 and "." in s2 and s2 == base:
                return True
        for d, pat, deep in facts.scans:
            if d and path.startswith(d + "/"):
                rest = path[len(d) + 1:]
                if (deep or "/" not in rest) and fnmatch.fnmatch(rest.rsplit("/", 1)[-1], pat.rsplit("/", 1)[-1]):
                    return True
        return False

    def hits(self, path):
        """path が変わったとき当たる試験と、その理由。"""
        got = {}
        if path in self.fileset:
            for t, cl in self.closure.items():
                if path in cl:
                    got[t] = "自分" if path == t else "import"
        readers = {m for m, x in self.facts.items() if self._reads(x, path)}
        for t, cl in self.closure.items():
            if t not in got and cl & readers:
                got[t] = "読む（" + ", ".join(sorted(cl & readers)[:2]) + "）"
        if path.endswith(".py") and path.startswith(("scripts/", "harness/")):   # pre-push ② と同じ名前の決まり
            stem = path.rsplit("/", 1)[-1][:-3]
            for t in self.tests:
                n = t.rsplit("/", 1)[-1][:-3]
                if t not in got and (n == f"test_{stem}" or n.startswith(f"test_{stem}_")):
                    got[t] = "名前"
        if not path.endswith(".py"):   # processes.py で同じ仕組みの .py に当たる試験
            for files in self.procs:
                if path in files:
                    for py in files:
                        if py.endswith(".py") and py != path:
                            for t, cl in self.closure.items():
                                if t not in got and py in cl:
                                    got[t] = f"仕組み（{py}）"
        return got


def affected(changed, root=ROOT, graph=None):
    """変わったファイル（相対の posix パス）→ {"all", "fast", "browser", "why", "unknown"}。git は使わない。"""
    changed = sorted({c.replace("\\", "/").strip() for c in changed if c.strip()})
    try:
        g = graph or Graph(root)
    except Exception as e:   # 何が起きても全部（安全側）
        return _all([], {"*": f"表を作れない：{type(e).__name__}: {e}"}, [])
    why, unknown, picked = {}, [], {}
    for c in changed:
        if ALL_RE.match(c):
            why[c] = "全部（試験の流し方・入れ物）"
            unknown.append(c)
            continue
        h = g.hits(c)
        if c.endswith(".py") and not any(r in ("自分", "import", "名前") for r in h.values()):
            # どの試験も import しない .py（新しい scripts など）は、名簿を覗く試験に当たっても「分からない」（安全側）
            h = {}
        if not h:
            if QUIET_RE.search(c):
                why[c] = "当たる試験なし（文章・絵）"
                continue
            if not c.startswith("tests/test_") or (Path(g.root) / c).exists():
                why[c] = "分からない：どの試験にも当たらない → 全部"
                unknown.append(c)
            else:
                why[c] = "消えた試験"
            continue
        why[c] = f"{len(h)} 本"
        for t, r in h.items():
            picked.setdefault(t, f"{c}（{r}）")
    if g.broken:
        unknown.append("（読めない .py）")
        why["（読めない .py）"] = "、".join(g.broken)
    if unknown:
        return _all(g.tests, why, unknown, g)
    names = sorted(picked)
    return {"all": False, "fast": [_n(t) for t in names if not g.is_browser(t)],
            "browser": [_n(t) for t in names if g.is_browser(t)], "why": why,
            "tests_why": {_n(t): picked[t] for t in names}, "unknown": []}


def _n(t):
    return t.rsplit("/", 1)[-1][:-3]


def _all(tests, why, unknown, g=None):
    return {"all": True, "fast": [_n(t) for t in tests if g is None or not g.is_browser(t)],
            "browser": [_n(t) for t in tests if g is not None and g.is_browser(t)], "why": why, "unknown": unknown}


def _git(args, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}   # hook から受け継いだ GIT_DIR などで別の repo を見ない
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def changed_files(base, head="HEAD", cwd=ROOT):
    """base...head で変わったファイル（3 点：main の新しい commit は数えない。名前の変更は消えた＋足したの 2 つ）。"""
    return [l for l in _git(["diff", "--no-renames", "--name-only", f"{base}...{head}"], cwd).splitlines() if l.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("range", nargs="?", help="base..head（例 origin/main..HEAD）")
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--files", nargs="*", help="git を使わず、変わったファイルを名指し")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--names", action="store_true", help="ALL か、空白区切りの名前")
    ap.add_argument("--fast", action="store_true", help="--names で fast だけ")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    root = Path(a.root).resolve()
    try:
        if a.files is not None:
            changed = a.files
        else:
            base, head = a.base, a.head
            if a.range:
                base, _, h = a.range.partition("..")
                head = h.lstrip(".") or "HEAD"
            changed = changed_files(base or "origin/main", head, root)
        res = affected(changed, root)
    except Exception as e:   # git が無い・base が無い など：全部
        res = {"all": True, "fast": [], "browser": [], "why": {"*": f"{type(e).__name__}: {e}"}, "unknown": ["*"]}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif a.names:
        print("ALL" if res["all"] else " ".join(res["fast"] + ([] if a.fast else res["browser"])))
    else:
        for c, w in res["why"].items():
            print(f"{c}: {w}")
        if res["all"]:
            print(f"→ 全部（{len(res['fast']) + len(res['browser'])} 本）")
        else:
            print(f"→ fast {len(res['fast'])} 本：{' '.join(res['fast'])}")
            print(f"→ browser {len(res['browser'])} 本：{' '.join(res['browser'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
