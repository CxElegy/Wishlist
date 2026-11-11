// クラウドで使った係の台本の例（2026-11-06「スマホの左写真カード」の回）。PC では道具名（mcp__github__ → gh か git）とパス（/home/user/Wishlist・scratch）を読み替える。
// 次の回の『この回の仕事』の文は harness/lanes/next.md。本体は harness-forever.js。
export const meta = {
  name: 'harness-forever',
  description: '止まらないハーネスのループ：BACKLOG.md の次の段を作る→確かめる→直す→合併→本番で確かめる、一覧が空なら計画の係が次の段を足して続ける',
  whenToUse: 'ウォッチリスト通信のハーネスを回すとき（HARNESS.md）。1 回の起動で最大 args.max 段（既定 6）、終わったら会話か定時タスクが次の回を起こす',
  phases: [
    { title: 'Plan', detail: '一覧が空・全部あなた待ちなら、点検して次の段を足す' },
    { title: 'Step', detail: '1 段を作って PR・合併・本番で確かめる' },
    { title: 'Check', detail: '別の目で本番と設計書に照らす' },
    { title: 'Fix', detail: '落ちたら直す（2 回まで）' },
  ],
}

const MAX = (args && args.max) || 6
const LANE = (args && args.lane) || ''   // 'request' = 依頼の係：【依頼】の段だけ（HARNESS.md「依頼の係」）
const SP = (args && args.scratch) || '/tmp/harness'
const COMMON = `【緊急・最優先（2026-11-02 21:30 UTC、入口の会話が中継したユーザーの依頼）：Supabase のメール「cached egress 19.2 GB / 5.5 GB」。11/5 以降は全 API が 402（Fair Use）。使った量は請求期間のリセットまで消えない。11/4 中に本番へ入れる。BACKLOG の最優先の依頼（PR #794）を読む。DB の形は変えない・消さない・鍵は触らない。段ごとに PR→CI 緑→合併→本番確認。「無料枠の決まり」の本番ブラウザの制限（写しから読む・確かめは 1 回・timeout 付き）は守るが、この件の確かめは Supabase を route.abort した状態で見る点検（本番の Supabase に負荷を足さない）。【ふだんのループ（計画の係あり）。無料枠の決まりを守る：本番の写真は写し（Pages の /p/・state/photo_cache）から、本番に向けた確かめは各段 1 回・timeout 付き、Supabase の網址を増やさない。【ディスクの決まり：前の係はディスク満杯（空き 16MB）で止まった。今は掃除済み（空き 13GB）。終わるとき自分の worktree を git worktree remove（強制なし。未コミットなし・push 済みのときだけ）で消す。作業の前に df -h / を見て、空きが 3GB を切っていたら先に自分の古い worktree を同じ条件で消す。pkill -f は使わない。】前の係の引き継ぎ：storage を写しから読む変更と user_pages の毎回読み廃止は #872 までで済み。**この回の仕事（max 2・順に・重い仕事は同時に 1 つだけ＝昨日 5 時間枠で止まった。『7点后停止』などの時刻を理由に自分で止まらない）：BACKLOG.md の【依頼】2026-11-06『スマホの左写真カード』だけ。スマホ（390px）で左写真・右字のカード（.wall の .wc・.wc.sb・.card.sb・.tape）は、写真をカードの高さいっぱい・幅約 40〜45%（cover）にし、右の字はそれに合わせる。今は .wc:not(.lead) が 120px 列で 16/10 の写真が上に寄り下が空く。型ごとに規則で（個別の手直しにしない）。店長もお客さまも同じ作り。前／後の 390px スクリーンショットと harness/scroll_measure.py の数字を出す（harness/browser.py の launch・timeout 付き・各 1 回）。★PR の前に python3 scripts/check_arch.py origin/main と変えた scripts の試験を手元で回し、render の埋め込み JS を壊さない（python3 harness/js_check.py --render）。段ごとに PR→CI 緑（测试・402 通し点検の両方を check_runs で）→合併。DB の形は変えない。終わったら worktree を消す。★お客さまのトップの『これからの予定』が店長と同じ条件で出ているかを確かめ、出ていなければ直す（右の列の欲しい物は答え待ちなので作らない）。以降の順：E15 案 B（公式の源を足す：A2O LITE・漫威电影・FROM。閾値は下げない）→E10（既存の決まりで直せる所＋新しい規則は○×見本）→boards PATCH の書き手→live_* の見回り。次の順で：（前の①は②に繰り下げ）①boards の PATCH が 24 時間で 397 回（#811 の put_config 直後は 36 回だったのに戻った）——毎回内容が変わる別の書き手を特定する：本番の Supabase の edge ログ（log_attributes のリクエスト）ではなく、まず scripts/ を grep して boards を書く全部の道（library.py・library_emblem.py・library_design.py・user_pages.py・push_shop など）と、それを動かす workflow の頻度から見積もり、毎回変わる値（at・時刻・件数）を指紋で比べて変わった時だけ書く形に直す（put_config を通らない道が残っていないか）。DB の形は変えない。②E15 案 B（公式の源を足す：A2O LITE・漫威电影・FROM。ユーザーが 2026-10-31 に決めた「公式サイトのキャラ画像を主な手段に」の適用。閾値は下げない。お客さまの版面でも release_head_rejects）③E10（既存の決まり emblem.md に照らして直せる所を直す。本当に新しい規則が要る所だけ docs/testground の審査待ちに○×の見本ページを作って URL を BACKLOG の [?] に）。④live_status POST 688・DELETE 295・live_log 572/日の見回りを減らす（BACKLOG 既存「API の見回りを減らす」）。本番ブラウザの確かめは各段 1 回・timeout 付き。終わるとき自分の worktree を消す。 優先（答え待ちでないもの）：①heat.html の札が文字に重なる 80（1400/390）の根を規則で直す②ゲストの ux_check ✗ E10（目標未達）・E15（主役がいない）・E24（小さいだけの絵が reject に残る）の根③お客さまのページの「ほかの注目ニュース」の空白（前の依頼）④製品の版面の Switch 2 のように題に会社名が無い場合の見本の補足（見本ページ docs/testground/product-head.html の更新だけ。本番は答え待ち）。答え待ちの段（審査の見本 4 枚の続き・欲しい物・製品の先頭の本番化・顔の大きさ 2 段目）は飛ばす。DB の形・鍵・消すことは [?] にして聞く。】
【無料枠の決まり（2026-11-02・最優先）：本番の写真は写し（~/.cache/wl_photo_cache、埋めるのは photo_cache.yml だけ）から読み、本番の Supabase の *.supabase.co/storage/ から落とさない（FILL_MAX は 0 のまま）。ブラウザは harness/browser.py の launch だけ。本番に向けた点検（ux_check など）は、この段の確かめの 1 回だけ・timeout 付き。見本ページ（docs/testground/）は写真を GitHub Pages か手元の写しで出し、storage の網址を直書きしない。写しが空なら「測れず」。】
リポジトリ /home/user/Wishlist（CxElegy/Wishlist）。最初に HARNESS.md・BACKLOG.md・CLAUDE.md・WORKING.md を main の最新で読み（触る分野の docs/rules/*.md も。CLAUDE.md の索引の表）、その決まりで動く。
作業は自分専用の worktree：\`git -C /home/user/Wishlist fetch -q origin main && git -C /home/user/Wishlist worktree add -f ${SP}/wt/{ID} -B harness/{ID} origin/main\`。メインの作業ツリーには書かない。一時ファイルは ${SP}/tmp/。
GitHub は mcp__github__ のツール（ToolSearch で読み込む）、Supabase は mcp__Supabase__（旧プロジェクトにつながる。いまの DB の接続先は items.yaml の supabase_url＝docs/rules/local-pc.md。読む・足すだけ。DROP・DELETE・表の形を変える文はしない）。
PR は push → mcp__github__create_pull_request（本文の最後に「🤖 Generated with [Claude Code](https://claude.com/claude-code)」）。CI は get_check_runs で見て、走っている間は手元のテストや画面の点検など別の作業をする（ただ待たない）。緑なら squash で合併、赤なら直して push。
scripts/*.py か workflow を変えたら scripts/processes.py も（check_arch）。\`python -m unittest discover -s tests\` を全部通す。コミットの最後に
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
合併したら必ず python harness/ux_check.py を走らせ（本番をログインなし・test-a・test-b・test-c × 1400/390 で自動点検）、✗ があれば次の段より先に直す。そのうえで本番で確かめ（Actions の結果・データベースの行・https://cxelegy.github.io/Wishlist/home/ を 1400/390px）、BACKLOG.md のその段を [x]（PR の網址・日付）にし、気づいた次の段を足して合併する（進み具合は progress.yml が Discord に送る）。
待ち方：GitHub の定時（cron）の回が来るのを待たない（遅れる・抜ける）。確かめたいときは workflow_dispatch で起こしてその回を見る。待つ命令には必ず 15 分の上限、過ぎたら待ちをやめて次へ。
トークンの節約：コードを書くときは .claude/skills/ponytail（full）の考え、返す summary は caveman の書き方で短く（事実・数字・網址は残す。ユーザーに見せる日本語の文・画面の文字は普通の日本語）。大きな機能の前に BENCHMARKS.md（似たサイト・受賞デザイン）を読む。
設計の考え（DESIGN_PRINCIPLES.md）に照らして作る：まず店長（test1）のページで同じことをどうしているかを見て同じ部品で。あなた（ユーザー）が決める設定・見た目の方向は作る前に BACKLOG を [?] にして木の形で聞く。
エンブレム（小元素）はサイトの売り：出ない・表示が違うものはほかの段より先に、EMBLEM_PLAYBOOK.md の過去の直し方の型で規則を直す（1 枚ずつ手で直さない）。新しい壊れ方を直したら EMBLEM_PLAYBOOK.md に 1 行足す。
一番大事な決まり（HARNESS.md）：test-a・test-b などを個別に直さない（データの手直し・特定のアカウントだけの分岐はしない）、直すのはいつも規則。ログインしたお客さまはだれでも店長と同じ P5 の枠組み（令牌・硬い影・傾けた見出し・札・ポスター・版面の主題と配色・小元素・目次）を見て、違うのは中身だけ。素の箱は出さない。確かめは test-a（多い）・test-b（1 つ）・test-c（0 個）を並べて。段を終えたら PROGRESS.md に 1 行（日付・何をした・PR・確かめた結果・次）。
段を取る印：BACKLOG の \`[~] … （開始 日付 時:分 JST・持ち主 {ID}）\` の形で書く（持ち主 = この係の名前。書き込みのたびに「最終 日付 時:分 JST」を足す）。\`python harness/claims.py BACKLOG.md --live <今動いている係の名前,…>\` で持ち主のいない [~]（持ち主が動いていない・書き込みから 60 分・書き方が古い）を出し、それは取り直してよい。動いている持ち主の新しい [~] は飛ばす。「取った」と知らせるのは、その段の最初のコミットが main か PR に出てから（BACKLOG の印だけで言わない）。
全体に効かせる（HARNESS.md「その箇所だけ直さない」、ユーザー 2026-10-26）：指摘された 1 か所・1 枚・1 版面だけを直さない。①なぜそこが壊れたかを規則の言葉で書く ②同じ規則で壊れている所を全部数える（連動の範囲の 5 つ：同じ種類の版面・店長とお客さま・同じ部品の画面・同じ数字の場所・前に作ったもの）③規則を直して全部に当てる ④ux_check か tests に、同じ壊れ方を数える点検を足す。PR の本文に「連動の範囲：…（n 件）」と「点検：…」を書く。⑤そのうえで「同じ考えでほかに直せる所」を 1〜3 個探し、BACKLOG.md に段として足す（返す spread・similar に書く）。
設計書にない新しい決めごと・本番のデータベースの形を変える／消すことが要るときは、作らずに BACKLOG.md を [?]（聞きたいことを木の形で、案ごとに良い点・困る点とおすすめ）にして status=asked で返す。答えが設計書から決まることは聞かない。`
const RESULT = { type: 'object', properties: {
  status: { type: 'string', enum: ['done', 'asked', 'failed', 'none'] }, step: { type: 'string' }, pr: { type: 'string' }, summary: { type: 'string' },
  spread: { type: 'string' }, similar: { type: 'array', items: { type: 'string' } } },
  required: ['status', 'summary'] }
