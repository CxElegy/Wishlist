"""git pull --rebase -X theirs（収集の提交）。「違う」で消えた画像を後台作業が書き直した衝突（modify/delete）も解く。

-X theirs は中身の衝突しか解けない。店長の「違う」が画像を消した直後に後台作業が同じ画像を書くと
modify/delete で rebase が止まり、その回の提交が捨てられた（2026-10-25 run 40151397207）。
消した側を勝たせる：消えた画像は git rm、items.yaml のその画像の行も外して続ける。
終わらなければ rebase --abort して 1 を返す（呼び出し側が再試行）。
"""
import re
import subprocess
import sys


def git(*a, check=False):
    return subprocess.run(["git", *a], capture_output=True, text=True, check=check)


def deleted_conflicts():
    """modify/delete で止まっているファイルと、ほかの衝突があるか。"""
    gone, other = [], False
    for ln in git("status", "--porcelain").stdout.splitlines():
        xy, path = ln[:2], ln[3:]
        if xy in ("DU", "UD", "DD"):
            gone.append(path)
        elif "U" in xy or xy in ("AA",):
            other = True
    return gone, other


def drop_lines(path, gone):
    """items.yaml から、消えた画像を指す行を外す。"""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    keep = [ln for ln in lines if not any(re.search(r'image:\s*"%s"' % re.escape(g), ln) for g in gone)]
    if len(keep) != len(lines):
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(keep)
    return len(lines) - len(keep)


def main():
    r = git("pull", "--rebase", "-X", "theirs", "-q")
    for _ in range(50):
        if r.returncode == 0:
            return 0
        gone, other = deleted_conflicts()
        if not gone or other:
            break
        for g in gone:
            git("rm", "-q", "-f", "--", g)
        n = drop_lines("items.yaml", ["emblems/" + g.split("/emblems/")[-1] for g in gone if "/emblems/" in g])
        git("add", "-A", "items.yaml")
        print(f"modify/delete を解いた：{len(gone)} 件・items.yaml の行 {n}", file=sys.stderr)
        r = subprocess.run(["git", "-c", "core.editor=true", "rebase", "--continue"], capture_output=True, text=True)
    git("rebase", "--abort")
    print(r.stderr, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
