# 無料の枠で回し続ける（2026-11-02，用户定的：「Supabase の利用量が上がっているメールが来たので、持続的に無料アカウントで運用できるようにアーキテクチャを再設計して」）

## 測った事実（2026-11-02 08:00 JST、Supabase のログ 24 時間）

| 何 | 量 | 無料の枠（月） |
|---|---|---|
| データベース | 48 MB | 500 MB |
| ファイル置き場（photos 116 MB・emblems 89 MB・pages 4 MB） | 208 MB | 1 GB |
| **写真の配信（egress）** | **1 日 11.06 GB・34.4 万回**（CDN の HIT 99%。HIT でも枠に数える） | 5 GB（＋キャッシュ分 5 GB） |
| API（rest/rpc） | 1 日 3.9 万回（大きさは小さい） | 回数の上限なし |

- 写真の 34.4 万回のうち **33.5 万回（97%）は、参照元なし・Linux の画面なし Chrome**＝自分たちの点検（ux_check・layout_v2_check・inspect・係の Playwright）。本物の閲覧（参照元 cxelegy.github.io）は 1 日 2 千回ほど。
- 時間ごとの量は係が点検を回す時間と重なる（07 時・12〜14 時 UTC に 3 万回／時）。
- つまり **枠を食っているのは読者ではなく点検**。読者が 100 倍に増えても、点検を外せば枠に収まる計算。

## 決まり

1. **点検は本番の写真を落とさない**：Playwright・requests で本番や見本を開く点検は、`*.supabase.co/storage/` への読み込みを止める（`page.route` で abort、または同じ大きさの灰色の画像を返す）。写真の中身を測る点検（同じ写真・主役の切れ）は、手元の写し（1 回だけ落として `state/photo_cache/` に置き、内容の指紋で使い回す）を使う。点検の 1 回で同じ写真を 2 回落とさない。
2. **配信の見張り**（2026-11-02 改め）：Actions では見張らない。`sbp_` の個人アクセストークンはアカウント全体（全プロジェクトの削除まで）を触れる鍵なので、公開リポジトリの Actions に置かない＝`SUPABASE_ACCESS_TOKEN` は作らない・頼まない。毎日 1 回、ハーネスの見回り（入口の会話／harness の係）が Supabase の `query_logs`（MCP）で写真の配信（GB・回数・参照元なしの割合・発信元別）を数え、BACKLOG／PROGRESS に 1 行書く。1 日 150 MB（月 4.5 GB のペース）を超えたら入口の会話に知らせ、どの発信元かを書く。管理ページへの表示は、写真を Pages に移したあとに要るか見直す（BACKLOG に 1 行）。
3. **写真の置き場の役割**：Supabase は「データベース・ログイン・本人だけのページ」を主に。公開の写真は、配信の量に上限のない／広い所へ移す案を、見本のページで選んでもらう（下の案）。決まるまでは 1 と 2 だけで枠に収める。
4. 新しく何かを足すときは、「1 日に何回・何 MB を Supabase から配るか」を PR に 1 行書く。

## 写真の置き場の案（ユーザーが見本のページで選ぶ）

- 案A（おすすめ）：**GitHub Pages の別の置き場**（写真だけの別リポジトリ、または同じリポジトリの写真だけの枝を毎日まるごと置き換えて歴史を増やさない）。月 100 GB の目安・費用なし・今の網址の作りに近い。作るのはユーザー（リポジトリ・Pages の設定）。
- 案B：Cloudflare R2（10 GB まで無料・配信の費用なし）。アカウントと鍵が要る。
- 案C：Supabase のまま、点検を外すだけ（今の読者の数なら月 2 GB 弱で収まる見込み。読者が増えたら A/B）。

## 決定（2026-11-02，用户定的：「案Aで」）＝写真は GitHub Pages から配る

