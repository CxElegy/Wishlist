# ログイン（メールアドレス・利用規約）

2026-10-21 第 1 步。访客 = 見るだけ、だれでも**メールアドレスだけ**で始められる（2026-10-21 にユーザー名から変えた・パスワードなし・重ならない・はじめに利用規約に同意・ブラウザが覚える）。運営者 = **店長**（店長のページはみんなが見るだけ）。店長の名前（メール）だけ、このブラウザで最初の 1 回メールのリンクで確認、管理者（5 人まで）だけ管理ページ。
Google ログインは保留（Google の「公開」にホームページとプライバシーポリシーのページが要るため。`PENDING.md`）。

## 身份

| | 访客（ログインなし） | ユーザー（招待） | 管理者（5 人まで） |
|---|---|---|---|
| 簡報・愿望清单・話題度を見る | ✅ | ✅ | ✅ |
| 運営者の 👍👎 が押された状態を見る | ✅ | ✅ | ✅ |
| 👍👎・設定・関注項・写真 | ❌ 見るだけ | ✅ 自分の account だけ | ✅ 全部 |
| 管理ページ | ❌ | ❌ | ✅（＋「ユーザーと招待」） |

- 門番はデータベース：書く関数の 1 行目で `can_edit(p_account)` / `is_admin()`（`db/auth_guard.sql`）。網页は止めて理由を出すだけ（`render.AUTH_JS`）。
- 開關 `private.auth_flags.enforce`：**2026-10-21 に開いた**。访客・お客さまは店長のページを見るだけ（👍👎・設定・依頼・写真・今すぐ実行は DB が断る）。ログインしない AI 編集の `edit_control_set` は step→pause とやり直し 1 件外すだけ通す。戻すときは false に。
- 管理者：`invites` 表の role=admin のメール（最初は `c.elegy@outlook.com`、5 人まで）。登録時の trigger が役割を決める。ほかの人はユーザー。
- **だれでもメール＋パスワード**（2026-10-21，用户定的：ログインの形をそろえる。メールは送らない・再発行なし・退会の機能はいらない）。新しく始めるでパスワード（8 文字以上）を決め、そのままログイン。テスト用 `test-a〜e@example.com` はパスワード `0000`。店長は管理ページ「お客さまと店長」でお客さまのパスワードを変えられる。
- **店長**：`c.elegy@outlook.com` ＋ **パスワード**でログイン（2026-10-21，用户定的：毎回のメール確認はやめた・パスワードの再発行は要らない）。はじめの 1 回だけ、ログインの欄で自分でパスワードを決める（`shop_set_password`、`private.auth_flags` の `pw_setup` が開いている間だけ、決めたら閉じる。もう一度開くのは `update private.auth_flags set on_ = true where key = 'pw_setup'`）。変えるのはログイン中のメニュー「パスワードを変える」。ほかの店長を足したときも pw_setup を開けてその人に決めてもらう（同じ日に一度 `CxElegy` という名前にしたが、メールアドレスに戻した）。
- **網址 = /home/**（2026-10-21，用户定的：一般的なサイトと同じく網址に名前を入れない。みんな同じ網址、中身はログインした人で決まる）：前の test1 の中身を店長のものとして戻した（Supabase の account 名は test1 のまま、網址は /home/）。試験の版 test2 は `archive/test2/`・`docs/test2/`（見るだけ）。
- account の持ち主：`accounts` 表（test1・test2 は owner 空 = 運営者 = 管理者のもの）。ユーザー自分の account は第 2 步。
- 保存するのはメール（と名前）だけ。管理ページのユーザー一覧は名前だけ（メールは招待表だけ）。

## 運営者がやること（1 回だけ・約 1 分）

1. **戻り先を許可**：https://supabase.com/dashboard/project/bzokpnbcjscbcehdxtjq/auth/url-configuration
   - Site URL に `https://cxelegy.github.io/Wishlist/home/` → 「Save」
   - Redirect URLs の「Add URL」に `https://cxelegy.github.io/Wishlist/**` → 「Save」
   （これがないとメールのリンクが localhost に飛ぶ）
2. Claude に「設定した」と言う → 右上の「ログイン」に `c.elegy@outlook.com` →「確認待ち」→ 届いたメールのリンク →「管理者」と出れば OK → 合併して `db/auth_enforce.sql`（開關を開く）

- **招待制にしない**（2026-10-21，用户定的）：だれでもメールで登録できる。`invites` 表は「管理者のメール」の表としてだけ使う（`hook_invite_only` は作ってあるが Hooks にはつながない）。
- **ブラウザが覚える**：一般ユーザーは localStorage（`wl-user`）、管理者は Supabase のセッション（`wl-auth`、鍵は自動で更新）。ログアウトするかブラウザのデータを消すまでログインのまま。
- **メールアドレス**（2026-10-21，用户定的）：「新しく始める」= 未登録かを打つたびに確かめる（`name_available`）→ 利用規約・プライバシーポリシーに同意 → `user_register`（`app_users`、大文字小文字を区別せず重ならない、同意した版・日時を記録）。「ログイン」= `user_login`（ある名前だけ）。
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

## 第 2 步（入口だけできた・2026-10-22）

- **アカウントは 1 つずつ独立**（2026-10-22，用户定的）：お客さま（テスト用を含む）がログインすると、/home/ の簡報・欲しい物・話題度・設定は**自分のページ**（最初は空）。店長の中身は出さない。
  中身は `my_page()`（ログインした本人の `app_users` の行だけ、`db/my_page.sql`）。キーワード = `prefs.picks`（入口の「新しく始める」で選んだものと同じ形）、設定で足す・外す（`my_keywords_set`、200 個まで）。
  画面の言葉は skill（impeccable の clarify・distill、onboarding、web-design-guidelines）に合わせる：仕組みの説明・準備中・店長のページへの切り替えは出さない、空の状態は「何のための場所か＋最初の 1 つを足す」、外したら「元に戻す」。ニュース集め・版面・欲しい物リストはまだ（下）。

- **お客さまの版面の記事集め**（2026-10-22）：選んだもののうち店長の関注項にないものは `scripts/userfeed.py`（AI なし・店長と同じ絞り込み）が集めて Supabase の `user_boards` に本人の account（`u_` + md5(メール) 16 字）で書く。網页は `my_boards()`（`db/user_boards.sql`，ログインした本人の行だけ）を読み、`{"boards": [{name, sec, stories: [{title, url, source, date, image, summary}], found, checked, updated}]}` を版面の形で描く（`checked` が null = まだ探していない「集めています」、`stories` が空で `checked` あり = まだ見つかっていない）。店長の関注項にあるものは店長の版面をそのまま見せる（行を作らない）。
- ユーザーが登録したら自分の account（`accounts.owner` = 本人）を作り、自分の関注清单・愿望清单・ページを持つ。
- ユーザーのページも同じ /home/（網址に名前を出さない）。本人だけが見られる：GitHub Pages は公開なので、ページは Supabase の非公開の場所に置き、ログイン後に読む。リポジトリにも入れない（リポジトリは公開）。
- ユーザーの関注項の AI 編集は Haiku（安いモデル）・1 日の上限つき。Discord はユーザーとは関係なし（運営者だけ、保留中）。
