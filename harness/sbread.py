"""点検の道具が本番の Supabase の REST（/rest/v1/ の GET）を読む入口は、ここ 1 つだけ（2026-11-04・egress 19.2/5.5 GB で 11/5 から 402）。
同じ網址・同じ鍵なら ttl 秒（既定 600）は手元の写し（~/.cache/wl_sb_read）から返す。本番へ出した回数は stats() で数え、点検の最後に出す。
tests/test_sbread.py が harness/*.py の /rest/v1/ 直書きを数える（名簿＝このファイルだけ）。"""
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

DIR = Path(os.environ.get("WL_SB_CACHE") or Path.home() / ".cache" / "wl_sb_read")
TTL = int(os.environ.get("WL_SB_TTL") or 600)
_n = {"net": 0, "hit": 0, "bytes": 0}


def get(url, key, tok=None, prefer=None, ttl=None, timeout=30):
    """(本文 bytes, Content-Range) を返す。読めなければ例外（呼び側の except がそのまま効く）。"""
    h = {"apikey": key, "Authorization": "Bearer " + (tok or key)}
    if not tok and key.startswith("sb_secret_"):   # 新しい secret key は JWT でない＝Authorization に入れると拒まれる
        del h["Authorization"]
    if prefer:
        h["Prefer"] = prefer
    f = DIR / (hashlib.sha256(f"{url}\n{h['Authorization']}\n{prefer}".encode()).hexdigest()[:40] + ".json")
    ttl = TTL if ttl is None else ttl
    try:
        if time.time() - f.stat().st_mtime < ttl:
            d = json.loads(f.read_text(encoding="utf-8"))
            _n["hit"] += 1
            return d["body"].encode("utf-8"), d["cr"]
    except (OSError, ValueError, KeyError):
        pass
    r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout)
    body = r.read()
    cr = r.headers.get("Content-Range", "")
    _n["net"] += 1
    _n["bytes"] += len(body)
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"body": body.decode("utf-8"), "cr": cr}), encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        pass
    return body, cr


def stats():
    return dict(_n)


def line():
    return f"本番の /rest/v1/ への要求 {_n['net']} 件（{_n['bytes'] / 1024:.0f} KB）・写しから {_n['hit']} 件"
