"""点検の道具が本番の Supabase の REST（/rest/v1/ の GET）を読む入口は、ここ 1 つだけ（2026-11-04・egress 19.2/5.5 GB で 11/5 から 402）。
写しは ttl を渡した読みだけ（既定 0＝毎回本番。直した直後の本番を比べる点検は古い写しで偽の緑にしない）。
写し（~/.cache/wl_sb_read）には secret key で読んだ非公開の版面も平文で入る＝手元・Actions の一時領域だけ、リポジトリ・Pages・artifact に出さない（free-tier.md）。
ブラウザからの Supabase 要求（rest・rpc・auth）は browser.py が browser_hit() で数える。本番へ出した回数は stats() で数え、点検の最後に出す。
tests/test_sbread.py が harness/*.py の /rest/v1/ 直書きを数える（名簿＝このファイルだけ）。"""
import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path

import browser  # noqa: F401  urllib の止め（free-tier.md）。browser 側は sbread を使う時に読む（循環しない）

DIR = Path(os.environ.get("WL_SB_CACHE") or Path.home() / ".cache" / "wl_sb_read")
TTL = int(os.environ.get("WL_SB_TTL") or 0)
_n = {"net": 0, "hit": 0, "bytes": 0, "br": 0}
_br = {}


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


def browser_hit(url):
    """ブラウザが本番の Supabase に出した要求（storage は browser.py の写しが受けるので数えない）。"""
    m = re.search(r"\.supabase\.co/(rest/v1/rpc|rest/v1|auth/v1|functions/v1|realtime/v1)", url)
    if m:
        _n["br"] += 1
        _br[m.group(1)] = _br.get(m.group(1), 0) + 1


def stats():
    return dict(_n)


def line():
    return f"本番の /rest/v1/ への要求 {_n['net']} 件（{_n['bytes'] / 1024:.0f} KB）・写しから {_n['hit']} 件／ブラウザから {_n['br']} 件 {_br or ''}"