const PLAN = { type: 'object', properties: { added: { type: 'array', items: { type: 'string' } }, pr: { type: 'string' } }, required: ['added'] }
const VERDICT = { type: 'object', properties: { ok: { type: 'boolean' }, problems: { type: 'array', items: { type: 'string' } } }, required: ['ok', 'problems'] }

const done = []
let planned = 0
for (let i = 1; i <= MAX; i++) {
  const id = `${LANE === 'request' ? 'r' : 'f'}${i}`
  let r = await agent(COMMON.replace(/\{ID\}/g, id) + `\n\nmain に hermes/ACTIVE があれば（Hermes が作る係）何もせず status=none で返す。なければ ${LANE === 'request' ? 'BACKLOG.md の【依頼】の付いた [ ] の上から、ユーザーの答え待ち（本文に [?] の答えが先に要ると明記）や持ち主のいる [~] で進められない段は飛ばして、進められる最初の 1 つだけを進める（依頼の係。先頭が答え待ちなだけで status=none にしない）。取ったらまず main の BACKLOG.md でその段を [~] …（開始 日付 時:分 JST・持ち主 ${id}・依頼の係）にして push し、ふだんのループと重ならないようにする' : 'BACKLOG.md の「いちばん先」の上から最初の [ ]（持ち主のいない [~] も：claims.py で出る）を 1 つだけ進める'}。【重要な用件だけ（2026-10-30 ユーザー：「ただ重要な用件だけ実行するように」）】進めるのは次のどれかに当たる段だけ：①本番が壊れている（ページが開かない・ログインできない・データが消える/見えない/漏れる・セキュリティ）②自動の仕組みが止まっている（后台・AI 編集・収集・公開の更新）③ユーザーが明確に直せと言った不具合（【依頼】の本文に「直して」とある壊れ）。【2026-10-31 ユーザーの審査待ちの答え（入口の会話が中継）で BACKLOG に入った【依頼】はすべて重要として進める：小元素のはみ出し＝案A、縦長写真の置き方＝案A（img.bg のぼかし 0）、ログインの札＝「⋯」メニュー、小カード＝案2（切る位置は顔・題字を測る）、BLEACH Mirrors High の公式サイトを第一の取り方に。小元素の 2 つ・縦長・小カードは同じ写真の部品なので一緒に設計してよい。】【2026-11-02 追記（ユーザー「确认的时候都做个网站，多可视化，点开链接可以直观看到改了什么、该改什么」）：確認は文字で聞かず、どれも testground の審査待ちに見本のページで：①欲しい物（A 表 wishes／B 👍一覧／C 隠す）②製品の版面の先頭（A 会社を版面に持たせる／B 安売りの減点）。今の本番のスクショと、案ごとに本物のデータで描いた見本を並べ、変わる所に印・押して選ぶと保存。製品の版面は iPhone 等で先頭が何から何に変わるか、全 product 版面で変わる数も出す。順番は：顔の大きさの 1 段目→並べ方の前／後→欲しい物→製品の先頭。DB の形は変えない（案を見せるだけ）。】【2026-11-02 最優先（ユーザー本人の言葉を入口の会話が中継：face-size.html と layout-v2.html の両方を不可。「没法直接改」「让我能直接 interaction」「大小还是参差不齐」「先从底层让我确认，再进阶到下一层，一步一步」「交代一下让我判断的背景，为什么要我判断，现在是什么样子」）：HARNESS の「審査は触って決める・下の段から 1 画面 1 段」に従う。①顔の大きさ：触って決める見本に作り直す。1 画面 1 段：1 分類（全身／胸像／ロゴ／物、札を押して直す）→2 顔の枠 ○×→3 胸像の顔 px をつまみで→4 全身→5 釣り合い→6 ロゴの文字→7 物→8 本物のページ 1400/390。前の段の答えを保存してから次の段を開ける。各段に「なぜ聞くか・今の実物の数字・何が変わるか」。中がばらつく見本は出さない（自分の点検を 0 にしてから）。まず 1 段目だけ作って公開し、網址を知らせる（BACKLOG に書く）。②並べ方：A/B/C の見た目の方向をやめる。今の見た目のまま、指摘のあった場所ごとに「今の本番／新しい並べ方」を左右に並べ、何が直ったか 1 行。聞くのは ○× だけ。まず ①の 1 段目を取り、次に ②。本番の DB の形は変えない。】【2026-11-02 夜の順番（入口の会話が中継したユーザーの依頼。まとめの段〔記事の並べ方の全体書き直し〕は別の係が持つので取らない）：①ユーザーのページを店長と同じに：ux_check に --diff-admin（同じ日の店長と test-a を 1400/390 でトップ・版面・設定の部品の一覧を比べ、違いを 1 行ずつ）→「管理なので無し」か「直す」に分ける→user_pages.py と AUTH_JS showMine の別の作り方を外し店長と同じ関数を通す→違い 0 を test-a〜e で。②ユーザーの 👍👎 を本人の account で feedback に書き、my_votes(p_account) で読み戻す（DB の変更なし：authenticated の INSERT は can_edit(account) で許可済み・my_votes(p_account) あり。足す・消す・形を変えるはどれも無し。影響表を埋める。test-a で 👍→u_ の行→再読込で押した状態・test-a/b/店長の票が混ざらない）。③小元素の顔の大きさ：人物は表示した顔の px を同じページで比べ最大÷最小 ≤1.2（E13 を表示の px で。全身と胸像で基準を分け、値は testground の審査待ちに 2〜3 組）、ロゴは文字の高さ ≤1.15、物・モンスターは外形。製品の版面の先頭（ランキングの変更）は範囲が大きいので作らず [?] にして入口の会話へ聞く。DB の書き換え関数 5 つ・管理者ログインの鍵は触らない。本番の DB の形は変えない。】【2026-11-01 最優先 0（ユーザー「老是ci fail 你改改呀」。入口の会話が調べた根：pages build and deployment が 24h で 8/30 失敗、全部 deploy で「in progress deployment, cancel <前の commit> first」＝main への push が多すぎ（24h で 312 コミット）で公開がぶつかる）：①.github/workflows/pages.yml（push main・workflow_dispatch、upload-pages-artifact docs/、deploy-pages、concurrency group pages cancel-in-progress true）を作って合併。切り替え前に Actions 側の公開が通ることを workflow_dispatch で確かめる（GitHub Pages の Source の切り替えはユーザーがやる。係は触らない）。②係の BACKLOG・PROGRESS・状態の push を段の終わりに 1 回へまとめ、render の再生成も間隔を空ける（processes.py も更新）。CI の確認は push 前に全部の試験を手元で。本番の公開の設定は変えない。】【2026-11-01 最優先 2 つ（ユーザー本人の言葉を入口の会話が中継。BACKLOG の先頭に書いてある）：①スクロールで下へ行くと写真が出ない（Astrae Oratio の小カード 6 枚が色の枠のまま。写真は置き場にあり src も入っている。店長のページは lazy 2,880 枚）。画面に入ってから出るまでの時間を Playwright で全 img 測り、原因（lazy の距離・同時数・JS が隠す・CDN 遠い）を数字で分けてから直す。物差し＝画面に入った写真の 95% が 0.3 秒以内。②並べ方の考え（DESIGN G・L1〜L6）で重ねて作り直す：決まった升目でカードの高さがそろって下が空く根を直し、同じ升目の所すべてに。空白の割合を ux_check で。見た目が 2〜3 通りあれば testground の審査待ちに見本。最初のコミットが出たら入口の会話へ知らせる。2 本の係が①と②を別々に取ってよい（[~] の持ち主で分ける）。】【2026-11-01 朝の順番（入口の会話が中継）：①ux_check の「写真の余白」を、各棚を画面に入れて読み込ませてから数える形に②ux_check を人ごと・ページごとに分けて、1 回 500 秒以内で全部完走できる形に（結果を人ごとに書き出す）③周杰伦の先頭の写真が置き場に無い件。縦長の 390px 実機はユーザーに頼むので飛ばす。DB の書き換え関数 5 つと管理者ログインの鍵は触らない。】【2026-10-31 夜の順番：「縦長写真の残り（390px 実機・テープの狭い棚）」はこの環境の網が切れて測れないので飛ばす。取るのは、①小カード案2（写真を正方形に近く・札は左下に小さく・切る位置は顔と題字を測る・主役の 6 割が残らない絵は切らずに別の写真か全体表示）②ux_check の残り（dota2 の頭の写真・Vaundy の先頭の写真・E2 の 403・三星手机 390 の E1）を規則から直す。DB の書き換え関数 5 つと管理者ログインの鍵は触らない。】新機能・見た目の磨き・デザイン案・点検の追加・「同じ考えでほかに直せる所」・小元素の細かい調整・見本づくり・ついでの整理は、本番が壊れていない限り飛ばす（status=none。自分で新しい段を足さない）。BACKLOG で「最優先」と書かれたユーザーの【依頼】（例：最初のニュースの読み込みが遅い）は重要として進める。2026-10-30 にユーザーが新しく出した【依頼】（管理ページの全区画で全ユーザーの中身を管理者アカウントから見て直せるように（まず③エンブレムを全アカウントの版面に。区画ごとの現状表つき。ユーザーのデータは公開 HTML に焼かず is_admin() の RPC で読む。RPC は足すだけ、消す操作は聞く）／最初のニュースの読み込み②の自前キャッシュ／「気になるかも？」小カードの写真の見える面積）も重要として、この順（BACKLOG の上の順）で進める。写真の「自前キャッシュ」は、ユーザーの言葉では「サーバー上に写真を一時的に保存して表示を速くする仕組み」で、キャッシュという名前にこだわらない：画面・管理ページ・コード上の呼び名は「写真の一時保管」にする（中身は変えない）。写真・RPC の待ち時間を測るときは、Supabase の地域（ap-southeast-2＝シドニー、日本から遠い）の分を数字で分けて出す（地域の往復・CDN が当たった後・ブラウザの描画）。迷ったら重要ではないとして飛ばす。進める段がなければ（全部 [x] か [?]）何もせず status=none。最後に status・step（段の名前）・pr・summary（日本語 3 行）を返す。`,
    { label: `step:${id}`, phase: 'Step', model: 'sonnet', schema: RESULT })
  if (!r) { log(`${id}: 返事なし`); break }
  if (r.status === 'none') {
    if (LANE === 'request') { log('依頼の係：【依頼】の段がもうない'); break }
    if (planned >= 2) { log('計画を 2 回しても段がない：この回は終わる'); break }
    planned++
    const p = await agent(COMMON.replace(/\{ID\}/g, `plan${planned}`) + `\n\n計画の係。HARNESS.md「設計者として導く」と DESIGN_PRINCIPLES.md の E（考えから反推した次の一手）のやり方で、A の考えから「まだ足りないもの」を反推して段を足す（E の表にも 1 行足す）。HARNESS.md「目標から決める」で、お客さま（test-a・test-b・test-c）が 1 日使ったつもりで通し（登録 → 足す → 読む → 👍👎 → 欲しい物）、いちばん困る所から段にする。店長（test1）のページの同じ機能の作りを見て、同じ部品で直す段にする。進める段が一覧にない。HARNESS.md の目標（小さな Wikipedia・1 つの仕組み・ライブラリ・人ごとのページ・言語・入口・管理）と、本番の画面（店長・test-a・test-b・ログインなし、1400/390px）・設計書との食い違い・壊れた画像・遅いページ・テストの穴を点検し、次にやる段を 3〜6 個、BACKLOG.md に「- [ ] 段の名前 — できたと言える条件」で足して合併する（答えが要るものは [?] で）。`,
      { label: `plan:${planned}`, phase: 'Plan', model: 'sonnet', schema: PLAN })
    log(`計画：${(p && p.added || []).join(' / ')}`)
    if (!p || !(p.added || []).length) break
    i--
    continue
  }
  for (let round = 1; r.status === 'done' && round <= 2; round++) {
    const v = await agent(`${COMMON.replace(/\{ID\}/g, id + 'v' + round)}\n\n別の目として確かめるだけ（直さない）。段「${r.step}」が終わったと言っている：${r.summary}（${r.pr || ''}）。本番と HARNESS.md に照らして本当にできているか、店長のページが壊れていないか。指摘の 1 か所だけでなく、同じ規則で壊れていた所が全部直ったか（連動の範囲を自分で数え直す。1 つでも残っていれば ok=false）、同じ壊れ方の点検が足されたか。`,
      { label: `check:${id}:${round}`, phase: 'Check', model: 'sonnet', schema: VERDICT })
    if (!v || v.ok) break
    r = await agent(COMMON.replace(/\{ID\}/g, id + 'f' + round) + `\n\n段「${r.step}」の続き。別の目の指摘を直して PR・合併・本番で確かめる：\n${v.problems.join('\n')}\n最後に同じ形で返す。`,
      { label: `fix:${id}:${round}`, phase: 'Fix', model: 'sonnet', schema: RESULT }) || r
  }
  log(`${r.step || id}: ${r.status} ${r.pr || ''}`)
  done.push(r)
  if (r.status === 'failed') break
}
return done
