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

## 運営者がやること（1 回だけ・約 15 分）

Claude からはできない（あなたの Google アカウント・Supabase の画面の設定）。画面の名前が日本語・中国語で出ても、下のリンクを直接開けば同じ所に行ける。

### A. Google Cloud で「ログインの鍵」（OAuth クライアント）を作る

1. https://console.cloud.google.com/ を開き、`c.elegy@outlook.com` の Google アカウントでログイン（初めてなら利用規約に同意、国を選ぶ。お金はかからない・カード不要）
2. **プロジェクトを作る**：https://console.cloud.google.com/projectcreate → プロジェクト名 `watchlist-login` → 「作成」→ 右上の通知で作成済みになったら、画面上の左のプロジェクト選択がこのプロジェクトになっていることを確認
3. **Google Auth Platform を始める**：https://console.cloud.google.com/auth/overview → 「開始」（Get started）
   - アプリ情報：アプリ名 `ウォッチリスト通信`、ユーザー サポートメール = 自分のメール → 次へ
   - 対象（Audience）：**外部（External）** → 次へ
   - 連絡先：自分のメール → 次へ → ポリシーに同意 → 「作成」
4. **スコープ**：https://console.cloud.google.com/auth/scopes → 「スコープを追加または削除」→ `openid`・`.../auth/userinfo.email`・`.../auth/userinfo.profile` の 3 つにチェック → 更新 → 保存（これ以外は足さない。足すと Google の審査が要る）
5. **公開する**：https://console.cloud.google.com/auth/audience → 公開ステータス「テスト中」の下の「アプリを公開」（Publish app）→ 確認 → 「本番環境」になる
   （テスト中のままだと、テストユーザーに登録した人しかログインできない。メール・名前・アイコンだけなので審査なし）
6. **クライアント（鍵）を作る**：https://console.cloud.google.com/auth/clients/create
   - アプリケーションの種類：**ウェブ アプリケーション**、名前 `watchlist-web`
   - 承認済みの JavaScript 生成元 →「URI を追加」→ `https://cxelegy.github.io`
   - 承認済みのリダイレクト URI →「URI を追加」→ `https://bzokpnbcjscbcehdxtjq.supabase.co/auth/v1/callback`
   - 「作成」→ 出てくる **クライアント ID**（`….apps.googleusercontent.com`）と **クライアント シークレット**（`GOCSPX-…`）をコピーしておく（「JSON をダウンロード」でも可）
   - **シークレットは Claude にもチャットにも送らない**。次の B で Supabase に直接貼る

### B. Supabase に鍵を入れる・招待制をつなぐ

1. **Google を有効に**：https://supabase.com/dashboard/project/bzokpnbcjscbcehdxtjq/auth/providers → 一覧の「Google」→ 「Enable Sign in with Google」をオン →
   Client IDs に A-6 のクライアント ID、Client Secret (for OAuth) にシークレットを貼る → 「Save」
   （下に出る Callback URL が A-6 のリダイレクト URI と同じ `https://bzokpnbcjscbcehdxtjq.supabase.co/auth/v1/callback` であることを確認）
2. **戻り先を許可**：https://supabase.com/dashboard/project/bzokpnbcjscbcehdxtjq/auth/url-configuration →
   Site URL に `https://cxelegy.github.io/Wishlist/test2/` → Save、Redirect URLs の「Add URL」に `https://cxelegy.github.io/Wishlist/**` → Save
3. **招待制をつなぐ**：https://supabase.com/dashboard/project/bzokpnbcjscbcehdxtjq/auth/hooks → 「Add a new hook」→ 「Before User Created」→
   Hook type = **Postgres**、Schema = `public`、Function = `hook_invite_only` → 「Create hook」（オンになっていることを確認）
4. **招待の取り消し・退会の関数**：https://supabase.com/dashboard/project/bzokpnbcjscbcehdxtjq/sql/new → リポジトリの `db/auth_delete.sql` を全部貼る → 「Run」
   （delete を含むので連接器では流していない）

### C. Claude に「設定した」と言う

一緒に試す：右上の「ログイン」→ Google →「管理者」と出るか、招待していないアカウントは「招待制です」で断られるか。よければ合併して `db/auth_enforce.sql`（開關を開く）。

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
