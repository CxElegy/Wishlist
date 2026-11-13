"""改行の向き（CRLF / LF）が base から反転したファイルを見つけて止める（2026-11-13）。
Linux で CRLF のファイル（scripts/render.py・docs/testground/*.html など）を作り直す・編集すると LF に変わり、
1 万行の差になる（#1032・#1034）。変わった中身ではなく「向きが変わったこと」を拦める。既存ファイルの向きは直さない。

    python harness/eol_check.py [base]      # base 既定 origin/main。base...HEAD で変わったファイル（新しいファイル・消したファイルは対象外）
    python harness/eol_check.py --worktree  # 作業ツリー（まだ commit していない版）も base と比べる

多数派の向きが違えば反転。改行のないファイル・バイナリは見ない。ネットワークは使わない。終了コード 0 緑／1 反転あり。
"""
import subprocess
import sys


def style(data):
    """b'..' → 'CRLF' / 'LF' / None（改行なし・バイナリ）。多数派の向き"""
    if b"\0" in data[:8192]:
        return None
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    if crlf == 0 and lf == 0:
        return None
    return "CRLF" if crlf > lf else "LF"


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True)


def flipped(base="origin/main", worktree=False):
    """[(path, 前の向き, 今の向き)]。base が無い・読めない時は []（呼ぶ側の fetch 失敗で止めない）"""
    mb = _git("merge-base", base, "HEAD")
    if mb.returncode != 0:
        return []
    ref = mb.stdout.decode().strip()
    names = _git("diff", "--name-only", "-z", "--diff-filter=M", ref, "HEAD").stdout.decode("utf-8", "replace").split("\0")
    if worktree:
        names += _git("diff", "--name-only", "-z", "--diff-filter=M", "HEAD").stdout.decode("utf-8", "replace").split("\0")
    out = []
    for p in sorted({n for n in names if n}):
        old = _git("show", f"{ref}:{p}")
        if old.returncode != 0:
            continue
        if worktree:
            try:
                with open(p, "rb") as f:
                    new = f.read()
            except OSError:
                continue
        else:
            r = _git("show", f"HEAD:{p}")
            if r.returncode != 0:
                continue
            new = r.stdout
        a, b = style(old.stdout), style(new)
        if a and b and a != b:
            out.append((p, a, b))
    return out


def main(argv):
    wt = "--worktree" in argv
    args = [a for a in argv if not a.startswith("--")]
    bad = flipped(args[0] if args else "origin/main", wt)
    if not bad:
        print("✓ 改行の向き：反転したファイルなし")
        return 0
    print("✗ 改行の向きが変わったファイル（差が全行になる。元の向きで保存し直す）：")
    for p, a, b in bad:
        print(f"  {p}: {a} → {b}")
    print("直し方：LF に変えた CRLF のファイルは `sed -i 's/$/\\r/' <file>`（全行が LF だけのとき）か、編集を向きを保つ道具でやり直す。")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
