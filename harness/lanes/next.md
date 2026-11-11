# 次に起こす係の台本（「この回の仕事」の文）

係を起こすとき、台本（`.claude/workflows/harness-forever.js` かその例）の「この回の仕事」にこの文を入れる。**1 つずつ。重い仕事は同時に 1 つまで。**
店長が見て決める見本（1）は、決まるまで本番に入れない。

## 1. 「記事の重さで組む」見本（案 C）

**この回の仕事（max 2）**：BACKLOG の【依頼】「版面の記事の並べ方を『型を選ぶ』から『その日の記事の重さで組む』」と【決定】「縦長の写真は案 C」だけ。
その日の記事の重さ（話題度・新しさ・👍・写真の形・字の長さ）で毎回組む規則を、テストグラウンドに**本物のデータで前／後の見本**（1400/390・空き面積の数字つき）として出す。
縦長の写真は案 C（写真を細くして見出しの列を広げる）。右下に余白が残るときは、①写真の高さと見出しの字の大きさを合わせる ②それでも余れば次のニュース・要約で埋める。
空きの面積を数えて 0 を目標にする。**本番には入れない**（店長が見て決める。決まった見本はテストグラウンドの「確認済み」の欄へ移す）。
PR の前に `python scripts/check_arch.py origin/main`・変えた scripts の試験・`python harness/js_check.py --render`。DB の形は変えない。終わったら worktree を消す。

## 2. スクロールの流畅性

**この回の仕事（順に・最大 max 段・ユーザー『スクロールするときの流畅性の問題も解決して』『现在还有点一卡一卡的』『引进网络的有名的 skill 来解决』）：BACKLOG.md の『スクロールの流畅性』の依頼と、全体点検の本 2 の①（もっと見るの中身 1.96MB を開いたときに読む＝要素 21,900→約 3,700）だけ。★作る前に Skill ツールで core-web-vitals・performance・performance-optimization・animation-performance・fixing-motion-performance を読み込み、その考えに照らして直し方を決める（PR に、どのスキルのどの決まりで直したかを書く）。★入口の測定（PR #948 合併後）：harness/audits/2026-11-05-scroll.md（原因 8 つ・前の数字・後の目安）を先に読み、測るのは harness/scroll_measure.py（前／後を同じ道具で）。今の本番は 1400 で 10.9fps・390 タッチで 50ms 超の frame 1,284。効く順に：①.sec>.grid と .picks>.pkbatch に content-visibility（section 全体は小元素が切れるのでダメ）②EMB_JS late() の画像ごとの IntersectionObserver 3,400→共有 1 個 ③NAV_JS の scroll で毎 frame 書く→IO＋transform ④FIT_JS の load ごとの全 grid の masonry→その grid だけ・読みを先に ⑤ResizeObserver 1,777 ⑥AUTH_JS のスマホ scroll ⑦drop-shadow 10 連。目標：①②③⑥で 1400 26fps・390 タッチ 50ms 超 78。★前／後の数字を必ず出す：本番 1400/390・CPU 4 倍遅く・スクロール中の長いタスクの数と合計・描画（paint/layout）の時間・要素数・最初の HTML の大きさ（harness/browser.py の launch・storage 止め・timeout 付き・各 1 回）。触るファイル：scripts/render.py・docs/home の新しい assets・tests の該当。★機能 B の係も render.py を触ったので、始める前と PR の前に main を取り込む。表示が変わる所（もっと見るを開くと 1 秒以内に中身）を壊さない。DB の形は変えない・消さない。段ごとに PR→CI 緑（测试・402 通し点検の両方を check_runs で）→合併→本番で数字。終わったら worktree を消す。**

## 3. 引っ越しの後片付け（済：1・2 番目は #960 付近と #988・#990。残りは BACKLOG の「休止の札」の段だけ）

- （済 2026-11-07 pc_watch.yml）写真の配信の毎日の見張りを新サーバーの死活（`/auth/v1/health` が 200／鍵なしなら 401）に替える。応えなければ入口へ知らせる。写真の配信の回数は Pages 側の記録（`pages_served`）で見る。
- （済 2026-11-11 #988・docs/test2 と archive は本 PR）旧 Supabase（`bzokpnbcjscbcehdxtjq`）を指す残りを `items.yaml` の接続先（`supabase_url`）から読む形に直す。直書きを 1 か所に集め、「旧プロジェクトの ref が残っていない」を数える試験を足す。対象：`scripts/choice_sample.py`・`face_sample.py`・`layout_ba.py`、`harness/emblem_pick_rules.py`・`fake402_check.py`、`.github/workflows/requests.yml`、`hermes/config.example.yaml`、`CLAUDE.md`・`LOGIN.md`・`PENDING.md`。
- 休止の札（`SB_DEG_JS`）を新サーバーの停止（5xx・接続失敗）にも効かせる。見る網址を接続先の設定から決め、402 の判定は残す。`fake402_check` の偽サーバーで 5xx・接続失敗のとき札が出て、復帰したら消えることを試験にする。

## 参考：スマホの左写真カードの回の文（済み・#952〜#955）

**この回の仕事（max 2・順に・重い仕事は同時に 1 つだけ＝昨日 5 時間枠で止まった。『7点后停止』などの時刻を理由に自分で止まらない）：BACKLOG.md の【依頼】2026-11-06『スマホの左写真カード』だけ。スマホ（390px）で左写真・右字のカード（.wall の .wc・.wc.sb・.card.sb・.tape）は、写真をカードの高さいっぱい・幅約 40〜45%（cover）にし、右の字はそれに合わせる。今は .wc:not(.lead) が 120px 列で 16/10 の写真が上に寄り下が空く。型ごとに規則で（個別の手直しにしない）。店長もお客さまも同じ作り。前／後の 390px スクリーンショットと harness/scroll_measure.py の数字を出す（harness/browser.py の launch・timeout 付き・各 1 回）。★PR の前に python3 scripts/check_arch.py origin/main と変えた scripts の試験を手元で回し、render の埋め込み JS を壊さない（python3 harness/js_check.py --render）。段ごとに PR→CI 緑（测试・402 通し点検の両方を check_runs で）→合併。DB の形は変えない。終わったら worktree を消す。★お客さまのトップの『これからの予定』が店長と同じ条件で出ているかを確かめ、出ていなければ直す（右の列の欲しい物は答え待ちなので作らない）。
