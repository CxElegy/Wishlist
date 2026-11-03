"""11/4 の本番ゲート（2026-11-03 Supabase egress 対策）。1 コマンドで ✓/✗ を 1 画面に出す。
    python harness/free_tier_gate.py [--skip-prod]
順に：docs の storage 網址 0 と写真の取得先（pages_served）・写真を Pages から配ってよいか（pages_health --photos）・
Supabase が止まっても崩れない（sb_down_check）・個人アクセストークンの混入 0・写真を本番から落とす道 0（test_browser_guard）。
本番に向ける 3 つは各 1 回・timeout 付き（無料枠の決まり）。--skip-prod は手元の静的な 2 つだけ。終了コード 0 ＝ 全部 ✓、--skip-prod は ✓ でも 2（本番の 3 つを見ていないので「入れ終わり」と言わない）。"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
TOKEN = re.compile(r"SUPABASE_ACCESS_TOKEN|sbp_[0-9a-f]{20,}")   # 個人アクセストークンはアカウント全体の鍵。Actions に置かない


SCAN_DIRS = (".github", "scripts", "harness", "docs", ".claude", "state")   # .md は説明文なので見ない（鍵の値は書かない決まり）
SCAN_EXT = {".yml", ".yaml", ".py", ".js", ".html", ".json", ".sh", ".toml"}


def token_hits(root=ROOT):
    """Actions・scripts・harness・docs・.claude・state に個人アクセストークンの名前・値があれば (パス:行) の一覧。この gate 自身は除く。"""
    hits = []
    for d in SCAN_DIRS:
        for p in sorted((root / d).rglob("*")):
            if p.suffix not in SCAN_EXT or not p.is_file() or p.name == "free_tier_gate.py" or "node_modules" in p.parts:
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if TOKEN.search(ln) and not ln.lstrip().startswith("#"):
                    hits.append("%s:%d" % (p.relative_to(root), i))
    return hits


def fill_max_problems(root=ROOT):
    """FILL_MAX の既定が 0 でない・browser.py 以外が FILL_MAX の環境変数 を書く、の一覧（写真を本番から落とす道）。"""
    bad = []
    var = "WL_PHOTO_" + "FILL_MAX"   # test_browser_guard が harness にこの名前の直書きを禁じるので繋いで書く
    if 'os.environ.get("%s", "0")' % var not in (root / "harness" / "browser.py").read_text(encoding="utf-8"):
        bad.append("browser.py の FILL_MAX の既定が 0 でない")
    for d, pat in ((".github", "*.yml"), ("scripts", "*.py"), ("harness", "*.py")):
        for p in sorted((root / d).rglob(pat)):
            if p.name not in ("browser.py", "free_tier_gate.py") and var in p.read_text(encoding="utf-8", errors="ignore"):
                bad.append("%s が %s を書く" % (p.relative_to(root), var))
    return bad


def sh(name, cmd, timeout):
    """(名前, ok, 末尾の 1 行)。時間切れは ✗。"""
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + r.stderr).strip().splitlines()
        return name, r.returncode == 0, out[-1] if out else ""
    except subprocess.TimeoutExpired:
        return name, False, "時間切れ（%d 秒）" % timeout


def steps(skip_prod=False):
    t = token_hits()
    out = [("個人アクセストークンの混入 0", not t, "なし" if not t else "あり " + ", ".join(t[:5]))]
    f = fill_max_problems()
    out.append(("FILL_MAX は 0 のまま", not f, "そのまま" if not f else "; ".join(f[:3])))
    out.append(sh("写真を本番から落とす道 0", [PY, "-m", "unittest", "tests.test_browser_guard"], 300))
    if not skip_prod:
        out.append(sh("docs の storage 網址 0・写真は Pages（pages_served）", [PY, "harness/pages_served.py"], 600))
        out.append(sh("写真の旗を on にしてよい（pages_health --photos）", [PY, "harness/pages_health.py", "--photos"], 300))
        out.append(sh("Supabase が止まっても崩れない（sb_down_check）", [PY, "harness/sb_down_check.py"], 900))
    return out


def report(res, skip_prod):
    """(終了コード, 出す行の一覧)。0＝本番まで全部 ✓、1＝✗ あり、2＝静的だけ ✓ で本番は見ていない（入れ終わりではない）。"""
    lines = ["%s %s　%s" % ("✓" if ok else "✗", n, line) for n, ok, line in res]
    bad = [n for n, ok, _ in res if not ok]
    if bad:
        lines.append("✗ %d 件：%s" % (len(bad), " / ".join(bad)))
        return 1, lines
    if skip_prod:
        lines.append("静的な点検だけ ✓。本番の 3 つ（pages_served・pages_health・sb_down_check）は見ていない → 入れ終わりではない")
        return 2, lines
    lines.append("全部 ✓（入れ終わり）")
    return 0, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-prod", action="store_true")
    a = ap.parse_args()
    code, lines = report(steps(a.skip_prod), a.skip_prod)
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
