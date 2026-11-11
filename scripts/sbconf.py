"""データベースの接続先を 1 か所から読む（items.yaml の settings.supabase_url / supabase_key）。
2026-11-07 に自前版へ移った。見本ページ・点検が接続先を直書きしない（旧プロジェクトの ref は OLD_REF にだけ残す）。"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
OLD_REF = "bzokpnbcjscbcehdxtjq"   # 旧 Supabase（402 で止まった・読むだけの控え）。コードがこれを指さない点検用（tests/test_sbconf.py）


def _get(k):
    m = re.search(r'^\s*' + k + r':\s*["\']?([^\s"\']+)', (ROOT / "items.yaml").read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit(f"items.yaml に {k} がない")
    return m.group(1)


def url():
    return _get("supabase_url").rstrip("/")


def key():
    return _get("supabase_key")


def pair():
    return url(), key()
