"""公開ページの置き場所（2026-10-19，用户定的）。

docs/test1/ = 2026-10-19 までの版の凍結した写し（もう作り直さない・後台も回さない）。
docs/test2/ = いま使っている版。網页の生成・小元素・本站保存の写真・愿望清单の写真はみんなここに書く。
docs/index.html = 入口（test1 / test2 の 2 枚のカード、手書き）。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAME = "test2"
SITE_DIR = ROOT / "docs" / NAME
URL = f"https://cxelegy.github.io/Wishlist/{NAME}/"
SINCE = "2026-10-19T12:36:00Z"   # test2 を始めた時刻（UTC）。設定・管理ページの「最近の依頼」はこれより後のものだけ（test1 の依頼を出さない）
