# ログイン（Google・招待制）

2026-10-20 第 1 步。访客 = 見るだけ、招待された人だけ Google でログイン、管理者（5 人まで）だけ管理ページ。

## 身份

| | 访客（ログインなし） | ユーザー（招待） | 管理者（5 人まで） |
|---|---|---|---|
| 簡報・愿望清单・話題度を見る | ✅ | ✅ | ✅ |
| 運営者の 👍👎 が押された状態を見る | ✅ | ✅ | ✅ |
| 👍👎・設定・関注項・写真 | ❌ 見るだけ | ✅ 自分の account だけ | ✅ 全部 |
| 管理ページ | ❌ | ❌ | ✅（＋「ユーザーと招待」） |

- 門番はデータベース：書く関数の 1 行目で `can_edit(p_account)` / `is_admin()`（`db/auth_guard.sql`）。網页は止めて理由を出すだけ（`render.AUTH_JS`）。
- 開關 `private.auth_flags.enforce`：閉じている間は前と同じ（だれでも変えられる・管理ページも見える）。`db/auth_enforce.sql` で開く。戻すときは false に。
- 招待制：`invites` 表にあるメールだけ登録できる（Before User Created Hook = `public.hook_invite_only`）。最初の管理者 `c.elegy@outlook.com`。
- account の持ち主：`accounts` 表（test1・test2 は owner 空 = 運営者 = 管理者のもの）。ユーザー自分の account は第 2 步。
- Google から受け取るのは メール・名前・アイコン だけ。管理ページのユーザー一覧は名前だけ（メールは招待表だけ）。

## 運営者がやること（1 回だけ・約 10 分）

Claude からはできない（あなたの Google アカウント・Supabase の画面の設定）。

1. **Google Cloud**（https://console.cloud.google.com/ ）
   - 新しいプロジェクト → 「Google Auth Platform」（OAuth 同意画面）→ 対象「外部」、アプリ名「ウォッチリスト通信」、サポートメール → 「アプリを公開」（メール・名前だけなので審査なし）
   - 「クライアント」→ 作成 → 種類「ウェブ アプリケーション」
     - 承認済みの JavaScript 生成元：`https://cxelegy.github.io`
     - 承認済みのリダイレクト URI：`https://bzokpnbcjscbcehdxtjq.supabase.co/auth/v1/callback`
   - 出てきた「クライアント ID」「クライアント シークレット」を控える（**シークレットは Claude に送らない**）
2. **Supabase**（https://supabase.com/dashboard/project/bzokpnbcjscbcehdxtjq ）
   - Authentication → Sign In / Providers → Google：有効にして、ID とシークレットを貼る
   - Authentication → URL Configuration：Site URL `https://cxelegy.github.io/Wishlist/test2/`、Redirect URLs に `https://cxelegy.github.io/Wishlist/**`
   - Authentication → Hooks → 「Before User Created」→ Postgres → `public` / `hook_invite_only`
   - SQL Editor で `db/auth_delete.sql` を 1 回実行（招待の取り消し・退会。delete を含むので連接器では流さない）
3. Claude に「設定した」と言う → 一緒にログインを試す → 合併して `db/auth_enforce.sql`（開關を開く）。

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
