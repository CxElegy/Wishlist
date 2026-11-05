"""生成した網页の埋め込み JS（<script> の中身）を node --check で 1 本ずつ確かめる。

2026-11-05：#919 で render.py の JS に文法の誤りが入り、本番の全ページの JS が約 15 分止まった（#929 で直した）。
CI と .githooks/pre-push がこれを回す。src のある script・JSON（application/json・ld+json）・テンプレートは見ない。

    python harness/js_check.py [docs/home] [docs/index.html ...]
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)
SKIP_TYPE = re.compile(r"""type\s*=\s*["']?(application/(ld\+)?json|text/template|text/x-template|importmap)""", re.I)


def blocks(html):
    """(何番目, JS の中身, module か) を返す。src のあるもの・JSON は除く。"""
    out = []
    for i, m in enumerate(SCRIPT.finditer(html)):
        attrs, body = m.group(1), m.group(2)
        if re.search(r"\bsrc\s*=", attrs, re.I) or SKIP_TYPE.search(attrs) or not body.strip():
            continue
        out.append((i, body, bool(re.search(r"""type\s*=\s*["']?module""", attrs, re.I))))
    return out


def check_file(path, node="node"):
    """壊れた script の (ファイル, 何番目, node の最初の誤り行) の一覧。"""
    bad = []
    html = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    with tempfile.TemporaryDirectory() as d:
        for i, body, mod in blocks(html):
            f = pathlib.Path(d) / (f"s{i}.mjs" if mod else f"s{i}.js")
            f.write_text(body, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                msg = next((ln for ln in r.stderr.splitlines() if "Error" in ln), r.stderr.strip()[:200])
                bad.append((str(path), i, msg))
    return bad


def check_render(node="node"):
    """網页を作り直さずに、scripts/render.py の *_JS の文字列を 1 本ずつ node --check（作業ツリーを汚さない・pre-push 用）。
    関数の中の断片（return を含む）も通るよう (function(){…}) で包む。% で埋める型（SNAP_JS）は %s を null に。"""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
    import render  # noqa: E402
    bad = []
    with tempfile.TemporaryDirectory() as d:
        for k in sorted(dir(render)):
            v = getattr(render, k)
            if not (k.endswith("_JS") and isinstance(v, str)) or v.startswith("http"):
                continue
            if "%s" in v:
                v = v.replace("%%", "\0").replace("%s", "null").replace("\0", "%")
            f = pathlib.Path(d) / f"{k}.js"
            f.write_text("(function(){\n" + v + "\n});", encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                bad.append(("scripts/render.py", k, next((ln for ln in r.stderr.splitlines() if "Error" in ln), r.stderr.strip()[:200])))
    return bad


def targets(args):
    for a in args or ["docs/home"]:
        p = pathlib.Path(a)
        if p.is_dir():
            yield from sorted(p.glob("*.html"))
        elif p.exists():
            yield p


def main(argv):
    node = shutil.which("node")
    if not node:
        print("::warning::node が無いので JS の文法は確かめない")
        return 0
    if argv[:1] == ["--render"]:
        bad = check_render(node)
        for f, k, msg in bad:
            print(f"::error file={f}::render.{k} の JS が文法の誤り：{msg}")
        print(f"render の JS の文法：壊れた {len(bad)}")
        return 1 if bad else 0
    files = list(targets(argv))
    bad = [b for f in files for b in check_file(f, node)]
    for f, i, msg in bad:
        print(f"::error file={f}::{f} の {i} 番目の <script> が文法の誤り：{msg}")
    print(f"JS の文法：{len(files)} ページ・壊れた script {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
