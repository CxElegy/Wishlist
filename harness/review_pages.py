"""審査待ちの見本が「触れる・保存先がある・なぜ／今／変わることが書いてある」を数える（HARNESS「審査の見本は触って決める」）。
tests/test_review_pages.py（文字の点検）と ux_check（本番を 1400／390 で押して保存まで）が同じ関数を使う。"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TG = ROOT / "docs" / "testground"


def pending_pages(index_html):
    """index.html の「審査待ち」の欄に並ぶ見本のファイル名（重複なし）。"""
    m = re.search(r'id="review".*?</section>', index_html, re.S)
    return list(dict.fromkeys(re.findall(r'href="([\w-]+\.html)"', m.group(0)))) if m else []


def static_bad(name, html):
    """1 枚の見本の文字の点検。共通の review.js（data-* の 4 つが全部ある・選択肢 2 つ以上）か、自前の review_save のどちらかが要る。"""
    m = re.search(r'<script src="review\.js"([^>]*)></script>', html)
    if m:
        a = dict(re.findall(r'data-(\w+)="([^"]*)"', m.group(1)))
        miss = [k for k in ("page", "options", "why", "now", "change") if not a.get(k, "").strip()]
        if miss:
            return [f"{name}：review.js の {','.join(miss)} が空"]
        if len(a["options"].split("|")) < 2 or any("=" not in o for o in a["options"].split("|")):
            return [f"{name}：選択肢が 2 つ未満か 記号=説明 の形でない"]
        return []
    if "review_save" in html and "なぜ" in html and "何が変わる" in html:
        return []
    return [f"{name}：触って答えを保存する欄がない（review.js も review_save もない）"]