調べたこと：今の Pages は「ブランチから公開」（`pages build and deployment`）。写真をブランチ（main）に入れると git の歴史が毎日ふくらむので、そのまま入れない。
やり方（おすすめ・A-1）：**Pages の公開元を「GitHub Actions」に切り替え**（ユーザーが設定 https://github.com/CxElegy/Wishlist/settings/pages の Source → GitHub Actions。これで前からの失敗メールも止まる）→ `pages.yml` が docs/ に写真を足して 1 つの公開物にする。写真は git に入れず、Actions のキャッシュ（`actions/cache`、写真の一時保管と同じ 14 日・300 MB の上限、内容の指紋の名前）に置き、新しい写真だけ元のサイトから取る。網址は `https://cxelegy.github.io/Wishlist/p/<指紋>-800.webp`（400 も）。Supabase の photos は、移し終えて 7 日たったら公開の配信をやめる（消すのはユーザーの確認後）。
- 本人だけのページ（pages の箱）・データベース・ログインは Supabase のまま（公開できないので）。
- 小元素（emblems 89 MB）も同じ公開物に入れる（配信は小さいが、同じ考え）。
- Pages の目安：公開物 1 GB まで・月 100 GB・1 時間 10 回の公開まで。公開の回数は今も多い（打ち消し多数）ので、写真の取り込みは公開 1 回にまとめる。
- 公開物の大きさの見張り（2026-11-03）：`pages.yml` の stage が manifest に bytes（docs 全部＋manifest 自身）を書く。`photo_cache.yml` が公開のあと・毎日 `pages_health.py --size --set` で測り、1 GB の 70% 超で赤（測れず＝bytes がまだ無いのは失敗にしない）。記録 `state/pages_size.json` は 1 日 1 回（前の日との増え方）。管理ページ「リソース」の先頭に 1 行。70% を超えたら古い写真を外す規則は消すことなので [?] で聞く。
- 切り替えまでは今の Supabase のまま（点検を止めたので 1 日 0.1〜0.2 GB）。
- 案A-2（切り替えができないとき）：写真だけの別のリポジトリ＋Pages、毎日まるごと 1 コミットに置き換え（歴史を増やさない）。リポジトリと書き込みの鍵はユーザーが作る。

## 実装（2026-11-02）

- 点検のブラウザは `harness/browser.py` の `launch(pw)` だけで開く。開いたページは `*.supabase.co/storage/` を取りに行かず、`state/photo_cache/<ファイル名>` の写しがあればそれ、なければ灰色の画像を返す。直接の `chromium.launch` は `tests/test_browser_guard.py` が CI で拦める。
- 配信の時間そのものを測る `photo_time.py`・`lcp.py`・`ahead_time.py` は `launch(pw, photos=True)`＝環境変数 `WL_ALLOW_PHOTOS=1` を付けたときだけ（付けない限り走らない）。
- 設計の道具（`.claude/skills/design-taste-frontend` の inspect）は CDP の `Network.setBlockedURLs` で同じ止め。
- **Python の読み込みも止める**（2026-11-02 追記：ブラウザだけ止めて、urllib の点検が残っていた）：`browser.py` が import 時に `urllib.request.urlopen` を包み、`*.supabase.co/storage/` は `storage_bytes`（`state/photo_cache/` の写しがあればそれ、なければ 1 回だけ落として写しを作る）か `storage_head`（Range で 1 バイト・同じ網址は 1 回）だけで読める。直接 urlopen すると RuntimeError。**写しが無ければ `storage_bytes`・`storage_head` は None を返し、本番から落とさない**（2026-11-02 追記：Python 側にも「写しに無ければ落とす」が残っていた。落とすのは `fill=True` で呼ぶ `photo_cache_fill.py` だけ。`storage_head` は本番へ出るので `photo_cache_bad` が `WL_ALLOW_PHOTOS=1` のときだけ fill する）。使う点検：`ux_check.photo_cache_bad`（16→6 枚・1 バイト）・`emb_check._get`・`emblem_pick_rules.audit_library`。harness の py が urllib を使うなら browser を import すること、requests・httpx は使わないことを `tests/test_browser_guard.py` が数える。写しの名前は指紋入りのファイル名（同じ名前の中身は変わらない前提。差し替えたら `state/photo_cache/` の該当を消す）。
- **係の Playwright MCP**：`.mcp.json` の `--init-page harness/mcp_init_page.js` が、開いたタブごとに `*.supabase.co/storage/` を灰色の画像に差し替える（`--blocked-origins` は rest/auth も止めるので使わない）。.mjs・`.claude/skills` の道具も `test_no_direct_launch_js` が数える（`shot.mjs` は file:// だけなので許可リスト）。
- 配る量の見込み：点検由来は **最初の 1 回だけ**（ブラウザの点検は写しが無い写真・小元素を 1 回だけ落として `state/photo_cache/` に写し、以後は網に出ない。1 プロセス 300 枚まで＝`WL_PHOTO_FILL_MAX`、超えたら灰色。全部で最大 205 MB を 1 度きり）。cache-control の確認は 1 日 6 枚×1 バイト。残りは読者の 1 日 2 千回ほど＝0.1〜0.2 GB。**実測は ④（入れた次の 24 時間のログ）で確かめるまで「見込み」**。灰色になるのは上限を超えたときだけ（8x8 の灰色は naturalWidth・縦横比を測る点検を狂わせるので、写しを作ってから返す）。
- **写しの空を本番で埋め直す漏れ**（2026-11-02）：以前は 1 プロセス 300 枚まで本番から落として写しを作り、写しは作業ツリー内（`state/photo_cache/`）だったので、毎回まっさらな係の ux_check が起動のたびに最大 300 件を落とした（3 分で 1,151 件）。直し：写しは `~/.cache/wl_photo_cache`（`WL_PHOTO_CACHE`）、`FILL_MAX` 既定 0（灰色）、埋めるのは毎日 1 回の `.github/workflows/photo_cache.yml`（actions/cache・1 回 100 MB まで・html にある網址だけ・html に無くなった写しは消す）。CI の点検（progress.yml の before_after）は cache を読むだけ。`tests/test_browser_guard.py` の NoFillByDefault が数える。発信元ごとの 1 時間の見込み：係・会話（Anthropic／Google）0 回、Actions の点検（Microsoft）0 回、photo_cache.yml 1 日 1 回だけ（初回は数日で全部、以後は新しい写真の分だけ）。

