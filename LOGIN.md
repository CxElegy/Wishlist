# ログイン（ユーザー名・利用規約）

2026-10-21 第 1 步。访客 = 見るだけ、だれでも**ユーザー名（メールでも可）だけ**で始められる（パスワードなし・名前は重ならない・はじめに利用規約に同意・ブラウザが覚える）。運営者 = **店長**（店長のページはみんなが見るだけ）。店長の名前（メール）だけ、このブラウザで最初の 1 回メールのリンクで確認、管理者（5 人まで）だけ管理ページ。
Google ログインは保留（Google の「公開」にホームページとプライバシーポリシーのページが要るため。`PENDING.md`）。

## 身份

| | 访客（ログインなし） | ユーザー（招待） | 管理者（5 人まで） |
|---|---|---|---|
| 簡報・愿望清单・話題度を見る | ✅ | ✅ | ✅ |
| 運営者の 👍👎 が押された状態を見る | ✅ | ✅ | ✅ |
| 👍👎・設定・関注項・写真 | ❌ 見るだけ | ✅ 自分の account だけ | ✅ 全部 |
| 管理ページ | ❌ | ❌ | ✅（＋「ユーザーと招待」） |

- 門番はデータベース：書く関数の 1 行目で `can_edit(p_account)` / `is_admin()`（`db/auth_guard.sql`）。網页は止めて理由を出すだけ（`render.AUTH_JS`）。
- 開關 `private.auth_flags.enforce`：閉じている間は前と同じ（だれでも変えられる・管理ページも見える）。`db/auth_enforce.sql` で開く。戻すときは false に。
- 管理者：`invites` 表の role=admin のメール（最初は `c.elegy@outlook.com`、5 人まで）。登録時の trigger が役割を決める。ほかの人はユーザー。
- account の持ち主：`accounts` 表（test1・test2 は owner 空 = 運営者 = 管理者のもの）。ユーザー自分の account は第 2 步。
- 保存するのはメール（と名前）だけ。管理ページのユーザー一覧は名前だけ（メールは招待表だけ）。

## 運営者がやること（1 回だけ・約 1 分）

1. **戻り先を許可**：https://supabase.com/dashboard/project/bzokpnbcjscbcehdxtjq/auth/url-configuration
   - Site URL に `https://cxelegy.github.io/Wishlist/test2/` → 「Save」
   - Redirect URLs の「Add URL」に `https://cxelegy.github.io/Wishlist/**` → 「Save」
   （これがないとメールのリンクが localhost に飛ぶ）
2. Claude に「設定した」と言う → 右上の「ログイン」に `c.elegy@outlook.com` →「確認待ち」→ 届いたメールのリンク →「管理者」と出れば OK → 合併して `db/auth_enforce.sql`（開關を開く）

- **招待制にしない**（2026-10-21，用户定的）：だれでもメールで登録できる。`invites` 表は「管理者のメール」の表としてだけ使う（`hook_invite_only` は作ってあるが Hooks にはつながない）。
- **ブラウザが覚える**：一般ユーザーは localStorage（`wl-user`）、管理者は Supabase のセッション（`wl-auth`、鍵は自動で更新）。ログアウトするかブラウザのデータを消すまでログインのまま。
- **ユーザー名**（2026-10-21，用户定的）：「新しく始める」= 名前が空いているかを打つたびに確かめる（`name_available`）→ 利用規約・プライバシーポリシーに同意 → `user_register`（`app_users`、大文字小文字を区別せず重ならない、同意した版・日時を記録）。「ログイン」= `user_login`（ある名前だけ）。
- **利用規約**：`render.render_terms` → `docs/<account>/terms.html`。中身を変えたら `render.TERMS_VERSION` を上げる → 開いたときに同意の画面（`askAgree`、同意しないならログアウトして見るだけ）。連絡先は `render.TERMS_CONTACT`（未設定）。
- **退会**：メニューの「退会する」= `user_leave`（名前を空けて同意の記録を消す。delete は使わない）。
- 店長（管理ページ「お客さまと店長」）：ユーザーの一覧（名前・規約に同意した版）と店長のメールの追加。
- **メール**：送るのは管理者の確認だけ。Supabase 標準のメール送信は Supabase のチームのメール宛てだけ・1 時間に数通なので、運営者のメールなら設定なしで届く。ほかの人を管理者にするときは「カスタム SMTP」（Authentication → Emails → SMTP Settings。ドメインなしなら Gmail のアプリ パスワード・Brevo）。

## ファイル

- `db/auth.sql`：invites・user_roles・profiles・accounts・is_admin / my_role / can_edit / auth_enforced・招待の hook・登録時の trigger・管理者用の関数・feedback.user_id
- `db/auth_guard.sql`：書く関数に can_edit を足した版・feedback / wish_requests のポリシー
- `db/auth_enforce.sql`：開關を開く（＋旧 test1 の書く関数を閉じる）
- `db/auth_delete.sql`：admin_uninvite・delete_my_account（SQL Editor で手で）
- `scripts/render.py`：`AUTH_JS` / `AUTH_CSS` / `_auth_tag` / `AUTH_LOCK`（ページごとに止める操作）
- `tests/test_auth.py`

## 第 2 步（まだ）

- ユーザーが登録したら自分の account（`accounts.owner` = 本人）を作り、自分の関注清单・愿望清单・ページを持つ。
- ユーザーのページは本人だけが見られる：GitHub Pages は公開なので、ページは Supabase の非公開の場所に置き、ログイン後に読む。リポジトリにも入れない（リポジトリは公開）。
- ユーザーの関注項の AI 編集は Haiku（安いモデル）・1 日の上限つき。Discord はユーザーとは関係なし（運営者だけ、保留中）。
