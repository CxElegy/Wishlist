"""アカウントと公開ページの置き場所（2026-10-19，用户定的）。

test1・test2 は「2 つのアカウント」（以後の一般ユーザーも同じ形で足す）。アカウントごとに別のもの：
- 関注清单・愿望清单・集めた記事・状態：このリポジトリでは今のアカウント（test1 = 店長のページ、2026-10-21 から）が items.yaml・wishlist.yaml・inbox/・reports/・state/、
  試験の版 test2（2026-10-19〜21）は archive/test2/ に凍結。
- Supabase の自分ごとの表（投票・篇幅・目次の分け方・依頼・写真・AI 編集の開關・更新中の帯・記事の写し）：account 列（db/accounts.sql）。
  網页は p_account つきの関数、Actions は digest.scope_account で自分の行だけ読み書きする。
- 公開ページ：docs/<アカウント>/（test2 は凍結した写し）。docs/index.html は入口（scripts/welcome.py）。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAME = "test1"                       # 今のアカウント（2026-10-21 から test1 = 店長のページにもどした）（Supabase の account・docs/ の下のフォルダ名）
SITE_DIR = ROOT / "docs" / NAME
URL = f"https://cxelegy.github.io/Wishlist/{NAME}/"