## 決定（2026-11-03，用户定的：「制限を受ける方向で作ってくれないかな」）＝Pro に上げず、制限の間も公開のサイトを動かす

Supabase のメール（2026-11-03）：cached egress 19.2 GB / 5.5 GB、11/5 以降は Fair Use Policy で全 API が 402。使った量は請求の期間がリセットされるまで消えない。制限はリセットで外れる。猶予の後にもう一度超えると猶予なしで即時に制限（ダッシュボードの印は何期か枠内に収まると消える）。

制限の間の形（「休止モード」）：
- **公開のページ（入口・店長のページ・テストグラウンド・話題度・欲しい物の一覧）は GitHub Pages だけで見える**。写真・小元素は Pages から（上の「決定」A-1）。Supabase の網址の写真は 1 枚も残さない。
- **Supabase を使う機能は止めて、そう書く**：ログイン・👍👎・本人のページ・設定の保存・管理ページの DB の表示・審査の保存。画面には 1 行「いまログインと保存を休止しています（再開予定：請求の期間の切り替え後）」。エラーの箱・空の枠・何度も呼び直す動きは出さない。休止中かどうかは、ページを開いたとき 1 回だけ軽い呼び出しで確かめ（402 か通信失敗）、その結果を 10 分覚える。
- **自動の仕組み（Actions）は止めない**：記事集め・AI 編集・出刊・Pages の公開は、Supabase への読み書きが 402 でも飛ばして続ける。Supabase にしかない入力（設定の篇幅・お客さまの版面など）は、最後に読めた写しをリポジトリの state/ に持っていて、それで回す。書けなかったもの（ライブログ・ニュースの表など）は捨てるか、state/ に溜めて再開後に 1 回で書き戻す（溜めるのは公開してよいものだけ。お客さまのデータは溜めない）。
- **再開**：リセットの後、休止の確かめが 200 に戻ったら自動で普通に戻る。戻った後は、写真を Supabase から配らないまま（egress の主な原因を戻さない）。毎日の見張りで egress を数え、月 5.5 GB の 1/3（1.8 GB）を超えるペースなら知らせる。
- データは消えない（制限は読み書きを止めるだけ）。データベースの形も変えない。

## 制限を受けたあと、どこまで抑えられるか（2026-11-03 測定・見積もり。ユーザー「制限を取る方向でどのくらい抑えられるか」「別のデータベースもあり、手段は問わない」）

直近 24 時間の Supabase の配信（ログ）：写真 332 MB（修正前の分）・**本人のページ（pages の箱）75 MB**・API 6,078 回（多くは Actions：live_status 1,112・live_log 542・nav_schemes 507・boards 459・live_report 338・edit_control_get 308・follows 286・user_boards 269・feedback 250）・小元素 2 MB・ログイン 38 回。
- 本人のページ 75 MB/日は、**Actions（Python-urllib）が 6 人分の HTML を 1 日 66〜78 回ずつ落とし直している**もの（比べるためと見られる）。読者ではない。→ 指紋（sha）を state/ に持って比べ、落とさない＝0 に。
- API は 1 回の返事が小さい（数 KB）。1 日 6 千回 × 2 KB ≒ 12 MB/日 ≒ 0.4 GB/月。ほとんどが Actions の見回り（live_status など）。→ 同じジョブの中で 1 回読んで使い回す・変わったときだけ書く、で半分以下に。

| 何 | 今（月の見込み） | 直したあと |
|---|---|---|
| 写真・小元素 | 〜330 GB（点検込み）→ 止めた後 0.5 GB | **0**（Pages から） |
| 本人のページ | 2.3 GB | 読者が開いた分だけ（1 回 0.3〜1 MB、月 0.05 GB 程度） |
| API | 0.4 GB | 0.2 GB 以下 |
| 合計 | — | **月 0.3 GB 前後＝枠（5 GB＋キャッシュ 5.5 GB）の 3〜6%** |

