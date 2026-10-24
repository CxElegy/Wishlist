# 進み具合の記録（HARNESS.md「長い会話とコンパクト」）

段を 1 つ終えるたびに 1 行（日付・何をした・PR・確かめた結果・次）。コンパクトの直前にはフックが状態を自動で足す。

- 2026-10-23 ライブラリの表・店長の版面 23 個を写す（#254）、Wikidata の番号（#256・#260・#262）、Discord に進み具合（progress.yml）
- 2026-10-23 お客さまのページのポスター・気になるかも？を店長と同じ作りに絞る（#259）
- 2026-10-24 後台：コードだけの合併で全体の収集を走らせない・お客さまの版面 1 人 100・1 回 10（#263）。確かめ：収集 1 回 6〜7 分、push のたびの重なりが原因だった
- 2026-10-24 お客さまのページを render.render で作り Storage pages/<account>/index.html に置く・AUTH_JS の ownPage（#264）。本番の初回の job を確かめ中
- 2026-10-24 本番の初回：Storage pages に 4 人分（test-a 40 版面・test-b 1・test-c 0 ほか）。本人だけ読める・他人のは 400 を確かめた。1400/390 で店長と同じ枠組み
- 2026-10-24 だれでも同じ枠組み・版面 0 個も静かな版面「はじめに」・HARNESS「一番大事な決まり」・PreCompact フック（#266）
- 次：お客さまの記事に写真と原文の網址（写真がないとポスターが「新着なし」になる：test-b で見えた。規則で直す）、JS で描く素の箱（showMine の残り）を外す
- 2026-10-24 お客さまが足した版面の番号を今の規則で引き直す（#273〜#276）。本番 41 版面で Ado→歌手・京都→京都市・無印良品→良品計画、F1・NBA・生成AI はそのまま。途中の間違い（ポケモン・キャンプ・京都）は規則で直して戻した。次：店長とお客さまの番号の決め方を 1 つに
- 2026-10-24 店長とお客さまの版面の番号の決め方を 1 つに（#279）。compare=true の回で店長 23 版面すべて同じ番号、お客さまの結果も変わらず。次：月曜の回にも比べを入れる
- 2026-10-24 ライブラリの控えの時計（#281）：library.yml の毎時 41 分が抜けたら後台作業が users_only で起こす。本番で users_only の回は引き直しを飛ばし、後台作業の判断の段も通った。次：1 日分の回を数えて毎時来ているか
- 2026-10-24 ログイン後の白い画面・開き直しのくり返し（ユーザーが見つけた）→ 一時止め（#278）→ 殻のページ me.html で読み込む・render.yml でもお客さまのページを作り直す（#282）。harness/ux_check.py が本番を自動で点検：✗ 0（ログインなし・test-a 40・test-b 1・test-c 0 × 1400/390）
- 2026-10-24 ループ 1 回分（6 段）：Wikidata の番号まわり（#260〜#281）。目標から遠い内部の段が続いたので HARNESS「目標から決める」を足し、BACKLOG を「いちばん先（お客さまが毎日読める）」に並べ直した
- 次：お客さまの記事の写真と原文の網址 → 人ごとの 👍👎・欲しい物・気になるかも？ → ライブラリの版面ごとの記事集めと AI 編集
- 2026-10-24 お客さまの記事に写真と原文の網址（#285・#287）：userfeed で店長と同じ resolve_url・images.pick。本番：Google の跳转 0・写真 test-a 177/438・test-b のポスターが写真つきの頭条に。ux_check ✗0（ポスターの「新着なし」も見る項目に）。次：写真が半分を超えたか（2〜3 回の収集のあと）→ 人ごとの 👍👎・欲しい物
- 2026-10-24 お客さまの写真が半分を超えたか（#291）：test-a 414/444・test-b 10/12。期限付きの網址（Yahoo ?exp=、87 枚）を 6 時間ごとに確かめて切れたら原文から探し直す規則を足した。本番の回で 78 枚確かめ全部開けた、ux_check ✗0。次：切れたとき本当に差し替わるか（1〜2 日後）→ ライブラリの読み取り権限（案 B）→ 人ごとの 👍👎
- 2026-10-24 ライブラリの読み取りを案 B に（#292）：restrictive のポリシーを足すだけ。本番：ログインなし 23/64・test-b 24・test-a 63・店長 64、画面は同じ。期限付きの写真の段は 10-25 まで待つ印を付けた。次：follows を本人が読める（権限のエラー）→ 人ごとの 👍👎
- 2026-10-24 follows を本人が読める：public.my_account（security definer）経由の policy に（#294）。REST で test-a 40・test-b 1・test-c 0・anon 0。次：網页が follows を読む
- 2026-10-24 お客さまのページの置き方をライブラリの follows から（#297）：板块・小分類・篇幅・並び。picks とのずれ 0 を先に数えた。本番：test-a に小見出し 23 種・test-b 1、ux_check ✗0。次：篇幅・分け方を本人が設定で変える
- 2026-10-24 外した版面が本人のページに残る後戻り（#297）を直した：own_picks は picks にある名前の follows だけ（#301）。本番：picks にない follows 0・render 4 人分失敗 0・ux_check ✗0。次：篇幅・分け方を本人が設定で変える
- 2026-10-24 出来事ごとに束ね、増えた分だけ AI に渡す（#306）：bundle.py と edit_brief。過去 7 日で誤まとめ 6/416、字数 29% 減（試算）。ux_check ✗0。次：本番の AI 編集で今の記事が残っているか・トークンの前後
- 2026-10-24 AI 編集を版面ごとに溜まったら起こす（3 件・2 時間・初めて）・1 日の上限 100 万 · https://github.com/CxElegy/Wishlist/pull/310 · 本番 background 40072168803 が 15:56 JST に 15 版面で起こした・ux_check ✗0 · 次：半日あとに回り方を確かめる
- 2026-10-24 増えた分だけの一覧（#306）の本番の回を確かめた：前の記事 31/34 残り、消えた 3 本は篇幅の上限で押し出されたもの。1 バッチ目の 1 版面のトークン 1.29 万（前 2.1〜2.3 万、約 4 割減） · https://github.com/CxElegy/Wishlist/pull/311 · 次：溜まったら編集が回っているか（半日あと）
- 2026-10-24 お客さまが自分の篇幅・分け方を設定で変える（#312）：店長と同じ render_settings を本人の分で作り me.html?p=settings で読む、my_size_set（follows.size）・my_nav_scheme_set（nav_schemes）。#312 の注釈で全ページの JS が止まり ux_check ✗8 → #313 で直し node --check のテスト。本番 test-b で押して DB・作り直しまで確かめた、ux_check ✗0 · 次：篇幅を版面の本数に効かせる・設定ページを P5 の枠組みに
- 2026-10-24 別の目の指摘を直す（#317）：test-c の設定ページも本人の分・篇幅で本数を切る（test-b 8→5）・kick_render を押すたびに（2 回押して後の回が勝つのを確かめた）・ux_check が設定ページも点検。ux_check ✗0（16 点） · https://github.com/CxElegy/Wishlist/pull/317 · 次：設定ページを P5 の枠組みに（見本を先に）
- 2026-10-24 ux_check にエンブレムの点検 E1〜E10（harness/emb_check.py、--emb full で全候補を差し替え・写真の一覧） · https://github.com/CxElegy/Wishlist/pull/319 · 本番 full：店長 1400＝小さい 1・切れ 1・重複 2・大乱闘の絵 3・届かない 4、390 は加えてはみ出し 5・題字に重なる 1、test-a E1 40・test-b E1 1・test-c ✓ · 次：お客さまの版面にもエンブレム
- 2026-10-24 合併後の ux_check（quick）で E2 が 16 枚の見誤り（画面の外の画像は loading=lazy で読まれていない）→ 測る前に画面に出す · https://github.com/CxElegy/Wishlist/pull/320 · 合併後の quick：店長 1400＝E7 1・E8 2・E9 3・E10 4、390 は加えて E5 1・E6 1（E6 は箱の端どうしの誤検出）、test-a E1 40・test-b E1 1・test-c ✓、E2 の見誤り 0。#320 の squash に決まりの Co-Authored-By が抜けた（main の履歴は書き換えない、以後は合併の文に入れる）
- 2026-10-24 エンブレムの点検を EMBLEM_AUDIT と合わせる（#321）：E6 は字そのもの（Range）・E7 は取るときの規則＋額の切れ（顔のモデル）＋切れ端・E8 に同じ動画・E11 何人も・E10 は main の状態 · https://github.com/CxElegy/Wishlist/pull/321 · 本番 quick：店長 1400/390＝E7 3（哈利波特・Black Panther・A2O LITE OA）・E8 3・E9 3・E10 4・E11 1、E6 0、test-a E1 40・test-b E1 1・test-c ✓。別人・遠景は画素で決められず目で · 次：お客さまの版面にもエンブレム
- 2026-10-24 お客さまの版面にも小元素（#322）：library_emblem.py＝店長と同じ fill_one を一時の items.yaml で、画像は公開の箱 emblems、結果は boards.config.emblem・user_pages が使う · https://github.com/CxElegy/Wishlist/pull/322 · 本番 run 40095633017（28 分）で 41 版面を全部試し 28 版面に 58 枚（報告の 29 は数え違い、DB で 28・0 枚 13）、ux_check：test-a E1 40→12・新しく E7 3（MGA・King Gnu・BTS）、test-b E1 1（広島旅行 0 枚）、test-c ✓。公開のログに版面・人の名前 → stderr も止めた · 次：キャラの版面の名簿（AniList の番号を Wikidata から）
- 2026-10-24 別の目の指摘を直した（#324）：emblem_state.note の「もう一度」を 24 時間の文に・BACKLOG の条件を書き直し（E1 は未達、名簿とロゴの穴の段を足した）・数を DB で 28 版面／0 枚 13 に・[?] run 40095633017 の公開ログを消すか · https://github.com/CxElegy/Wishlist/pull/324 · run 40101166095（手で 8 分）：library_emblem の段に名前 0（#323 を本番で確認）、3 版面を続き（139・141 が途中）。ux_check：guest 1400/390＝E7 3・E8 3・E9 3・E10 4・E11 1（前と同じ、390 は E4 1）、test-a E1 12・E7 3、test-b E1 1（広島旅行）、test-c ✓。test-a 390 が 1 度「開けなかった」（user_pages が同じ時刻にページを置き換えた）→ 走らせ直して ✓ と同じ中身 · 次：名簿とロゴの取り方の穴
- 2026-10-25 お客さまのキャラの版面の名簿（#327）：Wikidata から AniList（P8729→P8731）・Fandom（P4073→シリーズ P179）、fandom_api にハイフンの形・「:」のあと・転送先、RULES=2 で取り直し · https://github.com/CxElegy/Wishlist/pull/327 · run 40104597594：キャラ 7 版面 0→2〜12 枚、0 枚 13→6、ux_check test-a E1 12→5・test-b E1 1（広島旅行）・test-c ✓・guest は前と同じ（E7 3・E8 3・E9 3・E10 4・E11 1）。ux_check の「開けなかった（removeAttribute）」は emb_check の MEAS が消えた img で止まっていた → 1.5 秒待って探し直す · 次：題材の版面のエンブレム・名簿とロゴの取り方の穴
- 2026-10-25 題材の版面のエンブレム（#329・#330）：名前・小分類 → Twemoji の記号（なければ板块の記号）・Wikidata の画像は番号で・0 枚の版面を途中の版面より先に · https://github.com/CxElegy/Wishlist/pull/329 · run 40115130203 で 0 枚の 6 版面すべて 1〜2 枚、ux_check E1 全員 0（test-a 5→0・test-b 1→0）、✗ は店長の既知（E7 3・E8 3・E9 3・E10 3・E11 1）と test-a の E2 1（F1 の Commons ロゴ 429）・E7 4・E8 4 · 次：題材に代表の画像・Commons の網址を箱へ・キャラの同じ画像
- 2026-10-25 お客さまの版面の名簿とロゴの穴（#332〜#335）：分類・参照の続きで数える・Playable Characters・字だけ／図／古い写真・Commons のロゴは名前だけ・ロゴのない製品は P18・RULES 5 で全部作り直し · https://github.com/CxElegy/Wishlist/pull/332 · DB 41 版面 v5、原神・ゼルダが主役から、京都・大相撲の変な画像なし。ux_check test-b・test-c ✓。作り直しで BTS・iPhone が 0 枚（test-a E1 2）→ #335 で 0 枚にしない規則 · 次：BTS・iPhone の段（いちばん先の頭）・生成AI の 📦
- 2026-10-25 名簿の作り直しの穴（#336）：REDO でキャラも前の脇役を残さない・前と同じ値を null にしない・同じ網址は 1 本・not_character（List・Player・Smash Bros・vs.）・RULES 6 · https://github.com/CxElegy/Wishlist/pull/336 · run 40132592376（46 分 success）：41 版面 v6、原神から Aino 他 5 人・ポケモンから Player・Smash、モンハンから Felyne List・MvC が消えた、スプラ 3 の重複 0、iPhone 1 枚。ux_check：test-a E1 2→1（BTS）・E7 3→1（Mrs. GREEN APPLE）・E8 1→0、test-b・test-c ✓、guest は前と同じ（E7 3・E8 3・E9 3・E10 4〔绝区零 59/60 は管理ページの「違う」〕・E11 1、E2 は Commons 429 が出る回と出ない回） · 次：BTS・ゼルダの分類（Playable Characters がスマブラの参戦者）・名簿の順位で集める
