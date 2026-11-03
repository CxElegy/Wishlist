"""11/4 の本番ゲート（2026-11-03 Supabase egress 対策）。1 コマンドで ✓/✗ を 1 画面に出す。
    python harness/free_tier_gate.py [--skip-prod]
順に：docs の storage 網址 0 と写真の取得先（pages_served）・写真を Pages から配ってよいか（pages_health --photos）・
Supabase が止まっても崩れない（sb_down_check）・個人アクセストークンの混入 0・写真を本番から落とす道 0（test_browser_guard）。
本番に向ける 3 つは各 1 回・timeout 付き（無料枠の決まり）。--skip-prod は手元の静的な 2 つだけ。終了コード 0 ＝ 全部 ✓。"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
TOKEN = re.compile(r"SUPABASE_ACCESS_TOKEN|sbp_[0-9a-f]{20,}")   # 個人アクセストークンはアカウント全体の鍵。Actions に置かない


def token_hits(root=ROOT):
    """Actions と scripts に個人アクセストークンの名前・値があれば (パス, 行) の一覧。"""
    hits = []
    for d, pat in ((".github/workflows", "*.yml"), ("scripts", "*.py")):
        for p in sorted((root / d).glob(pat)):
            for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if TOKEN.search(ln) and not ln.lstrip().startswith("#"):
                    hits.append("%s:%d" % (p.relative_to(root), i))
    return hits


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
    out.append(sh("写真を本番から落とす道 0", [PY, "-m", "unittest", "tests.test_browser_guard"], 300))
    if not skip_prod:
        out.append(sh("docs の storage 網址 0・写真は Pages（pages_served）", [PY, "harness/pages_served.py"], 600))
        out.append(sh("写真の旗を on にしてよい（pages_health --photos）", [PY, "harness/pages_health.py", "--photos"], 300))
        out.append(sh("Supabase が止まっても崩れない（sb_down_check）", [PY, "harness/sb_down_check.py"], 900))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-prod", action="store_true")
    res = steps(ap.parse_args().skip_prod)
    for n, ok, line in res:
        print("%s %s　%s" % ("✓" if ok else "✗", n, line))
    bad = [n for n, ok, _ in res if not ok]
    print("全部 ✓（入れ終わり）" if not bad else "✗ %d 件：%s" % (len(bad), " / ".join(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
