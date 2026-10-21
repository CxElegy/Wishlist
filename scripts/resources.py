"""サーバーの残り・容量・トークンの記録（管理ページ「バックグラウンド → リソース」）。

裏で動く仕組みは、終わるときに snapshot() を実行ログ（runlog）に付けて残す：
  CPU の数・負荷・メモリ（全体 / 空き）・ディスク（全体 / 空き）・この処理のピークのメモリ。
ページを作るときは repo_sizes() でリポジトリと公開ページ（docs/）の大きさを量り、上限（LIMITS）と比べる。
トークン：Claude API を使ったときは応答の usage を数える（digest.TOKENS）。Claude の定時タスク（サブスク枠）は
数を読む仕組みがないので、セッションの Claude が自分の使った量を `runlog.py add … --tokens N` で書く（目安）。
"""

import os
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sitedir  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MB = 1024 * 1024
# 上限（GitHub の決まり）：Pages の公開サイトは 1GB まで、リポジトリは 1GB 未満を強く勧められている（5GB で警告）
LIMITS = {"pages": 1024 * MB, "repo": 1024 * MB}


def _meminfo():
    out = {}
    try:
        for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            out[k] = int(v.split()[0]) * 1024
    except (OSError, ValueError):
        pass
    return out


def snapshot(path=None):
    """→ {cpu, load, mem_total, mem_free, disk_total, disk_free, peak}（バイト）。取れないものは入れない。"""
    snap = {"cpu": os.cpu_count() or 0}
    try:
        snap["load"] = round(os.getloadavg()[0], 2)
    except OSError:
        pass
    m = _meminfo()
    if m.get("MemTotal"):
        snap["mem_total"], snap["mem_free"] = m["MemTotal"], m.get("MemAvailable", m.get("MemFree", 0))
    try:
        # total はマシン全体（ほかのセッションと共有）。このセッションで使えるのは「使った量 + 空き」なので、そちらを上限にする
        d = shutil.disk_usage(path or ROOT)
        snap["disk_used"], snap["disk_free"], snap["disk_total"] = d.used, d.free, d.used + d.free
    except OSError:
        pass
    try:
        import resource
        snap["peak"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024   # Linux は KB
    except (ImportError, OSError):
        pass
    return snap


def dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def repo_sizes(root=None):
    """リポジトリ（.git を除く作業ツリー）・公開ページ（docs/）・小元素の画像・集めた記事の大きさ（バイト）。"""
    root = pathlib.Path(root or ROOT)
    return {"repo": dir_size(root), "pages": dir_size(root / "docs"), "emblems": dir_size(root / "docs" / sitedir.SLUG / "emblems"),
            "inbox": dir_size(root / "inbox"), "state": dir_size(root / "state")}