結論：**Supabase は「データベース＋ログイン」だけにすれば、無料の枠に大きく余る**。読者が 10〜20 倍に増えても収まる計算。

別のデータベースの案（比べた結果、今は移らない）：
- Cloudflare（D1＋R2＋Workers）：配信の費用・上限がほぼない・D1 5 GB 無料。ただしログイン（Auth）・行の守り（RLS）・pg の関数を全部作り直し（数日〜）。今の請求の期間に使った分は移っても消えない。
- Firebase（Firestore）：読み取り 1 日 5 万回の上限・SQL なし。作り直しが大きい。
- Neon／Turso：Postgres／SQLite の置き場だけで、配信の枠は Supabase と同じ程度。ログインは別に要る。
→ 今の問題は「データベース」ではなく「ファイルの配信」だったので、移る利点が小さい。ファイルを Pages に出した後でも足りなくなったら（読者が数百人規模）、Cloudflare R2 に本人のページを移すのが次の一手。

## 落ち先の決まり（2026-11-03，写真を Pages から配ったあと）

- 公開の docs/ に Supabase storage の網址を書くのは `data-fb`（開けないときの落ち先）だけ。今ある 1 件は ig-articles（media 箱。インスタの網址は切れるので自前で持つ記事の写真）の落ち先。photos 箱の網址は落ち先にも書かない。見本ページ（testground）も Pages の `/p/` を直書きする。`tests/test_pages_served.py` が docs/ を数えて 0 を保つ。
- 新しい写真が `/p/` で 404 になる穴：photo_store が置いた写真は、render が html に載せてから写しに入る。以前は毎日 1 回の取り込みだけで最大 1 日 404（本番で 10 枚。見た目は原寸の外部画像へ落ちる）。直し：photo_cache.yml が render（网页立即更新）のあとにも走り、写しが変わったら pages.yml を起こす。
- 本番の確かめは `python harness/pages_served.py`（1 回・共通の launch）：画像の取得先を数え、Pages 99% 以上・storage 0・/p/ の 200・304 以外 0 を見る。小元素は `home/emblems/`（docs 内、Pages）で、もともと storage を通らない。

## 11/4 の本番ゲート（2026-11-03）

`python harness/free_tier_gate.py` が全部 ✓ なら入れ終わり。トークン混入 0（.claude/worktrees は見ない）・docs の静的な storage 網址 0（data-fb 含む）・写真を本番から落とす道 0・pages_served・pages_health --photos・sb_down_check を順に走らせる（本番に向ける 3 つは各 1 回・timeout 付き）。手元だけは `--skip-prod`。

## 点検の道具の本番読み（2026-11-04・egress）

- 本番の REST 読みは `harness/sbread.py` の 1 か所。**既定は 10 分の写し**（2026-11-04 逆にした：既定 0 だと ux_check の 6 か所が毎回本番へ出ていた）。毎回本番は `ttl=0`（photo_cache_fill の 1 日 1 回だけ）か `ux_check --fresh`（直した直後を比べる時）。写しの鍵はログインした人の JWT の sub（トークンが毎回変わっても効く）。版面の設定は丸ごと読まず `config->emblem` などの箱だけ。写し（`~/.cache/wl_sb_read`）には secret key で読んだ非公開の版面も平文で入る＝手元・Actions の一時領域だけ、リポジトリ・Pages・artifact に出さない。
- `photo_cache_fill.py` は毎日 1 回（photo_cache.yml）・boards と board_stories の 2 GET で、新しい写真を見落とさないため `ttl=0`。
- **ブラウザの Supabase 要求**（`browser.guard` の `_sb_route`、`WL_SB_BROWSER` で切り替え）：既定 `cache`＝GET と読むだけの rpc（`browser.READ_RPC` の名簿）は 10 分の写し（`~/.cache/wl_sb_browser`）から返す／`abort`＝rest・rpc・auth を全部止める（本番へ 0 件。落ちた時の見え方を見る点検用）／`live`＝全部本番（`--fresh`）。書き込みの rpc・ログイン（/auth/v1/token）は必ず本番へ通す（名簿に無い rpc は書き込み扱い）。点検の最後に「本番の /rest/v1/ への要求（python）・ブラウザから本番へ（rest・rpc・auth 別）・写し・止め」を出し、写しが空の最初の回でも python の /rest/v1/ が `ux_check.REST_MAX`（12）件を超えたら ✗。tests/test_sbread.py が直書き・ttl=0・config 丸ごと読みを数える。
