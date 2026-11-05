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
- 2026-10-25 【依頼】管理ページ「全体の構成（詳しい図）」の崩れ（#350）：etc 枠が grid-template-areas になく 4 列が 24px に潰れていた → areas に足す・libemblem を Actions 枠に・孤立 CSS 行を消す・札 3 行まで · https://github.com/CxElegy/Wishlist/pull/350 · render run 40137669318 成功、本番 ux_check 管理ページ 1400/390 ✓（ほかの ✗4 はエンブレムの既知の段 E7・E8・E1 BTS・E2）· 次：管理ページを 6 つに分ける
- 2026-10-25 【依頼】キャラの版面の人数を全部の版面で名簿から（#358＋続き）：find_sources を Wikidata・作品の分類・その作品の wiki だけ汎用・AniList より分類、実写は P161、NAMES_V で済みも数え直す · https://github.com/CxElegy/Wishlist/pull/358 · run 40143086136：チェンソーマン 171・GTA 6 7・マンダロリアン 17・FROM 11、BLEACH は 429 で次の回、dota2 の上書きは戻した · ux_check ✗4（前からのエンブレムの穴：漫威・A2O の切れ・Vaundy 重複・あつ森の SSBB・BTS 0 枚）· 次：実写の名簿の穴・Fandom の 429
- 2026-10-25 【依頼】管理ページを トップ＋6 枚に（#359）：render.ADMIN_PAGES・_admin_backend を now/table/sys に・7 枚に切り替え・前の admin.html#欄 は案内・version.json はページごと · https://github.com/CxElegy/Wishlist/pull/359 · render run 40144090252 成功、本番 ux_check 管理ページ 7 枚・全体の構成 1400/390 ✓（なくした欄 0）、ほかの ✗4 は既知のエンブレムの段（E7・E8・E1 BTS） · 次：全部の版面とエンブレムの作業ページ（③）
- 2026-10-25 キャラの版面の名簿の続き（別の目、#361）：分類に Wikidata P674 の登場人物がいるか（GTA 6 → gta の Characters in GTA VI）・手で数えた人数 ±10% の分類（dota2 Heroes）・名簿にいない人の小元素を外す（dota2 6 枚・GTA 6 4 枚）・NAMES_V 4（#362 の 3 の次）・failed のお客さまの版面も数え直す・後台作業が library.yml を起こす · https://github.com/CxElegy/Wishlist/pull/361 · 記録：#358・#360 のコミットの最後が「Co-authored-by: Claude」で決まりの行ではなかった（合併済みなので書き換えない、#361 から決まりの行）· 次：後台の回で dota2・GTA 6 の名簿と小元素、library_emblem の回で 140・142・145・146 の nv=4
- 2026-10-25 店長の名簿のキャラでない名前（#352）：subjects・roster で前から名簿にいる名前にも not_character・Special character も · https://github.com/CxElegy/Wishlist/pull/352 · run 40139179574：あつ森の対象に Player なし（Fandom 403 で 0 枚）・ux_check は前からの ✗（E7・E9 SSBB・E10・BTS E1・E2 429）＋Vaundy の E8 を段に · 次：種族・物の名前（Inklings・Zapfish）
- 2026-10-25 実写の名簿の穴（#362・#363）：live_cast＝作品の P161 → wiki: の記事の作品の P161（同じ言語の記事も全部）→ 記事の Cast の節・役は emblem_roles・NAMES_V 5。本番 run 40150270287：漫威电影 pool なし → 34・小元素 6 → 10（管理ページ 10/34）、哈利波特 pool 12（小元素 2/12 は別人で落ちる）。ux_check guest：E7 13・E2 4（前からの壊れ方、段を足した）。次：哈利波特の照合・店長の E7
- 2026-10-25 名簿の続き（#365・#369）：find_sources の Wikidata を wikihttp で（素の urlopen は 403 で GTA 6 を確かめられなかった）・名前のない端役（Unnamed …）を名簿と小元素から外す · https://github.com/CxElegy/Wishlist/pull/365 · 本番：dota2 Heroes 127・30 枚（伝承 6 枚なし）、GTA 6 gta / Characters in GTA VI 39・13 枚（Michael・Trevor・Niko なし）、ライブラリ BLEACH 476/200/80、140 呪術廻戦 139 人・145 ゼルダ 108 人 · ux_check ✗ 4（E7 切れ 13・E8 同じ画像・E9 あつ森 SSBB・E10・test-a E1 BTS：前からの段）· 次：142・146 の nv（次の library_emblem の回）・提交の modify/delete の衝突
- 2026-10-25 名簿から集まり・Unnamed を外す（#371）：emblem.groups（ページの分類 Music bands・Gangs）・NAMES_V 6・ライブラリの届かなかった版面の数え直しを running より先（1.5） · https://github.com/CxElegy/Wishlist/pull/371 · 本番：library_emblem run 40154776821 で 142・146 が最初（02:33、nv 6、142 は 1→3 枚）・後台 run 40156002872 で GTA 6 の名簿 39→27（19/27）・board 3 も 27・Unnamed/バンド 0 · ux_check：✗ は前からの段（店長 E2 1・E7 16、test-a E1 BTS・E4 2・E7 3）、test-b・test-c ✓ · 次：GTA 6 19/27 の止まり・dota2 の LoL・いたずらページ
- 2026-10-25 実写の名簿の穴の直し（#372、別の目の指摘）：fill_one の _recount（NAMES_V が上がった回は名簿がそろっていても roster）・wiki: のない版面は wd_enwiki の Cast の節・_same_person（Tenoch Huerta＝Tenoch Huerta Mejía）・役の <!-- --> を消す・emblem.save_cut／emblem_fill.drop_broken（切れ端・0 バイト）・NAMES_V 7 · https://github.com/CxElegy/Wishlist/pull/372 · 本番 run 40156839182：哈利波特 名簿 65・3/65、漫威 33・11/33、Black Panther・BLEACH 2 枚を外した。ux_check：guest E2 1→0・E7 17→15（残り E8 3・E9 3・E10 6・E11 1）、test-a ✗（E1 BTS・E7 3・E8 5、1400 で E2 1 F1 は 390 で出ない）、test-b・test-c ✓ · 次：切り抜きが作り直しで縮む根（fit_all）
- 2026-10-25 【依頼】Before / After を一目でわかるものに（#376＋続き）：「画面：」の行で欄だけ切り抜き・差 0 は写真なし・後で変わる PR は回のあとに After。本番で 2 回撮って差 0、合併の回 ✓・ux_check の ✗ は既にある小元素の段（E7・E8・E9・E10・BTS）だけ。次：後で撮る流れを次の LATER の PR で確かめる
- 2026-10-25 Before / After の別の目の指摘 5 つ（#376 の続き）：高さが変わったページは灰色で埋めて比べる（上 1400px だけ・赤枠なしだった）・入りきらない変化は変わり始めを上に・前か後にしかない欄は「ない」と比べる／両方撮れなければ「撮れませんでした」（「変化なし」と言わない）・後で撮る After は成功した回だけ・取れない artifact で全部止めない · テスト 11（新しい 3 つは前のコードで落ちる）· https://github.com/CxElegy/Wishlist/pull/380 · 本番：合併の回 40161082032 before_after ✓（「画面：index section.sec」の欄を 3 画面とも見つけた・欄がない 0・Discord 204）・ux_check test-b・test-c・管理ページ ✓、guest・test-a の ✗ は小元素の段（E7 19・BTS・E5 绝区零 +1px）＋新しい E2 三星手机（段を足した）· 次：画面の PR の切り抜きを本番で（BACKLOG に段）
- 2026-10-25 架构图の書き足しの場所の直し（#380 の別の目の指摘）：Before/After の新しい規則が library の lb1「items.yaml を読む」に入っていた → lb1 を「店長の版面 1 つずつ」に戻し pg5 に移す・テスト（pg5 に「撮れませんでした」・lb1 は元の文）。合併は commit_message で Co-Authored-By: Claude Opus 5.5 を渡す · https://github.com/CxElegy/Wishlist/pull/383 · 次：check_arch は processes.py が変わったかしか見ない（書いた場所は見ない）
- 2026-10-25 哈利波特剧集の小元素（#381、途中）：根＝役の記事・動画が前の映画の役者で別人 55。actor_role_images（出演者の記事・ファイル検索の「X as 役」）を役の記事より先に · https://github.com/CxElegy/Wishlist/pull/381 · 本番 run 40162216117：新しい取り方 5 枚・+0（遠景・切り抜きの検査）、手元で Hagrid・Lockhart が通る。ux_check ✗4 は前からの段（guest E7 19・test-a E1 BTS・E7 3）、test-b・test-c ✓ · 次：作品の記事の剧照を顔で出演者に割り当てる
- 2026-10-25 小元素のはみ出し・立体（依頼の係、[?] あなた待ち）：見本 testground/emblem-pop.html＝本番の店長のページの版面を読んで 3 案（A 15%・B 22% 硬い影＋ぼかし【おすすめ】・C 30% 2 色の影）の CSS を重ね 390/1400 で見比べ・管理ページ ③の「小元素」欄に見本 2 つへのリンク · PR は下 · 手元の Playwright で 3 案とも帯の上・右の縁から出て下の本文に重ならないことを写真で確認 · 次：答えをもらったら render.py の .emb と JS に同じ置き方＋ux_check
- 2026-10-25 哈利波特剧集の小元素（#381 の別の目の指摘）：名簿のずらしを STEP−HEAD ずつ（65 人の 30 人に届かなかった）・実写の「役（出演者）」を出演者名で見る・額で切れた切り抜きを取るときも前からも外す（emblem.forehead_cut）· https://github.com/CxElegy/Wishlist/pull/389 · 本番 run 40167195059：額切れ 4 枚（The Mandalorian 3・Harry 197×101）を外し Harry は役の写真 373×412 に、ux_check guest E7 20→12（額 0）・test-b/c ✓ · 次：前からの上の端 >50% を drop_broken に・Oliver Wood のぼやけ（34）・剧照の顔の割り当て
- 2026-10-25 小元素の中身の誤り 2 つ（依頼の係）：頭のてっぺんが切れた切り抜き（上 3px に 20%）・ぼやけた写真（顔の幅 80px・鋭さ 1.0）を取るときも前からのものも外す、お客さまは RULES 7 · https://github.com/CxElegy/Wishlist/pull/392 · 本番：後台 run 40170194681 で店長の壊れた小元素 52→42、ux_check E7 guest 51・test-a 9（新しい点検が拾った）· 次：失敗の待ちでも壊れた版面は待たない（続きの PR）→ 後台・library の回で E7 頭のてっぺん 0 を確かめる
- 2026-10-25 小元素の中身の誤り 2 つ（別の目の指摘）：#398＝broken_cuts の額は上の端 > TOP_TOUCH のときだけ・BROKEN_V 2 の unbreak で前の規則で外したものを見直し・作り直しの剧の役は untied_roles（Padma Patil）· https://github.com/CxElegy/Wishlist/pull/398 · 本番：後台 4bc85fe3（#397 の回）のあと main a8f915c9 で店長の broken_cuts 42→0・Oliver Wood は items.yaml と網页から消えた・哈利波特は Harry の役の写真。BACKLOG の [x] は条件を「規則と店長 0」に書き直し、全部の版面の E7 0 は下の段へ。お客さまは RULES 6 のまま 12 版面 · #398 の後台 run 40172742027（e2bc49ca）：The Mandalorian 9→11（2 枚戻った）・broken_cuts 0・FROM 23→20（untied_roles が作り直しでない剧の動画の場面も外した → 段を足した）· ux_check（--who で 4 つに分けて全部の組）：guest E7 51→0・test-a E7 9→4（お客さまの版面）・test-b/c ✓ · 次：library_emblem run 40173290178 で RULES 6→7・test-a E7 0
- 2026-10-25 哈利波特剧集・小元素（#389 の別の目の指摘 2）：額の判定を上の端に当たったときだけに・前の規則で外したものを unbreak で戻す・作り直しの剧の役の記事の画像だけでは本人にしない（tied） · https://github.com/CxElegy/Wishlist/pull/398 · 本番 run 40172742027・40173475123：The Mandalorian 9→11/17・哈利波特 Padma（映画の写真）外れ 2 枚・FROM 23→20・BLEACH は #392 の head_cut で −31（96） · ux_check guest E7 13→0・test-b／test-c ✓ · 次：剧照の顔の割り当て（哈利波特 6 人）
- 2026-10-26 小元素の中身の誤り 2 つ（別の目の再確認）：店長 broken_cuts 0・Oliver Wood なし・ux_check E7 は guest/test-a/b/c とも 0（残りは E8 Vaundy・E9 あつ森・test-a の Mrs. GREEN APPLE・BTS＝running）・unittest 831 OK（opencv<5）。次：library_emblem の failed 24 を 0 に
- 2026-10-26 哈利波特剧集の小元素（剧照の顔の割り当て）：#404 の assign_stills のあとの本番の後台で 2 → 出演者 9 人＋ポスター＝10 枚（条件 6 人以上）· https://github.com/CxElegy/Wishlist/pull/404 · ux_check guest 哈利波特 ✗ なし（残り：E8 Vaundy 2・E9 あつ森 SSBB 3・E10 13・E11 A2O LITE 1・390 E2 星巴克马克杯 1）· 次：三星手机／星巴克 E2 の画像が消える根

- 2026-10-25 記事の写真が出ない段：PR #405。写真探しは 3 時間おき 3 回・頭は写真のある記事・写真なしは字だけ。ux_check ✗0（札 8/195、お客さまのページの再生成待ち）。次：迷惑リンクを落とす規則・札 0 の確認。
- 2026-10-26 哈利波特剧集の小元素（別の目の指摘 3）：Hermione 194×92 は髪だけで顔なし → emblem.faceless_scrap（写真で顔なし＋横長 ✗、check_whole・broken_image・BROKEN_V 3、兜は残す）· 手元の全 photo 小元素で当たるのは Hermione のみ・unittest 835 OK · https://github.com/CxElegy/Wishlist/pull/408 · 本番の後台 run 40238331036 で Hermione の髪だけの絵が外れ、別の剧照（404×478・顔あり）に替わった・ux_check guest E7 なし（残りは前からの E8/E9/E10/E11）。次：Harry のカチンコ／Ronald は 36 の形の健康
- 2026-10-25 小元素の切り抜きの形（依頼）：PR #409。根＝face_fit の横切りで垂直の切り口・check_whole が下 35% を許す。cutshape（左右 15%・上 25%・凹み 0.45）→ 半身に直す（trim_flat）か外す、前からは repair_flat／drop_broken（BROKEN_V 4）、E12 点検、Before/After の赤枠に小元素を丸ごと。手元の 474 枚中 57 枚が当たる。次：後台の回で本番の E12 を 0 に・Before/After 確認。
- 2026-10-26 三星手机の小元素 E2：本番を ux_check（guest・test-a × 1400/390）で測り E2 0（前の回までに直っていた）· コード変更なし、BACKLOG を [x] · 残り：guest E8 Vaundy 2・E9 あつ森 3、test-a E1（Mrs. GREEN APPLE・BTS）・E8 · 次：前からの上の端 >50% を drop_broken で外す段。
- 2026-10-26 小元素の形の傷（依頼の続き）：参照される小元素の形の傷は 3 枚（logo のみ）、「79 枚」は置き去りファイルだった · SOLID_MIN 0.45→0.30・BROKEN_V 5・0 バイト置き去り 2 枚削除・notify.py の weight 欠けを直し 842 本 OK · PR #414（合併 5156aea）· 本番 ux_check：E12 は guest・test-a・b・c × 1400/390 すべて 0、test-b・test-c ✓ · 次：合併後に ux_check と BROKEN_V 5 の回の戻り枚数
- 2026-10-26 持ち主のいない [~]（依頼）：harness/claims.py（持ち主・最終・60 分で「取り直してよい」を数える）· harness-forever の取る印を「持ち主 係名・最終 時刻」に · 「取った」はコミットが出てから · tests/test_claims.py 3 件 · 本番の [~] 4 本のうち持ち主付きは 1 本（この段）、残り 3 本は書き方が古く取り直し対象 · 次：見回り（20 分）が claims.py を回す。
- 2026-10-26 小元素の管理（依頼）お客さまの版面の分：管理者でログインすると管理ページ「小元素」にライブラリの版面のボタンが増え、替える・固定・外すが RPC board_emblem_request → config.emblem_requests → library_emblem.apply_requests（次の回で反映・固定は規則の版が上がっても残る）· 851 本 OK · 本番の確かめ（替える→別の写真・固定が残る）と「候補から選ぶ」は次
- 2026-10-26 前からの切り抜きの上の端 >50%：broken_image に TOP_MAX（店長 drop_broken・お客さま library_emblem 共通）· #420 · 后台作業を手で起こしたあと ux_check guest 1400/390 E7 0 · 次：E8 Vaundy・E9 あつ森・test-a E1 3
- 2026-10-26 小元素の管理（依頼）候補から選ぶ：管理ページ「小元素」の札に 🔍（押すと集め始め、次の後台で 4〜6 枚並び、1 枚選ぶと入れ替えて固定）· 店長 = state/emblem_cands.json（emblem_cands.run_shop が後台の頭）、お客さま = config.emblem_want/cands/picks（library_emblem.serve）· RPC board_emblem_request に _emblem_cands/_emblem_pick を足した（本番に適用済み）· 863 本 OK · 次：本番で 替える・固定・候補を店長ログインで確かめ、ux_check
- 2026-10-26 店長の版面の E7・E2：本番 ux_check guest × 1400/390 を quick・full で測り E7 0・E2 0（#420 で直っていた）· コード変更なし、BACKLOG を [x] · full の残り E4 2・E5 6（390）・E11 2（a2o-lite）・E8・E9・E10 · 次：小元素の残り ✗（E8 Vaundy・E9 あつ森）
- 2026-10-26 Fandom の 429：emblem._get をホストごと 1 本・間隔 1 秒・Retry-After（wikihttp と同じ考え）· テスト追加 · 次：NAMES_V の数え直しの回で後台ログの 429 0 を確かめる
- 2026-10-26 小元素 E5（別の目の指摘）：390px で横長の立ち絵（武器・尻尾）が右へ 1〜11px はみ出す根＝body の margin-right が重心合わせで負（绝区零・Astrae Oratio の候補 6 枚）→ ≤600px で max(…, -22px) · #424 とは無関係（管理ページのみ）· 本番に CSS を当てて 89 枚の候補すべて off ≤0 · ux_check test-b・test-c を別々に --emb full で ✗0（1400/390）· 小元素の管理の本番確かめ（🔍→候補→選ぶ）は管理者ログインが要り未実施 · 次：店長ログインで 替える・固定・候補
- 2026-10-26 ux_check の小元素の残り（依頼）：別の作品の絵・同じ画像・グループのメンバー・2 人並びを規則で（#426 #428 #433）。本番 ux_check で E8・E9・E2 が消えたのを確認、E1 は library_emblem の次の回待ち。次：E1・E11 の再点検
- 2026-10-26 GTA 6 が 19/27 で止まる：fill_one が失敗の理由に「画像のない人 N」を数える · https://github.com/CxElegy/Wishlist/pull/432 · 本番 retry_now 回で画像のない人 8（+0、残り 4 人は確かでない取り方）· ux_check の ✗ は既存（E1 3・E2 429・E11）· 次：確かでない取り方 4 人
- 2026-10-26 GTA 6 の残り 4 人：確かでない取り方の候補（ゲバラ写真・公式宣伝画像）は名前がなく、画像のない人に数える（emblem_fill._named_in）· PR 待ち · 本番の回で札に「全員が画像のない人」を確かめる
- 2026-10-26 小元素の残り ✗（別の目の指摘 4）：E1 は library_emblem が RULES 7 の 24 時間待ちで飛ばしていた → RULES 8 で本番の emblem_who が入った（YOASOBI 2・Mrs. GREEN APPLE 6・BTS 7、有 1・1・6）· E4 は顔のアップを --k の分戻して測る（Fennec・Dre'Quan）· E10 は残り 1 枚を除く · https://github.com/CxElegy/Wishlist/pull/436 · 本番 ux_check guest 1400/390：E4 0、残り E10 5・E11 2 · 次：後台の回のあと E11 2 と E10 5、test-a/b/c の full
- 2026-10-26 小元素 E1・E11 の確かめ：E1 はページの遅れ・E11 は後台の落ち（#437）が原因で、規則は変えず。#440：候補が尽きた版面を exhausted（24 時間おき・ux_check E10 は情報）、PLAYBOOK 44・45。本番 ux_check 4 人×2 幅：test-a/b/c ✗0、guest E10 だけ。次：E10（GTA 6・漫威电影・Vaundy・BLEACH・FROM）
- 2026-10-26 Fandom の 429：本番の後台 run 40264147288 で 429 0（Fandom 23 回・403 20 は別の話）· https://github.com/CxElegy/Wishlist/pull/427 · 次：名簿は大きくなったのに小元素が増えない
- 2026-10-26 小元素 E10（依頼）：exhausted が名簿の残り 100 人のうち 10 人を試しただけで付き 24 時間待ちになっていた → 残り全員を試した回だけ（PLAYBOOK 46）· PR 待ち · 次：本番の回で BLEACH 92→増えるか
- 2026-10-26 名簿は大きくなったのに小元素が増えない：チェーンソーマンを手元で再現し原因を特定（取景の多数決 keep_framing が新しい胸像 5 人を捨て emblem_reject へ。切り抜き・形の検査は全部通る）· 見た目の方向なので BACKLOG を [?]（案 A/B/C）· GTA 6・Mandalorian・哈利波特剧集は規則どおり（画像のない人・別人）· コード変更なし · 次：ユーザーの答え
- 2026-10-26 小元素の残り ✗（r2f1）：後台を手で起こし note を確認。#444 は効いている（exhausted は A2O LITE・Astrae Oratio・The Mandalorian の 3 つだけ）、BLEACH は +0 で理由＝使った／外した画像 18・画像なし 10。E10 の根は取景の多数決（[?] 待ち）· PR 下記 · 次：[?] の答え
- 2026-10-26 後台作業の提交が「違う」と同時で落ちる：pull_rebase.py で modify/delete を消した側が勝つ形に解く（background・digest・requests）· https://github.com/CxElegy/Wishlist/pull/446 · 手元の衝突テスト・全テスト 876 通過・ux_check ✗2（E10 既知のみ）· 次：分類に別の作品のページ（dota2）
- 2026-10-26 分類の端の企画ページ（f1f1）：参照だけの規則は Ringmaster（本物の新キャラ 33/5521）を落とした → 参照 1 割未満かつ記事 3000 字未満に変更（Yasuo・Irelia・John Raider だけ外す・127→124 見込み）· 記事の長さが続きの返事で 0 になる傷も直した · NAMES_V 9 · 次：本番の後台で dota2 名簿を確かめる
- 2026-10-26 小元素は見てすぐわかる人から：名簿の別の版 (Adventures) などを後ろへ（known_first・off_roster の並べ直し・NAMES_V 8）· https://github.com/CxElegy/Wishlist/pull/450 · 全テスト 877 通過・CI 緑・ux_check guest は既知の E10 のみ · 次：library_emblem 後にポケモン版面の最初の 10 枚を確認
- 2026-10-26 分類の端の企画ページ（f1f1）：本番で確かめた＝dota2 名簿 127→124（Yasuo・Irelia・John Raider なし・Ringmaster あり）· https://github.com/CxElegy/Wishlist/pull/451 · ux_check ✗ は E10 だけ（既知・[?] 待ち）· 次：[?] の答え
- 2026-10-26 f1f2：dota2 端のページの別の目の指摘＝EMBLEM_PLAYBOOK に 48 行目・BACKLOG の NAMES_V 8→9 と Blood* 5 枚は残す決定を記録（文書だけ）· 確かめ：PR #451 の差分・items.yaml dota2 emblem_pool 124・本番 200 は別の目が確認済み · 次：[?] の答え
- 2026-10-26 f2：1 画面目の穴＝日付の □（数字・等幅の書体に日本語の予備）・足の注記を畳む・ux_check に □ と頭条の写真 · https://github.com/CxElegy/Wishlist/pull/455 ・ https://github.com/CxElegy/Wishlist/pull/456 · 全テスト 878 通過・CI 緑・ux_check guest ✓（点検が本番の「N 件」の □ も見つけた） · 次：浮いているボタンが中身を隠さない
- 2026-10-26 f3：画面の PR の Before/After の切り抜きを本番で確かめた（4 つの場合 OK・欄は切らず欄ぜんぶに直した）· https://github.com/CxElegy/Wishlist/pull/459 · 全テスト 880 通過 · 次：check_arch で「書いた場所」も見る
- 2026-10-26 ポケモンの並びが直らない根（r1f1）：RULES 8 の作り直しで分類を捨てたあと、Pokémon の é で作品の呼び名が空になり own_wiki が外れて名簿が空だった（work_names を NFKD に、NAMES_V 10）· https://github.com/CxElegy/Wishlist/pull/458 · 手元：最初の 10 は全部アニメ · ux_check 本番：test-a ✗ は呪術廻戦 E11 だけ（作り直し中）· 本番 run 40291679538：boards.id=144 の最初の 10 は全部アニメ〔Red (Adventures) なし〕· 次：現行シリーズを先に（Liko・Roy）
- 2026-10-26 r1（依頼）：小元素の管理の本番確かめ＝実データで swap/lock を offline 再現 OK・tests 28 通過・本番の swap/lock 依頼は 0 件（店長ログインのクリック待ち）· PR なし（文書のみ）· 次：店長が 1 回「替える」→ 次の後台で確認
2026-10-26 r2：小元素の人を足す：見本 emblem-manage.html に「＋ 人を足す」を足した（1400/390 で確認）、置き方 3 案を BACKLOG [?] に。次：ユーザーの答え → 本番
2026-10-26 f4：check_arch が「書いた場所」も見る（#462）。変えたファイルを files に持つ流れの絵が変わっていなければ ✗、テスト 4 本・全テスト OK・CI ✓。次：ux_check（下記）
2026-10-26 f6：Before/After の後撮りを本番で確かめた（run 40299411618：After 送信 Discord 200・ba-pending-458 を送って消した・残り 0）· PR は下記 · 次：[~] 小元素の管理は店長のクリック待ち、次の [ ] は ux_check の小元素の残り
2026-10-26 r2：見本 #463 合併。ux_check：test-b/c ✗0、guest は E10 のみ（[?] 待ち）、test-a に呪術廻戦 E11 が再発 → BACKLOG に段を足した
- 2026-10-26 r3(hr10)：小元素の脇役が出すぎ→版面の顔は名簿の上位 max(12, 2 割)・最初の 1 枚は上位 3 人（PR #470）。本番 data-alts 12 枚前後を確認、ux_check の新しい ✗ なし。次：②Playable characters を先に
- 2026-10-26 f1f1：記事の写真が書いた人の顔写真（BLEACH Mirrors High・noisypixel）：根は JSON-LD の Yoast @graph の Person の image（theouterhaven の 100_0578-scaled.jpg）を拾い、別家報道で借りたこと。JSON-LD の Person/author を除き state/author_imgs.json に覚え、repair_images でも外す。tests 889 通過。次：合併後 repair の回で写真が替わるのを本番で確かめる。
- 2026-10-26 r4：小元素の選び方①「点数」の見本（emblem_fame.py・testground/emblem-pick.html）。3 版面で前後を並べた、本番は変えず。AniList の名前ゆれ（Tōshirō→Toushirou）を名字検索で拾い、Wikipedia は 429 を残さない。次：ユーザーの見本の答え（BACKLOG [?]）。
- 2026-10-26 f1f2：BLEACH Mirrors High の顔写真が洗い直しで残った→ repair_images の「代わりなしなら画像なし」に author_imgs を足した（PR #475）。本番 reports/2026-10-24.json image null・home に 100_0578 0 件。ux_check：guest は E10 のみ（前から）、test-a は呪術廻戦の札に写真なし 1（前から・別の段）、test-b ✓
- 2026-10-26 r1：小元素の「パッ」対策（decode 後ふわっと・場所と影・eager）。PR #480。遅い回線の点検 1400/390 ✓。ux_check ✗4 は前からの E10・呪術廻戦の頭。次：残りの写真類の同じ出方
- 2026-10-26 f2：小元素の選び方の見本を案 2 で作り直し（emblem_fame に公式人気投票・使えるキャラ・記事に出た回数、harness/emblem_pick_page.py に顔の大きさをそろえた胸像）。本番は変えず。確かめ：testground/emblem-pick.html を 1100px で画像確認、tests 追加。次：ユーザーの答え（BACKLOG [?]）。
- 2026-10-26 f3：test-a 呪術廻戦の E11 は本番で消えていた（ux_check test-a 1400：E11 0）。残りの「頭が写真なし」の原因は ORB でブラウザが頭条の写真を断ること（サーバーの規則の穴でない）→ BACKLOG を [?]（案 A/B/C）· 次：答え待ち
- 2026-10-26 f4：untied_roles/untied を作り直しの剧だけに（is_remake）。PR #484。確かめ：テスト全部・check_arch・本物の Wikidata（FROM False・哈利波特 True）・ux_check 新しい ✗ なし（E10・頭の写真なしは前から）。次：後台の回で FROM の 3 人が戻るか
- 2026-10-26 r2：記事の写真（.pic）も load 後にふわっと（PR #483）。遅い回線の点検 1400/390 ✓。ux_check ✗4 は前からの E10・E2(429)・E6。次：管理ページの小元素の欄の同じ出方
- 2026-10-26 f5：「脇役が出すぎる」を閉じた。①③は #470 で本番済み、②（ゲームで使えるキャラを先に）は [?] 選び方の作り直し案 2 の「+1.5」と同じ物差しなので別に作らず、OK 後の全部やり直しに含める（二重を避ける）。コードは触っていない。次：[?] の答え待ち。
- 2026-10-26 r2f1：パッと出る・残り：3 秒の保険を画面に入ってから数えるに（#490・画面外の lazy 写真が先に不透明になる穴）。本番 check_emb_fade 1400/390 ✓〔画面外の未着写真の行つき〕。ux_check の高さ測りを offsetHeight に〔回転で ±4px 誤検出〕。guest の E10（9 版面）は前からの別件。次：管理ページの小元素の欄
- 2026-10-26 f5f2：「脇役が出すぎる②」の別の目の点検。ux_check を今の本番で測り直し：ログインなし E10 8 版面・test-a 呪術廻戦の頭が写真なし 1（どちらも [?] の答え待ち）。前の E1 テニス・NBA E2・遅い回線の透明は消えた。コードは触らず。次：[?] 選び方の作り直しの答え
- 2026-10-26 plan1：計画の係。本番を test-a/b/c・guest × 1400/390 で計測し、ux_check が押さない・空のアカウントの次の一手が固定ボタンに隠れる・フォント 326 本 11MB・HTML 2.6MB・入口の見本が 6 日前、の段 5 つと [?] 1 つを BACKLOG に足した（E の表にも 2 行）。コードは触っていない。次：先頭の段から
- 2026-10-26 r3：「同じ考えでほかに直せる所」の 1 つ目：emblem_rules.sparse_keys（手書き emblem_* が 6 割未満の版面にしかない項目）。店長 23 版面で 12 項目（emblem_category 6・fandom 8・subject 7・roles/people 4・who 13 …）。点検のみ、管理ページ・ux_check への表示と規則化は次。
- 2026-10-27 ux_check --journey（空の test-d で入口→ログイン→足す→設定→外す、押す点検）（#501）。本番 1400/390 は ✗（殻のページの素の箱・設定ページの二重描き・札が外れない＝本物の不具合）。次：殻のページを P5 の部品に・設定の二重描き。合併後の ux_check：guest は E10 だけ（前からの）、test-a E2 は画像サーバーの 429（一時）、遅い回線の点検は画面の遷移で開けず（一時）
- 2026-10-27 r1：顔の大きさを表示でそろえる（emblem_face：全部測る→fit/view で拡大も縮小も・顔 32% 目 30%）。tests 全通過・BLEACH 管理ページ 1400 で顔そろう。PR 合併後に本番確認。次：札 big/small の写真替え
- 2026-10-26 f6f1：ux_check --journey の足場を直した（待ちの文言 1 か所・見える a を押す・待ちを step に・背表紙の生 Markdown を規則で直す）（#505）。tests 923 通過。直した通しは「自分のページに札」で止まる（先の ✗ は未確認）。次：殻のページの段で札が出ない所から
- 2026-10-26 r4：管理ページトップに見本・試作の道（#504）。本番 ux_check 管理 ✗0、残り ✗ は E2(429)・E10・test-a 呪術廻戦の頭に写真なし（BACKLOG に段を足した）。次：呪術廻戦の頭の写真
- 2026-10-27 r1f1：顔の大きさ #502 の続き（お客さまの版面 17 個・135 枚が face なしだった）：library_emblem.measure_faces（fill_board の最後＋main で未測定の版面を 1 回測り直す）、ux_check E13 が網址の小元素も数える・E14（同じ版面の顔の大きさ最大÷最小 ≤1.25）。目の高さのずれ（店長 192 枚中 104 枚が 5% 超）は [?] で聞く。本番：library_emblem を起こして未測定 135→3（#507）。ux_check が render の nf 抜け（#507 の編集ミス、顔なしに nf が付かず E13 が guest 21・test-a 11 を出した）を拾い、直した。
- 2026-10-27 r1：呪術廻戦（test-a）の頭が札のまま＝写真の網址はあるが本物のブラウザで開けない（mantan-web の防盗链）ので、_photo_head（網址の有無だけで決める）が効かなかった。規則：開けない写真は SWAP_JS／ICON_NEXT_JS が記事カード全部で .nophoto（字だけの形）に落とす（店長・お客さま・全版面・頭／mini／小カード）。本番の数え（直す前）：札 guest 0／817 枚・test-a 1／193（呪術廻戦）・test-b 0／5。tests に実ブラウザの点検、ux_check は頭だけでなく版面の全記事を数える。次：合併後 ux_check
- 2026-10-27 f1：版面 0 個の最初の画面の主役を「選ぶ」ボタンに（#509・規則：block.start）。tests 928 通過・本番 ux_check test-c 1400 ✓。次：0 個の人の欲しい物・設定ページ／小さい端末の高さ
- 2026-10-27 f1b：版面 0 個の最初の画面の「新着なし」残り 3 か所（目次の件数・静かな版面の tag・2 つ目のリンク）を規則で外し、ux_check に .startgo 必須・新着なし字・入口数の点検。次：0 個の人の欲しい物・設定ページ／低い端末の高さ
- 2026-10-27 r1f2：#502 の続き（別の目の指摘）：目の線を最優先に view を直し〔店長 141 枚の札なし 67 枚が全部 ±5%、short 78〕・名前が logo の網址の画像をロゴ扱い〔E13 の 3 枚〕・ux_check E16。tests 935 通過。test-c 390 は本番で ✓（白画面は再現せず）。次：札 big/small/short の写真を選ぶ側の規則で替える
- 2026-10-27 r1f1 開けない写真の札をトップ（article.wc）・気になるかも？（.pk）も字だけの形に（#518・#519）。ux_check は全文書の札を下までスクロールして数え、頭が字だけを別に ✗。本番：札 0、頭が字だけ guest 2・test-a 3＝[?] 答え待ち。次：[?] の答え／ux_check を who ごとに並列
- 2026-10-27 r2：名簿の先頭 3 人の穴 9 版面を理由で数え、人でない名前 4・役が見つからない 1 を規則で直した〔NOT_CHAR・role_of・NAMES_V 11・点検 E17〕（#526）。店長の E17 は 0、手元で Katee Sackhoff の役の候補 0→15。残り 6 人は選び方の作り直し待ち。次：後台の回のあと E15 を数え直す
- 2026-10-27 f2：0 個の人の設定（.startgo）・欲しい物（.go.big）も主役のボタンに（#525）、ux_check に 390×667/740 と設定・欲しい物。tests 940 通過・本番 test-c 設定 ✓。次：店長・test-a の設定ページの最初の画面
- 2026-10-27 f2f1：ux_check に欲しい物・話題度を全員・全幅で（runs_for）、0 個の殻の主役を node で描くテスト。単体 950 OK、本番 test-b・test-c ✓。次：guest・test-a の「版面の頭が写真なし」
- 2026-10-27 r2f1：#526 の続き。E15 の残りの原因を 2 つ規則で直した〔失敗の版面の待ちに規則の版が入っていなかった／姿勢モデルなしで顔のない動物が上半身に切られ持ち手が頭切れ扱い〕（#531）。tests 950 OK・guest ux_check は E15 6・E10 10・E11 4・E16 10（背景の回が未実行のため変化なし）。次：背景の回のあと E15 を数え直す
- 2026-10-27 f2f2：ux_check の殻ページを docs/home から数える（shell_pages）→ themes・terms・guest も点検、tests で数え直しと突き合わせ（#534）。本番 guest・test-b・test-c 全ページ ✓、test-a は既存の写真なし 2。次：衝突の印を CI で止める、通し実行を 15 分に
- 2026-10-27 f3：ux_check の「版面の頭が写真なし」「札」の誤検知を規則で（開けなかった写真を取り直して開くなら手元の回線の都合）。tests 954 OK、本番 guest 1400 で頭の ✗ 消えた。次：衝突の印を CI で止める
- 2026-10-27 r1：BLEACH の胸像の入れ替えに公式サイトの立ち絵を先頭で足した（#540）。一護 official→1026×1256、tests 955 OK・CI 緑。測っていない 3 枚・古い 18 枚の CI 赤も入れ替え後の測りで直した。次：公式を名簿の取り方にも
- 2026-10-27 r1f1：別の目の指摘を直した。顔のアップ→胸像の入口 3 つを official_for で共通に（#542）、点検 E19 と find_bust の official を縛る試験。tests 958 OK・CI 緑。ux_check：新しい ✗ なし（guest E10・E11、test-a E2 403 は前から）。本番は後台 run 40405692911 のあとも公式の入れ替え 0 件で未確認（待ち 8 人ずつ、Renji に未到達）→ BACKLOG を [ ] に戻した。次：数回後に E19 の公式あり・why を見る
- 2026-10-27 f1：空の人の「選ぶ」ボタンが .top の pointer-events:none（継承）で押せなかったのを直した（#545・#546）。本番 test-d 1400/390 で elementFromPoint が本人、journey は足すまで ✓。tests 960 OK・CI 緑。次：journey の「自分のページに札」30 秒待ち
- 2026-10-27 r1f2：#542 の本番の確認で原因を見つけた。BLEACH は失敗の待ちで 1 度も回らず胸像の n が止まっていた（run 40407957652 は dota2 だけ）→ due() で胸像待ちの版面は待たない（tests）。tests 全部 OK。次：直した後の回で E19・「公式サイトの絵」を数える
2026-10-27 f1 通しの「自分のページに札」✗：焼いた本人のページが足した直後は空だった → ownWait（#551）。確かめ：tests 961 OK、本番は焼き直し後に --journey。次：1 人分の即時焼き直し。
- 2026-10-27 r1f1：#550 の連動の残り。お客さまの版面〔stage_holds〕が旧 close_order[:8] のまま→close_round に・見込みを保存〔close_plan：各人 next・版面 eta。店長 state/・お客さま boards.config〕・点検 E20〔✗〕・入口が close_round を使う tests。確かめ：tests OK。次：後台の回のあと E20=0・上位 12 人の入れ替え
2026-10-27 f1 通し ✗ の続き（#554）：焼いた版と画面の食い違い・外す道・素の箱 1 つ・殻へ送る上限を跳ね返し回数に・id 重複を普段の回へ。確かめ：tests OK、本番 --journey 1400・390 とも ✓、ux_check は guest・test-a・test-b（--emb off）で枠組み・設定・欲しい物・話題度すべて ✓（✗ は小元素 E2/E7/E10 の前からのもの）、test-c は 580 秒で終わらず未確認〔通し実行を 15 分に収める段〕。次：0 個の焼いた版から空の「はじめに」を外す。
- 2026-10-27 r1f2：#556 の別の目の指摘。E20 にお客さまの版面（boards.config）の分を足し〔boards_closeup_bad〕、保存の式を closeup_fields にして tests で E20 に通した。確かめ：tests OK・ux_check の E20 は ✗ なし（お客さまの待ち 0 件）・library_emblem を dispatch して bv 9 になった版面に待ちなし。次：待ちが出る版面での next/eta の実書き込み
- 2026-10-27 f1f2：別の目の指摘（E2・E7・E10）。E2 は 0。E7 の原因＝顔検出器のしきい値を書き換えて戻さず判定が順番で変わる（7/487 枚）→ face_id.SCORE に戻す（#559）。tests 974 OK・CI 緑。本番 ux_check guest・test-a・test-b・test-c × 1400/390：E7 0、test-c 全 ✓、残りは E10・E15・E18。次：E18（test-a）
- 2026-10-27 r2f1：#560 の別の目の指摘。公式が先を gather の全入口（wide・pages・roles）に official_cands 1 つの口で。E21 点検＋全入口テスト。tests 976 OK・CI 緑・合併。ux_check：E21 BLEACH 2 人、✗ は guest 390 の E10・E15 のみ（前から）。次：E21 の取り直し
- 2026-10-27 f2：ux_check に「検出器のしきい値の戻し忘れ＝順番しだい」の点検（#562）。本番 guest E7 0。次：test-a の E18（短い辺 256px 未満）
- 2026-10-27 f3：小元素を取るとき短い辺 256px 未満を断る＋元を幅 1000 で取る（E18 の根：small_url が 400 に縮めていた。#566）。tests 983 中 3 件は main でも赤（Ayon 顔未測定・check_arch 未コミット時）。次：前から入っている小さい分の入れ替え（【依頼】元から小さい小元素）
- 2026-10-27 r2f2：E21 の取り直しの道。掃除の鎖に official_swap（Fandom → 公式、1 回 4 人・取れた人から・質が下がらないものだけ）。対象 2 人（実データで数えた）。tests OK・CI 緑・#565 合併。本番の後台の回は取り消しが続き未確認。次：E21 0 を確かめて ✗ に上げる
2026-10-27 r3：規則の版を RULE_VERSION_NAMES の 1 か所に・お客さまの失敗の版面も版が上がれば待たない（#568、987 テスト OK、ux_check の ✗ は前からの E10/E15/E16/E18）。次：NONE_V・RULES も同じ点検に
- 2026-10-27 f3：E18 の続き。save_cut の下限を既定に（upper_all ほか全入口）・fit_all の下限外れは emblem_reject へ・前からの小さい画像は too_small で外す（店長もお客さまも、1 回 8 枚まで）・全 save_cut 呼び出しを数える試験。tests OK。次：本番で E18 の減りを数える
2026-10-27 r4：公式の立ち絵が入れ替えで 15 回外れていた根を直した〔鋭さの比べ方・fs なしの捨て方、#570、992 テスト OK〕。ux_check の ✗ は前からの E10/E15/E16/E18（E21 Ichigo・Byakuya 残り）。次：後台 run 40441415497 のあと「公式サイトの絵」の件数を数える
- 2026-10-27 f4：お客さまの画面の文字（ownWait・drawMine）を言語表 UI へ・直書きを数える試験 UiWording〔残り 67 行は歯止め〕。tests 993 OK。次：AUTH_JS の残り 67 行
2026-10-27 r1 顔なしの小元素を 3 つに分けた（①看板の姿・②記号・③替える）・体の枠の表示・点検 E17/E22：https://github.com/CxElegy/Wishlist/pull/572 テスト 1001 OK・ux_check 新しい ✗ なし。本番の 3 分けは次の後台の回のあとで確認。
- 2026-10-27 f4：AUTH_JS の日本語の直書き 67 行を全部言語表 UI へ（別の目の指摘：内訳の数え違いも直した）。試験 UiWording を 0 と鍵の存在に。次：render._own_add など Python 側の直書き
2026-10-27 r2：BLEACH 公式の段を本番で確認〔Ichigo・Byakuya が公式サイトの立ち絵に・E19 BLEACH 0〕。E21 の誤り〔取り直し済みの行を Fandom 由来と数え、毎回取り直す〕を emblem.fandom_sourced で直した。tests 1004 OK。次：後台の回のあと E21 が 0 になるのを数える
- 2026-10-27 胸像待ちの見込み（依頼の係 r3）：本番で待ち 49→1 人・E20 ✗ なし・E19 1 枚＝確認済み · #550/#556 · 次：お客さま側の next/eta は待ちが出る版面を待つ・E10/E15 の別の段
2026-10-27 f5：Python 側のお客さま用の日本語 9 つを SETTINGS_JA へ（直書き 0・試験 PyWording）：https://github.com/CxElegy/Wishlist/pull/576。次：render.py の残りの日本語（店長と共通の札）は言語を足す段で
2026-10-27 f5f1：「⇄ にも」と FIRST_BOARD を SETTINGS_JA/ZH の表へ（店長の中文設定にも日本語が出ていた）・PyWording を user_pages 全体と render の own 経路の ast 数えに。次：ZH/JA の鍵そろえ点検・render() 共通部分の直書き
2026-10-27 r4：スマホ右下の札が一番下の字を隠さない（≤560px の body 下 72px＋ux_check COVER_JS）：https://github.com/CxElegy/Wishlist/pull/577 ・#578（点検の誤検出〔閉じた details〕を直した）。本番 ux_check guest・test-a・test-b ✗0。次：561〜760px を右下にそろえるかをユーザーに聞く
2026-10-27 f6：SETTINGS_ZH/JA の鍵そろえを試験で止める：https://github.com/CxElegy/Wishlist/pull/582 。全試験 1012 通過・CI 緑・合併。次：render.render の共通部分の日本語の直書き。
2026-10-27 r4f1：スマホ右下の札の続き（管理ページ 7 枚の点検・殻の safe-area 統一・試作 2 枚）：https://github.com/CxElegy/Wishlist/pull/583 。全試験 1012 通過・CI 緑・合併。本番 ux_check 390 guest/test-a ✓・管理 7 枚 390/560 ✗0。次：ux_check の --fast（全部だと 25 分超）。
2026-10-27 f1 ux_check --fast（札・枠組みだけ 2 枚×4 人×2 幅）＋お客さまのページの外れた写真を数え損ねる誤判定を直す。PR #587＋次の PR。確かめ：本番 --fast 手元 5 分 50 秒。次：頭の写真が 404 の版面（test-a 大谷翔平・大相撲）を焼く時に除く
- 2026-10-27 r1：顔なし 3 分け——nk・bb が items.yaml に書き戻されない根を直した〔#586・#588〕。確かめ：テスト全部 OK・CI 緑。本番の nk はまだ 0 件。次：測り直しが回るか。
2026-10-27 f1 頭の写真が開かない（404）版面を焼く時に外す：render.photo_opens・_head_photo（店長・お客さま・ポスター共通）、ux_check は DOM に残る外れた写真も数える。全試験 1020 通過。次：合併後の本番 ux_check。
- 2026-10-27 r1f1：顔なし 3 分け——書き戻しの許可リスト 1 か所〔recrop・upper_all も〕・後台は毎回全版面を測り直す・点検 E23。PR #591。確かめ：items.yaml nk 43〔keep 34・replace 9〕・bb 43・「?」0、ux_check guest E17 keep 10・E22/E23 ✗ なし。次：replace 9 が減るか・BLEACH 27 枚の原因
2026-10-27 f2 試作ページ d5 の殻を今の AUTH_CSS に作り直し、ずれを止める試験を足した。確かめ：試験・CI。次：試作ページの数え方を他の部品（render の定数）にも。
2026-10-27 r1f2 #595 お客さまの版面の nk・bb 欠け 31 件の根（測り直しの入口）を直した・E23 に boards・除外リスト 1 か所。tests 1025 OK・CI 緑・合併。次：library_emblem run 40472667446 のあと欠け 0 と ux_check
2026-10-27 f3 試作ページ d5 の殻を render.yml で自動に合わせる（--if-stale：ずれたときだけ作り直し、失敗しても発布は止めない）。試験つき。次：render の日本語の直書きを数える段。
2026-10-27 f4 ux_check の測る前に「字が出るまで最大 30 秒待ち直す」(settle) を足し、--fast の設定 1400 白い画面の取りこぼしを止めた。確かめ：試験 Settle 2・全試験・CI。次：管理・通しの決まった待ちも条件待ちに。

2026-10-27 r2f1 顔なし 3 分けの本番確認を完了：library_emblem run 40472667446 は success、boards 64 版面で nfv 78・nk/bb 欠け 0、ux_check guest・test-a/b/c × 1400/390 で E17・E22・E23 ✗ 0（#572・#591・#595）。残りの ✗ は別の段（E10・E15・E16・E18）。次：ux_check を人ごとに分けて速く
2026-10-29 r1 E15 の根：小さいだけで外した縮めた幅の絵を emblem_reject に入れていた（89 枚が大きい幅で取り直されない）→ wide_retry・BROKEN_V 11・unbreak で戻す。試験つき。次：背景の回のあと E15 を数え直す。
2026-10-29 r1f1 E15 の続き：縮めた幅の reject を実データで数える点検 E24 を足した〔合併前 80 件〕・お客さま unbroken が reject に入れない試験。PR は合併後に記す。確かめ：背景の回 run 40802808081 のあと E24 0・E15 を数え直す。次：外した理由を残す〔BACKLOG〕。
2026-10-29 r1f1 E24 を合併〔#603〕・背景の回 40803254817 のあと E24 80→5、E15 は 6 版面のまま〔取り直し待ち〕。次：E24 の残り 5 件の理由・外した理由を reject に残す。
2026-10-29 r1f2 E15：先頭の人を redo より先・外した網址を版ごとに 1 回見直す（release_head_rejects）・人ごとの理由を funnel.heads に記録して E15 に添える。PR #605。確かめ：背景の回 12:24 JST success、E15 6→5 版面（dota2 Crystal Maiden 戻る）、ux_check guest/test-a/b 1400/390 は E2（Wikimedia 403/429）と E10 のみ。次：Rukia（候補なし）と漫威・FROM・ILLIT・A2O LITE の理由別の規則
2026-10-29 r1 「頭が切れた」の段を閉じた：本番 ux_check 4 人×1400/390 で E7 全員 0（test-a・b・c ✓、guest は E10・E15・E16・E4 が別の段で残る）。コードの変更なし。次：E4 チェーンソーマン pochita の大きさ（47〜74px）を規則で。
2026-10-29 r2 小元素を待たせない第 1 弾：library_emblem.yml を 15 分ごとの見回り＋増えたら自分で次の回（#609）。確かめ：試験 Chain・ux_check --fast ✗0・手動回 40822513249 は --check 通過で実行中。次：①起きたらすぐ（収集・requests・library の終わりから dispatch）・chain の本番確認。
2026-10-29 r2f1 小元素を待たせない第 2 弾（④）：店長・お客さま両方の RETRY_HOURS 廃止、失敗は材料の指紋が変わるまで・時間切れは見回りですぐ（点検 E25・tests）。確かめ：手動回 40822513249 success（待ち 41→そろった 10・届かない 24・more=false で止まった）。次：15 分 cron の回と chain の本番確認、①起きたらすぐ。
2026-10-29 r2f2 小元素を待たせない第 2 弾の取りこぼし：時間で待つ固定文言 5 か所（processes・overview・render・admin.md・emblem_fill ログ）を直し、固定文言を数える点検（emb_check static_time_waits・test_no_time_wait_phrases_in_scripts_and_rules）を足した（#611）。確かめ：CI 緑、手動回 40826788854 success（fill 30 分の予算内で終了・chain 起動 2 秒）。ux_check：E25 0、guest は E10/E15/E16/E24（別の段）、test-a の E2 24 件は未確認（サンドボックスの画像取得失敗の疑い）。次：test-a E2 の本番再点検。
- 2026-10-29 r4：管理ページ②版面に「ライブラリの版面」欄（店長ログインでだけ全版面を読む・配色の変更 board_theme_set）。PR https://github.com/CxElegy/Wishlist/pull/613 ・本番に公開を確認・テスト全通過〔emblem_face 2 件は元から赤〕・ux_check 管理ページ ✗0（guest は小元素の E1/E2/E4/E10 のみ）。次：motif の通し・店長ログインでの確認（[?]）
2026-10-29 r4f1 管理ページ全版面の点検を足した（#614）：ux_check に「公開 HTML のお客さまだけの版面名 0」（本番 35 名・8 枚で 0 件）「管理ページの網羅」（店長の合言葉がないと未確認）、board_theme_set の anon execute を外した（本番）。boards の読みは boards_visible で anon は 23/64 のみ。次：点検用の店長アカウント [?]・未達 4 件。ux_check --fast guest/test-a に別件 ✗ 2（星巴克马克杯の近さ 390・生成AI の頭が写真なし 390）
2026-10-29 r4f2 管理者用 RPC の anon 権限の取りこぼし：board_emblem_request・admin_email_for を revoke from anon（本番適用・anon で実行できる admin_/board_ は board_visible のみ）。点検を名指しから数える形に（db/*.sql の関数を anon で呼ぶ）・公開 HTML を glob で全 19 枚・お客さま test-a〜e。確かめ：ux_check check_public_leak ✗0（35 名）・tests。次：anon 実行の security definer 41 本の総点検（BACKLOG）

- 2026-10-30 r1（依頼）：最初のニュースを速く 1 段目。画像ごとの onerror/onload を head の 1 か所へ。PR #618。本番 index 4.1MB→1.9MB・guest ux_check --fast 1400 ✓。次：自前の縮小画像・HTML を分ける
- 2026-10-30 r1f1（依頼）：最初のニュースを速く 1.5 段。残っていた inline onerror 4 か所〔xgal・小元素・wthumb・JS カード〕を data-e へ、最初の 3 枚を HTML で eager。点検を tests と ux_check に足した。次：Lighthouse で LCP を前後測る・自前の縮小画像
- 2026-10-30 r1：管理ページ③エンブレムの版面の札をライブラリ全版面に（店長の令牌・②と同じ読み方）· https://github.com/CxElegy/Wishlist/pull/623 · CI 緑・合併、ux_check は guest の既存の小元素 ✗ のみ（③の数は店長ログインの回で確認）· 次：④AI 編集を全版面に
- 2026-10-30 r1f1：③の続き。library_emblem.py の収集が followers>0 のままだったのを外した〔0 人の版面も小元素を探す・画面の約束どおり〕。tests に scripts 全体の followers 絞り 0 件の点検。本番 boards 64 行は全部 followers=1 で数は変わらず。次：④AI 編集・③の状態表を全版面に。
- 2026-10-30 r2：管理ページ④AI 編集に全版面の編集状態（admin_board_edit_state）。PR #626。tests 通過（emblem_face 3 件は環境差で既存）・ux_check ✗ は既存の 2 件だけ。次：③版面ごとの状態表・数字の全アカウント合計。
- 2026-10-30 r2f1：④AI 編集に「全員／ユーザーを選ぶ」＋載せた：待ちの棒（ライブラリの全版面）。ux_check に版面名が全部出る点検（UX_ADMIN_* の回）。tests 追加。店長ログインの本番画面は未確認（合言葉なし）。次：③版面ごとの状態表・数字の全アカウント合計。
- 2026-10-30 r2f3：「全員／ユーザーを選ぶ」を AUTH_JS の WL_WHO 1 つに部品化し②③④に横展開（④の自前コードを外した）。render.ADMIN_WHO／ADMIN_WHO_NO で全区画を「入れた／入れない理由」に分け、tests が漏れ 0 を数え、ux_check が account を選んで行が follows の通りに絞れるか・「全員」で戻るかを見る。手元は部品を stub で動かして確認（店長の資格情報がないので本番の店長ログインは UX_ADMIN_* の回）。次：投票・欲しい物と写真・篇幅・言語の全アカウント分（読み口の RPC から）。
2026-10-30 r1f1 管理ページ③の版面ごとの状態（全版面）・PR #631 合併・本番反映確認・ux_check guest は emblem 品質の既存 ✗ のみ（管理ページ起因なし）・次：投票/tokens の全アカウント化
- 2026-10-31 r2：管理ページ②全アカウントの 👍👎（admin_votes・全員／ユーザーを選ぶ）。PR #633 合併。tests 緑（顔検出 3 件はこの環境のモデル取得不可で既存）、ux_check --fast は既知の test-c settings 1400 のみ ✗。次：④の tokens 全アカウント合計。
- 2026-10-31 r3：管理ページ④tokens＝全アカウント分と明記（AI 編集は 1 本だけ）。PR #634 合併・CI 緑。顔検出 3 件は main でも赤。ux_check は後続。次：投票以外の残り（欲しい物・篇幅・言語・editdiff）。
- 2026-10-31 r3f1：④tokens の注記を事実に訂正（店長の分だけ・お客さまの版面はまだ編集されない）。BACKLOG は [x] を外し「注記済・お客さま専用の編集待ち」に。tests と ux_check に画面の文と編集範囲の食い違い点検。次：296・297（版面ごとの収集・AI 編集の書き込み）。
- 2026-10-31 r3f1：PR #635 合併・本番 admin-ai に反映・ux_check --fast ✗ 0 件。tests 緑（顔検出 3 件は既存）。次：区画ごとの注記点検。
- 2026-10-31 r3f2 管理ページの注記を ADMIN_WHO_NO「店長の」6 区画に自動で出す（panel()）。tests 区画ごと・ux_check 本番の画面で数える。次：「お客さまの版面も同じ編集」型の全文検索。
2026-10-31 r4 管理ページ②に全アカウントの分量・写真の受付・依頼・言語を足した（RPC admin_accounts／admin_ui_langs・店長のみ）。PR #638。tests 緑（emblem_face 3 件は環境で main も失敗）。次：関注項の中身・置き方。
- 2026-10-31 r1f1 写真の一時保管 続き：PR #641 srcset・全種類の写真・お客さまのページを同じ置き場に・ux_check に割合と srcset・publish を状態 1 ファイルに。本番 1168/1346 枚。LCP 実測 4.4〜7.8 秒（>2.5）。次：③HTML を分ける（案A）。
- 2026-10-31 r2 管理ページ②の全アカウント表に置いた板块・小分類つき・見たい種類・乗換駅つきを足した（RPC admin_follow_detail・店長のみ・本番に適用）。tests 緑（emblem_face 3 件は環境で main も失敗）。次：tokens はお客さまの版面の編集待ち。

- 2026-10-31 r2f1 管理ページ全ユーザー管理の指摘直し：置き方・関注項の中身を follows 1 行ずつ②に（RPC admin_follow_rows・admin_account_langs で言語も account に結ぶ・本番に適用・anon 不可を確認）。ux_check は値を follows と照合、列数ずれ(10/11)を直した。tests 緑。次：設定の書き換え・tokens。
- 2026-10-31 r1：写真 0.5 秒 第 1 回。最初の主写真を head で preload・cache-control immutable・ux_check 点検（PR #646）。確かめ：本番に preload あり・スマホ開始 627→256ms。次：④置く順・色の下絵。
- 2026-10-31 r1f1：写真 0.5 秒 第 2 回。根＝Mandalorian の主写真は lazy で目次から飛んで初めて取っていた。全版面の先頭の写真を先に取る（ahead）・既存写真の cache 上げ直し・点検を全版面に広げ・photo_time.py・settings 素の箱の race。確かめ：PC 365〜572ms。次：上げ直しの完了・色の下絵。
- 2026-10-31 r2f2 管理ページ②の指摘直し：ux_check の表のマスを列の位置（slice(7,11)・g[2]..）でなく data-k で読む・tests が admin_ の関数の is_admin() 守りと位置読みなしを数える・admin_email_for を authenticated から revoke（本番適用・anon/auth とも不可を確認）。店長ログインの回（UX_ADMIN_*）は鍵がなく未実行のまま。次：③の cells.slice(1,4) も data-k に。
- 2026-10-31 r1f1：写真 0.5 秒 第 2 回の本番確認（PR #648）。上げ直し 639 枚・cache-control 1 年 immutable・HIT。ux_check の cache ✗ は消えた。残る ✗ は picks の札 1（BACKLOG に段）。

2026-10-31 r3：「気になるかも？」小カードの写真が細い→枠の高さの床を規則に（PR #652）。見える高さ 1400px 0.22→0.5、ux_check に pkv。次：札が顔に重なる位置。
2026-10-31 | 写真 0.5 秒 第 3 回：再測定のみ〔PC 321〜571ms・スマホ 370ms・下絵は #651 済〕で区切り | 本番測定 | 次：なし（Fast 3G は物理下限）
2026-10-31 r1f2：写真 0.5 秒 第 3 回（PR #651・#653）。MondoXbox の札＝推薦 .pk が写真なしでも出典アイコンの札を出していた規則漏れ→最初から字だけ。色だけの下絵〔平均色 1370 枚・本番 1170 枠〕。本番 --fast は札 ✓、HTML 上限を 2.6→2.8MB に。飛び測定：PC 35ms・390 12ms・Fast 3G 507ms。次：ahead を早める。
2026-10-31 r2：漫威电影の名簿＝中の作品（P179 の 49 作）の出演者を出た回数順に上位 60（franchise_cast・NAMES_V 12）。根＝名簿が Avengers: Doomsday 1 作の 33 人で主役が入らず 3 枚止まり。次：合併後に emblem workflow を起こして 3→n を本番で確かめる。
2026-10-31 r1：審査待ちの欄＋縦長の写真 5 案（docs/testground/photo-fit.html）を作った | PR 後に記す・ページを 1400/390 で確認（横あふれ 0） | 次：②小カード案・③○× 作り直し見本
2026-10-31 r1：②小さいカード 3 案（docs/testground/small-card.html、見える割合 いま 50→案1 56・案2 85・案3 65%）。1400/390 横あふれ 0 | 次：③○× 作り直し見本
2026-10-31 r2：お客さまが admin_ の関数から中身を読めない点検 (#660)。本番 DB は admin_ 16 関数、15 は is_admin() の守り・admin_email_for は anon/authenticated とも不可。check_customer_admin_rpc 本番で漏れ 0。次：店長ログインの回(UX_ADMIN_*)。
2026-10-31 r2f1：管理者の中身の点検を強めた（②管理ページ直開き check_customer_admin_pages・ログイン 3 人未満は ✗・admin_email_for は権限を本番で確認・公開の書き換え関数の穴は tests/test_open_definer.py で固定し BACKLOG [?]）。本番で漏れ 0。次：[?] の答え待ち。
2026-10-31 r2f2：公開の書き換え関数の点検を引数名→「anon・SECURITY DEFINER・書き換え・守りなし」全体に（署名ごと・revoke 反映）。本番で数え直し 6 つ（5 つは承認待ち [?]、live_report は設計）。tests/test_emblem_face の手元だけ落ち 3 件＝モデルがある手元だけ走る（CI は skip）＋収集で画像が作り直され測り値が変わった→固定の画像 tests/fixtures/emblems に | 次：ux_check 全体を --who 別に background で
2026-10-31 r2f2 第 3 回：PR #664 合併。本番 pg_proc で書き換え関数の穴 6 件に確定。ux_check を background で走らせ guest ✗ は E10・E15 のみ・test-a ✗ 0 | 次：小元素 E15/E10 の規則
2026-10-31 r2f1：お客さまが管理ページを直に開く点検 check_customer_admin_gate (#662)。test-a・test-c × 7 枚 × 1400/390 で門・行 0・入口 0 ✓。漏れ 1 件修正（③loadLib を店長だけに）。ux_check 全体：②は ✓、残 ✗ は小元素 E10/E15・E2 | 次：小元素の E10/E15
2026-10-31 r1：審査待ち③ 小元素の選び方の作り直し見本 emblem-pick-2.html (#668)。規則 harness/emblem_pick_rules.py、印との一致 新しい 28/36・× を出す 0/16・○ 13/17。ux_check --fast ✗ 0 | 次：顔なし ○5 枚の扱い（案 A/B）と Ikkaku 型を聞く、④前からの 3 つ
2026-10-31 小元素の規則に本番の数え(--audit 340 枚中 × 32)と点検(tests/test_emblem_pick_rules.py)を足した (r1f1)。次：外れ 3 型と別の版面の検証
2026-10-31 r3：小元素の凍結を直した（PR #667）。根＝先頭 10 人が全員だめだと failed になり材料同じで永久に凍る（漫威电影 3/81 ほか店長 8 版面・お客さまも）。名簿を 1 周するまで続ける rounds/passes_left。tests 全緑・ux_check --fast ✗ 0。次：background の結果で 3→n を本番で確認、主役が別人で落ちる側の根。
2026-10-31 r1f1：写真の先取り（#670）の点検を足した：ux_check.ahead_bad が「1 版面ずつ・low／high・2.5 秒の上限・load 待ちでない」を数え、tests/test_images が実物の EMB_JS を照らす。本番は render.yml 実行中で旧版のまま、Fast 3G 測定は未 | 次：本番に出たら photo_time.py --slow／ux_check --fast
2026-10-31 r1f2：小元素の規則の点検を強めた（#669 への指摘）。× を数える棚 40 → 待ちの一覧 32 枚で増減どちらも落ちる、`--library` でお客さまの版面も数えた（見える 14 版面 257 枚：○171・× 9・− 77）。規則の本番適用は審査待ち③の答えまで見送り。次：審査の答え→選ぶ段に入れる、全版面の計測

- 2026-10-31 r1f2：写真の先取りを本番で実測（harness/ahead_time.py）。Fast 3G 25 版面の先頭：中央 15.6→14.1 秒・90% 23.8→17.5・最後 57.8→23.5（3 版面は未達）、続きの先取り 104→174 枚。3 版面ずつ・暇待ち 300ms・先頭の後に続き。ux_check に実測を追加。次：置き場に無い先頭の写真。

- 2026-10-31 r2：管理ページ③ 版面ごとの状態に記事・設計の列（PR #674）。guest・test-a ux_check --fast ✗ 0。次：お客さまの版面の記事集め（board_stories）ができたら列が埋まる
- 2026-10-31 r1：審査待ちの④ログインの札（docs/testground/login-dock.html・3 案）を足し、入口の審査待ちは全部そろった。テスト通過。次：答え待ち（A〜E・小元素の選び方・小カード・ログインの札）
- 2026-10-31 r2：写真の一時保管の置く順を「各版面の先頭の写真」が先に（photo_store.scan_text・test 追加）。次：回のあと ahead_time.py --slow で「届かない」が 0 になったかを本番で確かめる



- 2026-10-31 r3 hr31：漫威电影の小元素 4 枚止まりの根を規則で直した（BROKEN_V 13・実写は外した画像の札を全部解く／切り抜きで外れた人は同じ回で次の候補・PICK_PASSES 3）。手元で 1 回分（10 人）の枚数 0→4。残る壁は切り抜きの検査の厳しさと名簿後ろの人の画像の少なさ。次：本番の rounds・have を確かめる。
- 2026-10-31 r2f1：写真の置く順の続き。ux_check に lead_outside_bad〔先頭の写真が置き場の外に残る版面を数え 0 以外は ✗。SVG・GIF・shrink できない分は例外〕＋test。本番の render が終わるまで星巴克 2 件で ✗。次：render 後に ahead_time.py --slow と ux_check で 0 を確かめる
- 2026-10-31 r2f2：写真の先頭の点検をお客さまにも。ux_check の lead_outside を DOM 向けに（属性の順を問わない）、check() で test-a・b・c の描いたあとの DOM にも当て、例外〔SVG/GIF/ICO・x〕の数を「最初に取る HTML」の行に出す。test 追加・unittest 1098 OK。本番の店長 HTML は先頭 0 件・例外 0 件。次：ahead_time.py --slow で Fast 3G の全版面の実測
- 2026-10-31 r3f1 hr31：実写は先頭が埋まっていても外した画像の札を 1 回解く（release_head_rejects・哈利波特剧集 20 枚・The Mandalorian 21 枚）＋emb_check E26（実写で札が残り版が古い：本番 items.yaml 4 版面）＋tests 2 本。次：合併後 background で E26 0・漫威电影 headv 13 を本番で確認。
- 2026-10-31 r3f1 hr31：#681 の本番確認。漫威电影 have 5→10・headv 13 が 4 版面・E26 残り 2（哈利波特剧集・The Mandalorian、次の回で解く）。次：その 2 版面と E26 0 を確認。

- 2026-10-31 r3 hr33：最初のニュースの遅さの根を測り直し：LCP の要素は H2（4.6 秒）で、Google Fonts の CSS が描画を止めていた。font_link で止めない形に（手元の再現 4.3→1.2 秒・PR #683）。次：合併後に本番の lcp.py。
- 2026-10-31 r3 hr33：本番の LCP 中央値 4.6→1.14 秒（lcp.py 3 回、PR #683）。HTML を分ける案Aは不要。ux_check --fast ✗ 5 件は先頭の写真が置き場に無い版面（photo_store の続き）で今回と無関係。次：photo_time.py で最初の写真の届く時刻。
- 2026-10-31 r3 hr33：入口 docs/index.html が止める font link のまま本番に残っていた（入口は24時間おきの作り直しで、source を直しても古い出力が残る）。welcome.build_if_stale が止める link を見つけたら作り直す形に、render.blocking_font_links＋tests/test_perf.py が生成済みの入口と docs/home を数え、ux_check が本番の入口＋本体 4 頁を数える。次：合併後に本番で入口を確かめ。
- 2026-10-31 r1 hr35：縦長写真のぼかしをやめた（F-16・案A）。_pic は img.bg を出さず、hero・lead・wide は枠を写真の幅に絞って空いた横に同じ版面の次の記事（.nx）。手元の本番データで img.bg 0・大きいカード 10 枚が絞られ・1400 の見た目を確認。次：合併後 ux_check と 390px、小さいカードの余白。
- 2026-10-31 r1 hr35 続き：#689 合併後の ux_check が「枠を絞っていない大きいカード」を数えた（本番 3〜9 枚）。根：2 回目の load・resize で絞った枠のまま比率を測り r≈1 で絞りが外れた。unnarrow で元の枠に戻してから測る形に。手元で 0 を確認。
- 2026-10-31 r1f1 hr35 続き：縦長の段の残り半分。小さいカード（c3・mini・wc・tape）と気になるかも pk も、写真が枠より細いとき枠を写真の幅に絞り字の列を横に置く（FIT_JS side・.sb）。390px は大きいカード 1.6 倍・pk 1.5 倍まで。ux_check に gap（全部のカードで空いた横 25% 超）。手元で本番の中身に当てて 1400：11→0・390：8→0・768・1024：0。次：合併後の ux_check（test-a/b/c）。
- 2026-10-31 r1f1 hr35 続き 2：#691 合併後の本番 ux_check で test-a 390 に「空いた横」6 枚（大きいカードの枠が絞られないまま。手元で resize を送ると 0＝読み込み時の測り漏れ）。FIT_JS に ResizeObserver・MutationObserver・load の capture を足し、隠れた版面・あとから足された写真も測る。
- 2026-10-31 r1f1 hr35 続き 3：#692 合併後の本番 ux_check（test-a・test-c × 1400/390）で「写真の余白」0。残る ✗ は test-a の「先頭の写真が置き場に無い版面」（別件）。縦長の段は済（実機は未了）。
- 2026-11-01 r2 hr35：公式サイトの人物の絵を主な手段に（規則：名前の長音の書き方を同じ人に・一覧ページもたどる・Fandom 由来を出どころの網域でも数える）。店長の 12 の character 版面で公式の絵が取れるのは BLEACH MH だけ（4/39 → 取り直しの対象 Renji・Tōshirō が E21 に出る）。次＝後台の取り直しを本番で見る。
- 2026-11-01 r2f1 hr35：公式サイトの人物の絵の続き。本番 run 41223765473 で Renji・Tōshirō が公式の立ち絵に替わった（BLEACH の公式 4/39）。Rukia・Kisuke が名簿に戻らない根＝公式の候補の source「公式サイト」が AUTO_SOURCES['character'] に無く毎回外れていた＋回す順の rotation で先頭から外れていた。直した：AUTO_SOURCES・Fandom より先に選ぶ・subjects で欠けた主役と公式のある人を固定（STEP の半分まで）・official_key にヘボン式/訓令式と m/n・E21 を ✗（いない人も数える）・E27 情報（公式の HTML から人物の絵を読めない版面）。店長の 12 版面のうち公式の絵が読めるのは BLEACH だけ・JS で描く公式 6 版面は未対応。次＝本番で Rukia・Kisuke が戻り E21 が 0 になるのを確かめて [x]。
- 2026-11-01 r2f1 hr35 続き：#696・#697 合併。NAMES_V 13 で失敗の待ちを解き、本番の後台で Rukia・Kisuke が公式の立ち絵で名簿に戻った（41 枚）。E21=0。次＝JS で描く公式 6 版面（E27）。
- 2026-11-01 r2f2 hr35：別の目の指摘（お客さまの版面が未計測・JS 描画・Marvel の各人のページ）を規則で。①library_emblem.official_swap_board（入口は店長と同じ official_cut）＋E21 が boards.config も数える ②official_person_images（一覧が名前だけ→その人のページの cut/og:image）③JS 描画は本物のブラウザの HTML（Astrae Oratio は playwright で 2 枚取れると確認）④wiki 網域のアイコンを公式にしない（ぐでたま）。本番の数：店長 E21=0・お客さまの版面（見える 23）E21=0・E27=5（GTA 6・あつ森・绝区零・dota2・Astrae〔ブラウザで解消見込み〕）。次＝合併後 ux_check と 1400/390 で /home/ を確認。
- 2026-11-01 r3：ログインの札 561〜760px を右下の「⋯」メニューに（#701）。本番 700/1000px で確認、ux_check --fast の札の ✗ 0（残る ✗ は先頭の写真のみ＝別の段）。次＝≤560・PC と揃えるか見本で聞く。
- 2026-11-01 r3f1：「⋯」の点検の穴を規則で。ux_check に札の境目（guest・test-a・test-b × 390/560/561/700/760/761/1000、既定・--fast とも走る）＝幅ごとの見える子・「⋯」の開け閉め・しまう動き。開いた「⋯」を下へ読むと札ごとしまう壊れ方（点検が検出）を render.py で直した。手元の同じ部品で 21 回 ✗0。次＝本番で確認。
- 2026-11-01 r3f1：#702 合併・本番で札の境目 guest・test-a・test-b × 7 幅 ✗0（ログイン中は me.html へ移り終わるまで待つ直しを追加）。次＝幅の境目の部品を既定の回に（BACKLOG 【同じ考え】）。
- 2026-11-01 r3f2：札の点検の穴＝他のページ。ux_check の札の境目が home/ の他の 6 枚も開く・tests が札のある全ページの CSS と守りを数える。同時に先頭の写真の ✗（dota2）の根を規則で＝render._pic の落ち先 data-fb も置き場の写真を先に。PR は合併後に記入。次＝✗ の文に根の網址を添える。
- 2026-11-01 r3f2：#704・#705 合併。本番 1400 の先頭の写真の ✗ 0（dota2・Vaundy 消えた＝落ち先は置き場の写真に替える）。札の点検は他の 6 枚（guest 700px の admin 含む）も ✓。guest の E2 読めない 10（403）・E1 三星手机 は別の段として BACKLOG に。次＝E1・E2。
- 2026-11-01 r2：依頼の係。段 9（公式の立ち絵）を [x]：E27 の 4 版面は規則の「公式にいない人は今までの取り方」で決まり。本番 ux_check guest --fast の ✗ は dota2 の頭が写真なし・Vaundy の先頭が届かないのみ（既知・別の段）。photo_time 390px 0.5 秒超え 0。次＝Vaundy の先頭の写真。
- 2026-11-01 小元素のはみ出し・立体 案 A を本番へ（r1・依頼の係）：render.py の .emb（--r .15・右へ 6px・墨の硬い影 4px＋ぼかし・写真は 0.82 倍 +5°）と EMB_JS place（帯の高さを測って --s 最大 1.15・--lift）。390px で帯の中に収まっていた（はみ出し 0 未満）を 5〜26% に。ux_check emb_check E28。次：合併後の本番 ux_check
2026-11-01 r1: 小カードの切る位置を顔・題字の分布から決める（photo_store m・cropAt）。PR #708。本番 m 1500 枚・ux_check guest 1400 は dota2 のみ ✗。次: 他の小カード・スマホ。
2026-11-01 r1f1: 切る位置の規則（cropAt）をスマホ .pk・c3・mini・wc・tape・主写真へ。data-m を全部の写真に・pkcut を全部の .fill に。テスト 1135 OK。次: 合併後 ux_check と 390px の確認。
2026-11-01 r1: Wikimedia への直リンクの小元素 10 件（三星手机ほか）を倉庫へ置く規則 localize_remote。PR #713。本番 guest ux_check で E1・E2 なし。次: E4 Pochita 85px（全身の絵の下限）。
- 2026-11-01 r2：ux_check E4（Pochita 85px）＝_body_len のしゃがみ見積もりを 1.4 倍までに。PR #714。本番 guest 1400 で E4 0。次：周杰伦の先頭の写真（photo_store 待ち）
- 2026-11-01 r3：ux_check 残り（先頭の写真が置き場に無い）の根＝render のあと写真の一時保管を起こさない → render.yml に `photo_store.py --todo`＋起こす段・test。次：合併後 photo_store の回が起きたか・guest ux_check で picks の ✗ 0 を確かめ。dota2 の頭（17173 取れず）は残り。
- 2026-11-01 r3f1：#716 の連動漏れ＝収集の回〔digest.yml・background.yml〕の発布に写真の一時保管を起こす段が無かった→`photo_store.py --kick` に共通化し 3 workflow に足す・tests/test_photo_kick.py（render を呼ぶ workflow を数える）。次：合併後 collect の回のあと photo_store が起きたか確認
- 2026-11-01 r1：ux_check「写真の余白」を全候補（1,394 枚中 約 130 → 1,374 測定）で数える形に（GAP_JS・読めない 25% 超は ✗）。本番 guest 1400/390 とも bad 0。次：②人ごと・ページごとに分けて 1 回 500 秒以内（BACKLOG の ux_check 再走の段）
- 2026-11-01 r1f1：ux_check の loose・pkcut・pkv も全候補を読み込んでから数え、測れた割合 75% 未満は ✗（PR #720）。本番 guest 1400 ✗ 0・390 は pkcut 1（A2O LITE c3、BACKLOG に段）。ログイン中は未確認。次：その c3 の規則、ログイン中の確認。
2026-11-01 r1f2 ux_check pkcut: FIT_JS 枠の比率を小数の箱で測る（整数丸めで境目 fill）・ux_check 再試行・測れた割合 0.9。次: 本番で 4 人×2 幅
- 2026-11-01 r1：スクロールで写真が出ない＝load を window で聞いて .ld が付かず 3 秒透明の根を document に（#723）。本番 390 の 0.3 秒以内 33→100%・1400 58→100%・ux_check guest に新 ✗ なし。次：②カードの空白の作り直し
- 2026-11-01 r1b：ほかの注目ニュースの壁を中身の高さで詰める〔升目で背をそろえて下が空く根を規則で〕・#725。本番の壁のカードの空き 0（前 1400 で 441px）・ux_check guest に HOLE_JS・✗ は既存の dota2 の頭だけ。次：気になるかも・テープ・お客さまの版面にも空きを数える
- 2026-11-01 r2：ux_check を人×幅の回に分ける harness/ux_all.py（#727）。--fast guest,test-c が 5 回・2 分未満で完走（未完走 0）。残る ✗ は dota2 の頭の写真のみ（別の段）。次：全部の点検を ux_all で通しで測る
2026-11-01 r1f2 PR #724 合併：pkcut 0（原因＝整数丸め）。本番 ux_check --fast guest/test-a/b/c × 1400/390：✗ は guest の dota2 頭 nohead 1 のみ（BACKLOG に段）。次：代用画像の頭落ち
- 2026-11-01 r1f1：版面の中の .grid〔滑雪の例〕を中身の高さで詰める〔右の記事を升目の 1 段ずつ・大きい記事は段をまたぐ・横長の主写真は写真の形〕・#728。本番の滑雪 1400：上の段 561→507px・下の段の始まり 609→555px・色の帯なし。ux_check に gridHole。次：ILLIT 型（縦長の主写真）の 84px の空き
- 2026-11-01 縦長の主写真（ILLIT 型）の空きを規則で直す・gridHole の緩めを戻し .pkgrid と 2 記事の並びも測る（r1f2）。ILLIT 空き 0（1400・768）・気になるかも 0。残り＝テニス 53px・星巴克 67px（次の段に足した）
2026-11-01 r1: Pages 公開を Actions の pages.yml に（#735）・dispatch で build/deploy success・次＝ユーザーが Source を GitHub Actions に切替→continue-on-error を外す
2026-11-01 r1f1：Pages 別の目の指摘〔#736〕：harness/pages_health.py〔標準の回が残る＝Source 未切り替え・24h 失敗 8〕・空振りの公開 2 つを外す・試験を両方向に・後台の提交を畳む。本番 ux_check guest --fast の ✗ は記事の並びの空き 2 件〔テニス・マグカップ、docs 無変更で別の段〕。次＝ユーザーが Source 切替〔BACKLOG [?]〕→continue-on-error を外す

- 2026-11-01 r2f1：版面の記事を積み上げ（mason）に #737。本番 ux_check --fast guest・test-a/b/c × 1400/390 すべて ✓。次＝mason 外の並びの空き。

- 2026-11-01 r1 まとめの段 第 1 部：L7 次のニュースの二重を直した（#743）。本番 33→0（1400）・18→0（768）。ux_check に二重の点検。次＝割り当て 1 か所・カード/器の統一・方向案の審査待ち

- 2026-11-01 r1f1 L7 ページ全体：トップに出た記事を版面から外す＋once（.dupd）で予定・次のニュースとの二重を畳む。ux_check sameStory をページ全体に・実際に描くテスト追加。本番 1400px 12・390px 7 組から 0 へ（合併後に確認）。次＝割り当ての 1 か所化の残り（気になるかも）
- 2026-11-02 r2f2：mason 外の穴の本体＝過去のニュース〔.older〕の固定の行〔23 並び 10〜20%〕を mason で積む #740・.sb の行の隙間 #742。本番 ux_check の結果は返答。次＝768 テニスの右の束・店長ログイン点検。

- 2026-11-01 r1f2 L7：気になるかも（.pk）を対象に（#748）。本番静的 HTML .pk 71 件・重なり 0。ブラウザ不可で 1400/390 は未確認。次＝ux_check test-a の先頭写真なし 7 件の原因調べ。- 2026-11-02 r2：L10 次のニュース(.nx)を押すとその記事へ行く（#750）。pointer-events の例外に .nx a。実ブラウザで前=主記事の網址・後=次の記事。本番 test-a 1400/390 の ux_check wrongLink 0。次＝写真の主役を測らずに切る 7 枚（test-a 1400 の ✗）は L9 の段。
- 2026-11-02 r2f2：本番 ux_check の残りを #745 #749 #751 で直した〔.sb の行・toggle・mini c6〕。gridHole ✗ なし。残り＝pkcut の回ごとの ✗・768 テニス・test-a の置き場 7〜10 件。
- 2026-11-02 r3f1 L8 残り：.burst を枠の内側・.wc .tg をカード先頭の流れへ（#756）。本番 390/1400 札×字の重なり 0。badgeOver を絶対配置の札すべてに。次＝.pk 写真が細い 4 枚・test-a 先頭写真 6 版面。
- 2026-11-02 r1：ログイン中の役割の札を店長だけに〔render.AUTH_JS 1 か所＝右上・メニュー・スマホ共通〕。tests と ux_check E-rl を追加。次＝合併後 test-a〜c を 1400/390 で確認。
2026-11-02 r2 お客さまの版面に motif・like_fx を写し仮の主題を付けた（#759・tests 1190 通過）。次：41 版面の AI デザイン・本番で m- class の点検
- 2026-11-02 まとめの段（r1）：testground/layout-v2 に全体見本（3 方向・7 か所・本物のデータ）。1400/390 で横はみ出し 0。次：ユーザーの方向選び
- 2026-11-02 r2f1 ux_check に「m- class のない素の版面 0」(plain) と tests 全 type 5 種を足した。店長の本番 23 版面は全部 m- あり。次＝test-a〜c 本番確認・41 版面の AI デザイン
- 2026-11-02 まとめの段 第二版（r1）：layout-v2 に もっと見る全部開く・左の目次・小元素の帯・768 目視。3 幅 × 3 方向のスクショで横はみ出し 0、文字だけカードの穴を文字パネルで埋めた。次：ユーザーの方向選び・写真 URL の重複を割り当てで
- 2026-11-02 まとめの段 第二版の点検（r1f1・PR #762）：harness/layout_v2_check.py と tests 9 本を足し、数えたら もっと見るの格子の穴 7 か所・猫用品の主写真が絵文字・同じ写真の二度出しが出たので規則で直した（12 の倍数＋余りは一覧・絵文字は写真にしない・写真は中身で 1 回）。1400/768/390 で点検 OK。次：ユーザーの方向選び→入れ替え
- 2026-11-02 r2f2 ライブラリ 64 版面すべてに motif・theme（41 版面に AI のデザインの回）。library_design.py・ux_check「デザインのない版面 0」を足した。次＝合併後 ux_check 完走・E6/E10/E15/E16/E24

- 2026-11-02 r1 ユーザーのページ＝店長（#764）：ux_check --diff-admin。話題度を店長と同じ heat.compute・目次は板块が多くても駅を 1 つ（render ①b）。本番 test-a 1400 で違い 0（欲しい物・👍👎・気になるかも？・予定の 7 件は△で次の段）。次＝👍👎を本人の account で feedback へ
- 2026-11-02 r1f1 ユーザーのページ＝店長 ②（#765・#766）：👍👎を本人の account へ（my_vote_add・my_votes_own、本番で test-a の票が u_ 行・test-b/店長と混ざらない・guest 拒否を確認）・気になるかも？を本人の票と版面の載らなかった記事から・過去の号も渡す。本番 --diff-admin：test-a/b/c × 1400/390 で ✗0（残り＝欲しい物 2 件は [?]、予定・もっと見るはデータ待ち）。次＝欲しい物の置き場（ユーザーの答え待ち）・お客さまの版面の AI 編集
- 2026-11-02 r2 小元素の顔の大きさ：表示した顔の px を型ごとに測る〔emblem_face.shown_face_px・emb_check E29 情報〕。店長 283 枚：胸像 50px 前後でそろい、全身 8〜86px・上半身 11〜58px がばらつく。基準 3 案を testground/face-size.html に出し BACKLOG を [?]。次＝答えで CSS と E29 を ✗ に
- 2026-11-02 r1：顔の大きさの審査 1 段目（394 枚を 4 分類で並べ押して直す・保存は review_save→review_answers）。PR #770。確かめ：1400/390 で押す→保存・本番 200・ux_check の ✗ は既存の E10/E15/E24 で今回と無関係。次：店長の答え待ち→2 段目
- 2026-11-02 r1 依頼の係：写真の配信止め ①② — 点検のブラウザを harness/browser.py の launch に 1 本化（*.supabase.co/storage/ は写し/灰色で返す・配信を測る 3 本は WL_ALLOW_PHOTOS=1 のみ）・直接 chromium.launch を拦める tests/test_browser_guard。tests 1223 通過。次＝③毎日の見張り（管理ページ・150 MB/日 Discord）
- 2026-11-02 r1f1 写真の配信止めの続き（#774）：urllib の storage 読み・Playwright MCP・JS も止め、写しは読む時に作る（state/photo_cache 1097 枚 46 MB を 1 度）。tests 1228 通過。ux_check 本番：guest/test-a は走った分で ✗ は E4・E10・E15・E24・heat 札重なり（E4・heat 札は写真と無関係に見えるが基準未確認）、完走は 15 分超。次＝③毎日の見張り（管理ページ・150 MB/日 Discord）と ④24 時間後のログ実測
- 2026-11-02 r1 依頼の係：無料枠の残り出どころ #777 — HARNESS に「その場も launch」1 行・workflow が playwright 直起動しない点検（0 件）。確かめ：全 1229 テスト OK・CI 緑。ux_check は写真を読む本番ページを開くので今回は回さず（段の決まり）。次：pages.yml（案A 2 段目）、毎日の見張り。
- 2026-11-02 r1f2 写真の配信止めの続き（#778）：ux_check.server_opens が止めの RuntimeError を except Exception で飲んで常に「開けない」と判定していた（E4 の偽の ✗ の原因）→ storage 網址は storage_bytes 経由・RuntimeError は再送出。layout_sample.photo_key の requests.get も storage は写しだけ。tests に飲み込み・直接 urlopen の数え点検。全 1229 テスト・CI 緑。本番 ux_check は 9 分で打ち切り（guest 1400 のみ完走：E4 は出ず、E10・E15・E16・E24 の ✗ は写真と別）。次：ux_check の完走時間（15 分超）を縮める
- 2026-11-02 r1f1 無料枠の別の目の指摘：係が使うスキル webapp-testing（SKILL.md＋examples 3 本）が chromium.launch を直接教えていた→ launch(pw) に書き換え・skills-lock に localPatch。test_no_direct_launch の走査に .claude/skills の *.py・SKILL.md を足し（前は 0 件と数えていた）、同じ壊れ方を数える。連動の範囲 4 件。次：pages.yml（案A 2 段目）。
- 2026-11-02 r1 依頼の係：無料枠・写しの空を本番で埋め直す漏れ — 写しを ~/.cache/wl_photo_cache へ・FILL_MAX 既定 0・photo_cache.yml（1 日 1 回）・tests NoFillByDefault。確かめ：手元のテスト（PR の CI）。本番の写真を読むブラウザは回していない。次：Pages への移行（ユーザーの Source 切り替え待ち）。
- 2026-11-02 r1 依頼の係：#782 合併。photo_cache.yml を手で起こすと 20 分で切られた（逐次 DL）→ 12 分の時間上限を足した（cache は保存された）。ux_check は本番の写真を読むため回していない。
2026-11-02 r1f1 Python 側 storage_bytes/head を写し無しは None に（PR #784）・photo_cache 手動実行 success（2509 網址・残り 311）・ux_check は係の写しが空で灰色の ✗ 多数（実害か未判別）・次: ux 用に cache を読む回
2026-11-02 r1f2 ux_check の写し空＝「測れず」（✗ にしない）：server_opens None・nohead_real・pkcut/pkv/余白/loose/tiny を blind で飛ばす・tests/test_ux_blind.py。確かめ：手元のテスト。次: 係の写しを埋める・settings 素の箱 1 件の切り分け
2026-11-02 r1f2 続き：写しが空のとき、灰色が引き起こす差し替え（一時保管の枚数・DOM の先頭の写真・版面の頭）も「測れず」。guest 1400 が ✓ に（残るのは heat の札重なり 33＝実害の疑い）。
- 2026-11-02 r1 依頼の係：free-tier.md 決まり 2 を「ハーネスの見回りが query_logs で毎日数える」に書き換え（sbp_ トークンは Actions に置かない）。コード無し。次：写真を Pages へ移した後に管理ページ表示を見直す。
- 2026-11-02 free-tier 決まり 2 の続き：BACKLOG 旧文（「配信の見張り」の札）を直し、sbp_ を workflow に置かない点検を [ ] で足した。docs のみ。次：その点検の unittest。
2026-11-02 r1 並べ方の見本を「今の本番／新しい並べ方」の前後に作り直し（scripts/layout_ba.py・layout-v2.html・3 方向は外した）。数字：穴は ほかの注目 23%→0% のみ有意・中が空いたカードは増える所あり。次: ○× の答え待ち→欲しい物→製品の先頭の見本。
2026-11-02 r2 欲しい物・製品の先頭の見本 PR #793（wishes.html・product-head.html・審査待ち）。次＝答え待ち
2026-11-03 r1 緊急 402 の縮退 (2)(3)(4)(5)：SB_DEG_JS（全ページ・入口）・sbstate（Actions は 402 で飛ばして続行）・管理ページ 1 行・sb_down_check（abort／402 とも 1400/390 全部 OK）。PR #796。次：本番で確かめ → (1) の別の係の分と合わせて閉じる
- 2026-11-03 休止モードの続き（#799）：入口が #796 のあと古いまま SB_DEG 無しだった根を規則（render.with_sb_deg・入口の作り直し条件・tests が docs/ を数える）で直し、本人の殻・見本の審査にも。live_log 溜め置き・user_pages 指紋・見回り間引き。本番 abort で 16 ページ OK。次：24h 後のログで回数を測る。
2026-11-03 r1f1 sb_down_check の ✗ が出たり出なかったり（me.html 1400）＝固定 3.5 秒待ちで、殻から ./ へ飛んだ先の読み込みの呼び出しが「押したあと」に数えられた。落ち着くまで待つ settle・呼ばないページは 1 回呼んで案内を確かめる・休止にならないなら ✗。アプリ側の漏れなし（殻はログインなしで Supabase を呼ばない）。次：本番 1 回・24 時間後に Supabase ログ
2026-11-03 r1f1 egress (1) ④：本番 5 ページ 写真 184 件 Pages 100%・storage 0・query_logs 45 分 0 件。/p/ の 404 10 枚の根（新しい写真は取り込み前）を photo_cache の追従で直す・見本の storage 直書きを /p/ に・pages_served.py と tests。次＝マージ後 photo_cache 起動→404 0 を確認
2026-11-03 r1f2 sb_down_check：呼ばない 4 ページ（face-size・layout-v2・wishes・product-head）は probe 後 hits.clear() で案内 1 の点検が常に偽＝漏れ。probed 旗で案内 1・dataset.sb=down を assert、tests に固定（#805）。手元 16 ページ×1400/390 全部 OK。次：本番で 1 回・ux_check・24h ログ数え

- 2026-11-03 r2：休止モード③④ #806（library 系の 402 緑終了・読み取りの使い回し）。CI 緑・合併。確かめ：全試験 OK。次：24 時間後に nav_schemes 等の回数を数える。
2026-11-03 r1f1 ux_check の止めが pages 箱まで灰色にしていた（ログイン後 12 件 ✗ の根）を直す。確かめ：✗ 12→3（別の件を BACKLOG へ）。写真の 404 10 枚は photo_cache 追従＋再 render で 0。次＝残り 3 件
2026-11-03 r1f2 egress ④ 続き：#812＝はじめに版面の主題（user_pages motifs）・気になるかも 5 枚未満の穴（CSS :has）・pages_served --who。本番ログイン中で /p/ 404 251（写しが docs/ の html だけ見て pages 箱の写真 1,194 枚が漏れ）→ photo_cache_fill が photo_store の全部を対象に。次：合併→photo_cache 1 回→--who と ux_check を本番で・24h の egress。
- 2026-11-03 気になるかもの穴を 761〜1200px（2 列）にも規則で（r1f1）。札が全部で偶数枚の大きい 1 枚＋小札、.row が奇数枚で最後の行の右が空いた→最後の 1 枚を 2 列に。tests/test_pkgrid_fill を 5 幅（1400/1200/1100/900/761）×1〜9 枚×(.row) に広げ穴 0。本番の /home/ がその枚数・幅になるかは ux_check で。次：ux_check の gridHole を 1100px でも
- 2026-11-03 r1：pages_served --who 再測（本番 1 回）Pages 95.8%・storage 19・/p/ 失敗 0＝19 件は全部お客さまの版面の小元素（emblems 箱）。#818：user_pages が旗 on で /p/ に書き換え・ux_all に全体の持ち時間 540 秒。photo_cache は anon で名前 0 件→ service key で読む（続き）。次：写しが埋まり user_pages→pages のあと pages_served --who 1 回で storage 0
- 2026-11-03 r1：#818〜#821 ログイン中の写真・小元素 Pages 100%・storage 0・/p/ 失敗 0（本番 pages_served --who 1 回）。小元素 660 種を写しへ（3 つの根を直した）。ux_all --fast は 9/9 ✓（global の SystemExit と順番を直し、--only で続きを走らせる）。次：定時の photo_cache が毎日お客さまの小元素を足すこと・24 時間後に storage egress の数え直し
- 2026-11-03 r2：photo_cache 取り込み後の pages_served --who test-a,test-b,test-c（本番 1 回）＝455 件 Pages 100.0%・storage 0・/p/ 失敗 0 ✓。ux_check 時間切れは ux_all（#822）で解消済みを確認。次：24 時間通しの egress を 11/4 01:30 UTC に query_logs で数える。
2026-11-03 r2f1：egress 小さい係 ①②の続き（#824＋本件）管理ページ小元素 pg()・候補写真も pg()。docs/ の storage 網址 0（data-fb 除く）。boards の小元素名 660＝manifest の小元素 660（DB 数え・MCP）。boards 64 件に photos 箱の画像 0。tests 1288 OK。次：24 時間通しの egress を 11/4 01:30 UTC に
2026-11-03 r2f2：egress ①② 別の目の指摘を直す。小元素名の集合を md5 で突き合わせ（DB 660＝manifest 660・⊆ 証明）、boards/board_stories の非小元素 storage 網址 0 を pages_health --emblems と photo_cache.yml の毎回の点検に。/p/ 名は docs 2715・store 5224 とも manifest に全部ある。次：本番 ux_all --fast を 1 回。
2026-11-03 r2f2：#826 合併後 本番 ux_all --fast（test-a/b/c × 1400/390 ＋ global）7 回 ✓・✗ 0・未完 0。前の /p/ 失敗 14 は再現せず。次：11/4 01:30 UTC の egress 数え直し。
2026-11-03 plan1：計画。egress 24h 数え直し・11/5 朝の本物の 402 確認・heat.html 札・小元素 E10/E15/E24 を型で・ほかの注目の空白を店長と同じ部品に、の 5 段を BACKLOG に足した（product-head の Switch 2 補足は既にあり）。次：11/4 01:30 UTC の数え直し。
2026-11-03 f1：heat.html の「札が字に重なる」（1400＝43・390＝80）の根は話題度グラフの字 .cl どうしの衝突（等級名×右端の値・最初の日×7 日おきの日・縦軸 0×横軸）。_chart で規則化し局所描画で 0/0。PR 本件。次：合併後 ux_check 1 回
2026-11-03 f2f1：E24 の続き（PR #830 の指摘）：reject_srcs(item, bad) に 1 回だけの記録 emblem_small_tried（店長もお客さまの config も。取り直しても外れたら 2 回目で reject）、processes.py の owner 札の kind を戻し bust に文を移した、お客さまの split_closeups も同じ道、E24 は stale_narrow_rejects で店長＋boards.config を数える、tests は道 4 つを実際に走らせる。次：合併後 ux_check、E10・E15。
2026-11-03 f2f2：E24 が 18 のまま（background 41603590213 は gate が「仕事なし」で小元素の段を飛ばした）の根＝解く入口 release_small_rejects に着く番 due が、そろった・失敗で材料が同じ版面を飛ばす。due に stale_narrow_rejects を足し tests。次：合併後 background を dispatch し E24 を数える
2026-11-03 f1：お客さまの「ほかの注目ニュース」の空白＝確認のみ（店長と同じ _front＋WALL_JS・本番 ux_check test-a/test-b 1400/390 の壁の空き ✓・test-c は壁なし）。コード変更なし。E24：background 41607700962・41609761853 とも success（f2f2 が確認の続き）。次：E15→E10（f2f2 持ち）。
2026-11-03 f1f1：壁の空き＝#834 の [x] を [~] に戻した。根：HOLE_JS が壁の中の列の底しか見ず、壁が右の列より低い空き〔カード 2〜4 枚〕を数えず、写しが空では写真の形も出ない。手元の画像で形ごとに測ると 10 中 8 組が右の列と 12〜30% 差。FIT_JS wall が差 6 割までは写真枠を右の列の高さまで伸ばす・ux_check sidePct・tests/test_wall_shapes.py。確かめ：テストは直す前 8 組 ✗・直した後 全部 ✓。次：写しのある環境で test-a 1400/390。
- 2026-11-03 f1：E24 確認＝background run 41607700962 成功・main の narrow_small_rejects()=0。ux_check は回線切れで測れず。次：E15→E10。
- 2026-11-03 f1f1：E24 の [x] を [~] に戻した（別の目の指摘）。店長 narrow_small_rejects()=0 は再確認、版面側は DB 64 版面のうち縮めた札のある 21 を同じ関数で数えて 1 件（原神 Xiangling）。library_emblem.yml は #832 のあと未実行だったので dispatch（run 41626091935）。画面（ux_check）は未測。次：その run のあと版面側を数え直して 0 なら [x]（データ側のみ・画面未測と明記）。
- 2026-11-03 f1f1：E24 データ側 [x]：library_emblem run 41626091935 のあと店長 0・版面側（DB 64 版面の縮めた札 21）0。画面 ux_check は未測。次：E15→E10。
2026-11-03 plan1：次の段 4 つを BACKLOG に足した（Pages 公開物 1GB／月帯域の見張り・Actions の応答バイト数え・test-c 最初の画面の導線・11/4 本番ゲート 1 コマンド）。コード変更なし、架構図：不用改。次：先頭の段から。
2026-11-03 f2：11/4 の本番ゲートを 1 コマンドに（harness/free_tier_gate.py・tests/test_free_tier_gate.py）。架構図：不用改（harness のみ）。次：11/4 に実行して全部 ✓ を確かめる。
- 2026-11-03 f2f1 別の目の指摘：ゲートの穴（--skip-prod が「入れ終わり」と出す・走査が狭い・FILL_MAX 無点検・main 無試験）を直し、Pages 98.3% の根（photo_cache が render 後だけ）を Pages 公開後にも走らせて直す。確かめ：手元の全テスト。本番のゲートは回していない。次：合併後 pages_health --photos を 1 回、11/4 朝にゲート。
- 2026-11-03 f2f2 別の目の指摘（続き）：token 走査が git 管理外の .claude/worktrees の写しを拾う→見ない／docs の静的な data-fb に storage 網址が 1 件残る（render._pic が落ち先に入れていた）→入れない＋free_tier_gate に docs 静的 storage 網址 0 の点検を足した。連動の範囲：docs の html・js 全部（1 件）。架構図：processes.py p1ph に 1 文。次：render 後に gate --skip-prod が全部 ✓ か確かめる。
- 2026-11-03 f3：11/4 ゲート再実行＝全部 ✓（Pages 6076 枚・載る 5416 枚の 100.0%・/p/ 失敗 0・storage 0・sb_down_check OK）。BACKLOG の初回 ✗ を [x]。架構図：不用改（文書のみ）。次：11/4 01:30 UTC 以降の 24h 数え。
2026-11-03 f4：Pages 公開物の大きさの見張り（manifest.bytes・pages_health --size・ゲートに 1 行）。架構図：processes.py p7 に 1 文。次：公開後に --size の値を書く、11/4 01:30 UTC 以降の egress 24h 数え。
2026-11-03 f4b：公開物の大きさの見張りの穴 4 つを直した（ゲートの測れず＝ - ・定時の記録と赤・管理ページの 1 行・manifest.bytes に manifest 自身も入れた）。連動の範囲：見張りを走らせる所 2（photo_cache.yml・ゲート）、tests が数える。架構図：processes.py p7 に 1 文。次：公開後に最初の値を PROGRESS へ。
2026-11-03 f4c：PR #847 合併・本番で確かめ：公開物 225 MB＝1 GB の 21%（pages_health --size ✓）、photo_cache.yml が state/pages_size.json をコミット（Actions 成功）。次：翌日に「前回より」が出るか。

- 2026-11-03 f1f2：E24 版面側を繰り返せる点検に：emb_check が数えた版面数と key の種類（公開＝23/64 は未測あり）を出し、library_emblem の回が service key で全版面を数えて log に「E24 お客さま N 件」。tests 追加。ux_check E24 の画面は未測のまま（Playwright MCP 不通・本番は 1 回だけ）。次：合併後の library_emblem run の log で N を確認→E15。
- 2026-11-03 plan1b 計画の係：段 4 つ＋[?] 1 つ（放置タブの呼び出し・402 から戻る点検・worktree 掃除〔160 個〕・BACKLOG 438 KB を縮める・公開の表を Pages JSON から読む案）。架構図：不用改（文書のみ）。次：各段を取る。
- 2026-11-04 f1 放置タブの Supabase 見回りを止める（SB_DEG_JS の every・4 か所・harness/idle_check.py：1 時間 24 回・2 時間後 0・触れば再開）。次：402 から戻る点検
- 2026-11-04 f1 放置タブ続き：管理ページ（livelog.py 3 本・overview.py 1 本）の Supabase 見回りも every 経由に。tests＝scripts/ 全体の生の setInterval 点検、idle_check＝admin-now を 200 返しで放置（30 分〜2 時間 0）。次：402 から戻る点検
- 2026-11-04 f1f2 放置タブ続き：設定ページ additem.js の loadQueue（setTimeout 自己呼び出し 15/30 秒）を WL_SB.every 経由に（PR #852）。tests＝docs/home/*.js の自己呼び出し点検、idle_check＝設定ページ 30 分〜2 時間 0 回（最初の 1 分 2 回・36 分まで 45 回）。本番 additem.js 反映済み・ux_check ✗ 0。次：402→200 復帰の点検（sb_down_check）。

- 2026-11-03 f2：402 が終わったら自動で元に戻る（SB_DEG_JS recover・sb_down_check --mode recover 全部 OK・outbox 二重書き 0 を tests）。次：11/5 朝の本番 402 の実機確認。
- 2026-11-03 f2f1：recover の抜け直し。見本 6 枚（testground）が古い休止の部品のまま→with_sb_deg が古い版を取り替え、docs/ 全部に function recover() があるかを tests で数える。管理ページ（POST の admin_*・my_role・can_edit）は読む呼び出しと見なされず戻らなかった→READ を広げた。sb_down_check --mode recover を 4 ページ×1400/390 に（入力中は読み直さないことも）、全部 OK。次：render 後に ux_check、11/5 朝の本番 402 の実機確認。
- 2026-11-04 hr72 f1：#855 合併（休止の recover の抜け直し：見本 6 枚＋admin の READ）。本番 sb_down_check --mode recover = 全部 OK（4 ページ×1400/390、admin 6 回→案内 0）。注意：合併直後は Pages が古い admin のまま〔render 再生成の後に反映〕で ✗ が出る→反映を待ってから点検。残り：E15→E10→③WW→④。
- 2026-11-04 f2f2：③の別の目の指摘。壁の試験が CI で skip（playwright 未導入）だった＝赤と緑の差の原因。試験に「右の列 +14 行」と 390px を追加（手元で全部緑 161s）。実写の写しでの本番測定は未（写し空）。次：CI にブラウザ試験を入れる段（BACKLOG）。
- 2026-11-04 f3：11/4 夜ゲート。free_tier_gate = ✗1（Pages の写真 98.6%・80 枚欠け）。根＝photo_cache.yml の cache/save が『Unable to reserve cache』を警告だけで緑のまま終了＝2 回写しが保存されず。保存の確認→別名で再保存→赤、を足す（tests 追加）。dispatch の再実行で 100.0%（6400 枚）。他は ✓（storage 0・sb_down_check 全部 OK・公開物 230MB=21%）。次：合併後にゲートをもう 1 回。
- 2026-11-04 plan2：引き継ぎの休止 recover の抜け直しは #855 で合併済みと確認（bbd9681f は重複・取り込まず）。ci.yml に chromium を入れ skip 数を出力（手元でブラウザ系 27 件 OK）、BACKLOG に次の段 5 つ（skip 0 の門・CI 時間・egress 日別・E10/E15 理由別・製品の見本補足）。次：E10/E15 の理由別。
- 2026-11-04 f1：E10・E15 の理由別（別人 143・顔なし 85・何人も写る 66・出尽くし 約 230／E15 は別人 10）。別人の 134/143 は実写 3 版面。基準の写真案は #14 と食い違うので [?]。emb_check に理由の行を足した。次：④製品の見本の補足。
- 2026-11-04 plan1 計画: 402 通知・sbstate 直書き数え・英語の取り残し・a11y・OGP の 5 段を BACKLOG に足した（PR 本件・次: 各段を進める）
- 2026-11-04 plan2b 計画：BACKLOG に 4 段（402 中の生成物が縮まない端から端の数え・足してから最初の記事までの実測・ログイン中の訪問の Supabase 応答バイトと人数・休止の案内に戻る日）。本番 ux_check --fast guest 1400 ✓（版面 23・記事 1482）、残りは時間切れで未測。架構図：不用改（文書のみ）。次：各段を取る。
- 2026-11-04 f1：Actions の Supabase 直書き 7 か所を sbstate.sb_open に（402 で呼び続けない）。名簿の外 0 を tests が数える。次：egress 24h 数え直し（11/4 01:30 UTC 以降）。
- 2026-11-04 f1f1：photo_store の user_pages()（pages/ を一覧して全ページを 3 時間ごとに取る）を外した。評価：日数での消去は止め上限超えだけ古い順。tests に「非公開の storage 道は書きだけ」「一覧を呼ばない」を足した。お客さまだけの写真は数えなくなる（原寸の落ち先で出る）。次：無料の出どころ（user_pages.py が使う URL を書く）の段。
- 2026-11-04 plan2c 計画：BACKLOG に 4 段（置き場 208→258 MB の増え方・リポジトリ 185 MB と 1 日 226 commit・2 日目の「前回から新しい」・最初の画面の重さの予算）。測り：execute_sql 読むだけ（DB 47 MB 横ばい）。架構図：不用改（文書のみ）。次：各段を取る。
- 2026-11-04 f1：お客さまだけの版面の写真を置き場へ（user_pages→pages/_fp/imgs.json 1 本→photo_store）。pages/ は読まない。tests 通る。次：合併後 photo_store.yml→photo_cache.yml→pages_served --who test-a を 1 回。
- 2026-11-04 plan1d 計画：BACKLOG に 4 段（photo cache の保存失敗が 30 回中 6 回赤・boards PATCH の出所確定・点検道具の本番 REST 読み 0・定時の Supabase 呼び出し見積もり表）。boards の書き込み道は scripts を全読して put_config 以外に毎回変わる道は無し→put_config が変わった鍵名をログに出すようにした。架構図：不用改（診断ログ 1 行）。次：pages_served の確認（render→photo_cache→Pages の後）。
- 2026-11-04 plan1d：#875 の確かめ。pages_served（test-a/b/c × 1 回）= Pages 100.0%・storage 0・/p/ 失敗 0（426 件）。次：PR #876 合併後に ux_check。
- 2026-11-04 plan1d：#876 合併。ux_check --who guest は pages_served が分母 0 で ✗（点検の穴・BACKLOG に段）。他は ✓。
- 2026-11-04 f1：photo cache の赤（30 回中 6 回）の根＝run ごとの 200 MB 保存で cache 枠が満杯。保存前に古い写しを最新 1 つだけ残して削除する 1 手を追加（tests 1 件・processes.py pg6）。確かめ：合併後の photo cache が緑か 24 時間見る。
- 2026-11-04 f1f1：#878 の続き。掃除を毎回・run_id キー 4 名前（連動の範囲 4 件：photo・ask-state・wishlist-http・wd-facts）・失敗は警告・tests/test_cache_keys.py（全 workflow 数え）。全試験 1343 OK。直ったかは未確認（保存が起きた回の要約と 24 時間緑で見る）。
- 2026-11-04 f1f1：#879 合併。dispatch 1 回（run 128）は保存成功。#878 後の workflow_run の回 127 は掃除後も「token has no writable scopes」で保存拒否＝枠だけが根ではない。続き：workflow_run の回は入らなければ dispatch で起こし直す。直ったかは未確認（24 時間緑まで）。

- 2026-11-04 f2：点検の道具の REST 読みを harness/sbread.py に一本化（10 分の写し・件数を最後に出す）。tests/test_sbread.py。次：ux_check 1 回の件数を本番で確認。

- 2026-11-04 f2f2：egress 別の目の指摘。sbread 既定を 10 分の写しに逆転（ttl=0 は photo_cache_fill だけ）・ux_check の版面 config 丸ごと読みを 3 箱に絞る・ブラウザの Supabase 読み（GET＋READ_RPC）も写し（WL_SB_BROWSER=cache|abort|live）・件数の行は --part who でも出る（早い return で出ていなかった）・上限 REST_MAX 12。本番 test-a 1400 --fast 2 回目：python /rest/v1/ 0 件・ブラウザ→本番 23〜38 件（user_login 24 が大半）・写し 295・✗ 0。次：user_login の呼びを減らす・ux_all 全部の合計。

- 2026-11-04 f3：402 の通し点検。harness/fake402_check.py が偽の 402 に Actions の入口 13 本を当て、入口ごとに docs/・state/ の縮みを数える。結果：全入口 終了 0・名簿外の縮み 0。tests/test_fake402.py。次：網が要る入口（digest.py 本体・emblem_fill）を偽 402 で通す。
- 2026-11-04 f3f1：402 の通し点検の穴 3 つを塞いだ。①縮みを JSON のバイト数・要素数でも数える（photo_store.json は 1 行 389KB）②workflow の入口を全部数える点検（名簿に無い入口が赤）で入口 13→25 本、走らせない物は理由つきで NOT_COVERED ③402 を 1 回も受けない入口は赤（受けなくてよい 13 本は NO_HITS に理由）。結果：全入口 終了 0（notify-weekly は webhook 無しで 1＝RC_OK）・名簿外の縮み 0。見つけたこと：repair-images は網の無い所で reports/*.json を 1350 行縮める（402 と別の原因・BACKLOG）。次：repair-images の網なしの縮みの切り分け。

- 2026-11-04 f3f2：402 の通しの最後の穴（収集の本体）。fake402_check に `digest all`・`digest ingest`・`repair-images` を足した（止める口 WL_COLLECT_LIMIT・WL_REPAIR_LIMIT、外の網は閉じたプロキシ）。見つけた本物の穴：repair-images が網エラーで報道の画像を外す（直す前 reports/ 4621 バイト縮み→直した後 0）。images.unusable で直した。本体は reports/inbox 縮み 0。次：photo_cache_fill・pages_health の入口、404 が多い回の門。

- 2026-11-04 f4：ログイン中のページを開くたびの user_login（書き込みつき）を、同意済みなら 1 時間に 1 回までにした（render.py の me.chk）。連動の範囲：user_login の呼び口 2 つのうち開く時の 1 つ（ログイン直後は必ず呼ぶ）。点検：ux_check の「本番への要求 n 件」で user_login が 1 回目だけになること。次：本番で ux_check を 1 回測る。

- 2026-11-04 f1：test_wall_shapes 赤の根＝FIT_JS wall() が 2 列の大きい 1 枚だけの列を伸ばさず、壁 3 枚以上で隣の列が高いと 9% 空いた（生成ページの先頭が .tall でなくなって表に出た）。列に大きい 1 枚しかないときはその 1 枚が伸びる（#890、試験は緩めず手元と CI 緑）。#889 を更新して合併。連動の範囲：壁を持つ全版面（同じ FIT_JS）。確かめ：本番 test-a 1400 --fast で壁の ✗ なし（残る ✗ は先頭の写真が置き場に無い 26 件＝402 で photo_store が書けない件・別）。未：合併後の user_login 回数は ux_check に数える行が無く未測定。
- 2026-11-04 f1 main の CI が cancelled になる根（PR #893）：tests/test_fake402.py が全 28 入口を 1 本ずつ通しで走らせ手元で約 5.5 分（library --refresh/--compare 各 51 秒・digest 50 秒・repair-images 94 秒は網が落ちた状態の再試行待ち）、CI の遅い機械で全試験が 25 分を超えた。→ 通し点検を別 workflow fake402.yml（scripts/・workflows・fake402_check を触った PR で必ず通す／毎日定時／手動）へ分け、入口を作業枠 4 つで並べて走らせ 108 秒に（ci.yml では WL_FAKE402 なしで skip）。photo_store.json の stat 数え直しによる偽の赤を名簿に。合併前後に workflow を手で 1 回回す。次：②#893 に main を取り込む ③ux_check --who test-a --part who
- 2026-11-04 f1 #894（fake402.yml 分離・並列 108 秒、PR 前後の workflow 回し緑）→ #893 を main 取り込みで CI 緑のうえ合併 → 本番 ux_check --who test-a --part who：ログイン中の 2 枚目 user_login 0 回（check_login_once 空）。写真の先頭欠け 35 件は既知の E 系。次：E15 案 B
- 2026-11-04 f1f1 fake402 の待ちを飛ばす：遅い根は「網が落ちた状態の再試行の待ち」（library --refresh の Wikidata 5+10+15+20 秒・repair-images の 1 秒おき再取得など、sleep）。入口を並べただけでは待ちは残るので、harness/fake_clock/sitecustomize.py（time.sleep を 0.02 秒に。PYTHONPATH に足す、点検の中だけ）を入れた。再試行の回数は同じ。108→47 秒（repair-images 94→19・library --refresh 51→1）。全入口 終了 0・名簿外の縮み 0。必須チェックの設定（ブランチ保護）は API が 403 で見えない＝店長に BACKLOG [?]。次：E15 案 B
- 2026-11-04 f1hr83 本番 ux_check --who test-a --part who（1 回・約 10 分）：本番 /rest/v1/ への python の要求 0 件・ブラウザ→本番 75 件（user_login 35＝点検が毎回新しい文脈でログインするため。実利用の 2 枚目ではない）。「ログイン中の 2 枚目」は --part global の中で --part who では走らない＝別に check_login_once を本番で 1 回：user_login 0 回で合格。✗ 2 は先頭の写真が置き場に無い 35 件・E1/E2（既存の BACKLOG 項目）。次：photos を読む道の洗い出し（②）。
- 2026-11-04 f2hr83 photos の読み道：nostorage を urllib だけでなく http.client・urllib3(requests)・curl_cffi の要求点に移し、import を辿る点検で網を使う 34 本を数える。PR #900。確かめ：全試験。次：24h 後 edge ログで取り込み以外 0。
- 2026-11-04 plan1：boards PATCH が edge ログで 18 回×13 バッチ/日残っていた＝library.push_shop の上級 parent_id を毎回 PATCH。返りの parent_id と同じなら書かない。photos の edge ログ：#900 合併後の 21 時台は 0 件（24h 後に取り込み以外 0 を数え直す）。E15 案 B は網で確かめられず #901 のまま。
- 2026-11-05 plan2：①は f1 で済み（user_login 0 回）。②photos の edge ログ：#900 合併後 21 時台以降 0 件（直前は 18〜20 時に 60〜86 件/時）。③は #902。④は網で確かめられず BACKLOG に先の 1 段。BACKLOG に 4 段足した。次：24h 後に photos 数え直し。
- 2026-11-05 plan2：計画。24h の API 呼び出しを UA で分けた（Actions 74%・点検 25%・人 0.5%）。BACKLOG に 5 段（内訳の毎日 1 行・点検の予算・工程またぎの読み・live_* の書き手・404.html）と E 表 1 行。次：依頼 ①boards PATCH から。
- 2026-11-05 f1f2：live_* の書き手を数え直し（live_mark・report・Lines の 3 つ、gate は読むだけ）。report 自身が同一内容を送らない入口に・tests/test_live_writers.py（書き手の表＋回数）。合併前 24h＝status POST 681・DELETE 274・log 558・report 422。#908 合併後 24h の数え直しは 11/6 00:00 UTC 以降。次：数え直して 250/450/200 以下か。
- 2026-11-05 f1f1：E15 案 B 続き。a2olite.world を実際に読んだら SPA（絵は bundle 内）で official_images=[]。根は meta charset の「char」誤検知＋bundle 未読＋artwork 語なし。emblem.py の規則で直し（OFFICIAL_IMG・official_bundle_images）、試験 1 つ足し。YOUNG/HIMEKI/XILI の網址をローカルで確認。次：合併後 library_emblem を dispatch して E15。
- 2026-11-05 f1f1：E15 案 B 続き 2。#911 後も 0 枚の根は「公式が先」が character 限定（group 未対応）。group に拡張・試験 1 つ。次：合併後 background dispatch で YOUNG/HIMEKI と ux_check E15。
- 2026-11-05 f1：E15 案 B 続き 4。公式の候補が strict の本人確認で毎回「別人」（A2O LITE 6 人・漫威电影 1 人）→ official_cands に trust_id（閾値そのまま）。PR #920。次：background dispatch で A2O LITE の枚数・FROM は公式に人ごとの絵なし。
- 2026-11-05 f1 hr93：本 3 ①②③。#922 公開ログからお客さまの版面の名前・scrapling の網址を外す（合併後 library_emblem の log で名前 0・Fetched 0）。#923 古い db/*.sql 7 本に流し直し禁止・pw_setup 行を無効・3 関数の search_path 固定（本番適用・呼び出し確認済み）。ux_check --fast は時間切れ・✗ 6 は前からの写真の件。次：本 3 ④⑤⑥ か E15 案 B。
- 2026-11-05 f1（本 4 第 1 段）：種族・敵の型・物を名簿から分類で外す（emblem.THING_CAT・NAMES_V 14）・E17 をお客さまの版面にも（boards_not_people）。実データ：お客さま 16＋店長 7 版面で外れるのはスプラ 3 の 12・ゼルダ Fairy・モンハン Wyverians のみ（Ganon・Frye・Big Man は残る）。次：名簿の数え直しの回の後で E17 お客さま 0・浦原＝夜一・ゼルダの名簿
- 2026-11-05 f1：#920 合併→后台 dispatch で A2O LITE 2→4 枚（HIMEKI・AYUNE が公式に）。VORA・XILI・MERCI は切り抜きの検査で外れ＝次の段。ux_check --fast の ✗ は写真の一時保管（別の係）。
- 2026-11-05 f1（hr89）：test-a の小元素 0（16 版面）の根＝#883 で photo_cache_fill.board_text が tuple→小元素 0 件→写しから全部消え /p/ 404→枠ごと消えた。直し＋外の小元素も /p/＋次の候補へ＋別人の Commons 写真（Ado）を外す規則。https://github.com/CxElegy/Wishlist/pull/919 。確かめ：photo_cache 717 種・pages_served test-a〜c ✓（消えた版面 0）。ux_check --fast は「先頭の写真が置き場に無い」test-a 33（記事の写真・別件）。次：外の小元素の残り（Commons 18）・記事の写真の置き場
- 2026-11-05 f1（本 4）：#924（THING_CAT・NAMES_V 14・E17 お客さま）合併 → ux_check --fast で全ページ「Invalid or unexpected token」＝#919 の EMB_JS の \n → #929 で直し、本番 home の JS を node で 0 件 ✗。library_emblem の回のあとも boards 148 の名簿に Inklings ＝お客さまの版面は NAMES_V で数え直していなかった → _recount・NAMES_V 15。次：library_emblem を起こし boards 145/146/148 の名簿を確かめる・浦原＝夜一
- 2026-11-05 f1：本 1 ① 共通の scripts/push_main.py（6 回・2^i 秒・--regen を自分の提交に畳む・items.yaml 検査・403 は即失敗）を全 push の道に。依頼は push 後に done。PR #921。確かめ：render 1 回目・background は先を越されて 2 回目で push。次：② photo_store ⇄ render の呼び合い。
- 2026-11-05 f1（本 4）：#933 合併（library_emblem.board_item の _recount・NAMES_V 15）。本番 run 41977651865：ゼルダ 145 の名簿 12→8（Fairy・Old Man など）・モンハン 146 8→6（Wyverians・Hunter）。スプラ 3 148 はまだ nv 14＝回の残り待ち。次：148 の名簿・E17 お客さま 0・浦原＝夜一・ゼルダの名簿の分類（1 作目のものを使っている）
- 2026-11-05 f1（機能 C）：#928 お客さまの版面の小元素を材料が同じでも日に 1 回（RETRY_S）→ 本番 41/41 版面が 24h 以内に試された。#931 収集が board_stories.pending に版面ごとに書き user_pages が先に読む → 本番 0→41 行（pending 482）・2 回目は変わった 17 版面だけ・user_pages 6 人・失敗 0。ux_check --fast は 600 秒で打ち切り、✗ は写真の一時保管 0 枚（手元の写しが空＝測れず・機能 A の分）。次：④ AI 編集の入口。

## コンパクトの前の記録 2026-11-05 18:09（自動）
- 進行中・あなた待ち：
  - [~] お客さまの版面で外したはずの画像が残る（Ado の Alassane_Ouattara は #919 のあとも boards 152 の config.emblem に残った。開始 2026-11-05 15:10 JST・持ち主 f1f1・最終 2026-11-05 15:10 JST） — fill_board が外して 0 枚になった emblem を書き戻さない根。reject
  - [~] （開始 2026-11-05 13:50 JST・持ち主 f1・最終 2026-11-05 14:20 JST・1 本目の PR 本件＝F2・F3・F4①②・F6（refresh まとめ・me.html 12 秒・my_page_path を端末に）・F7。残り F5 話題度・F8・F6 の 2 文書分は次の PR）**機能 B：render.py の機能の壊れ（F2・F3・F4・F5
  - [?] **F4 の残り 2 つ（ユーザーに聞く）**：
  - [~] （開始 2026-11-05 13:54 JST・持ち主 f1・最終 2026-11-05 15:32 JST。[x]①F10 小元素の再試行＝材料が同じでも日に 1 回〔RETRY_S〕https://github.com/CxElegy/Wishlist/pull/928 ：本番 41/41 版面の emblem_state が 11-05 05:3x〜05:43 UTC（24h 
  - [?] **F12 情報源の鍵（ユーザーに聞く）**：Reddit の API（REDDIT_CLIENT_ID・REDDIT_CLIENT_SECRET）と TMDB_API_KEY を Actions の Secrets に入れるか。入れない間は Reddit を止めて 429 で時間を使わない（係でやってよい）。
  - [~] （開始 2026-11-05 13:35 JST・持ち主 f1・最終 2026-11-05 15:20 JST・#933 合併〔お客さまの版面も _recount・NAMES_V 15。本番 run 41977651865 の途中で boards 145 ゼルダの名簿 12→8〔Fairy・Old Man・Merchant・Old Woman が外れた〕・146 モンハン 8→6〔Wy
  - [?] **本物のお客さまを招く前の必須条件：DB の窓口を絞る**（2026-11-05 ユーザー「いまはまだテストだけなので」＝今はしない）。節 3 の一覧（user_leave・user_agree・user_login・user_set_prefs・remember_user・shop_set_password・user_signup の admin 招待・run_now tick・s
  - [~] （開始 2026-11-05 持ち主 f1・PR 本件：live_mark の fetch 遅延・未書込 DELETE 省略・emblem 段 30 秒・rpc 重ね書き廃止・live_log 8 秒。合併後 24h で数え直す）live_status／live_log／live_report の Actions 側の書き手を 1 つ特定して減らす（plan2 2026-11-05、依
  - [~] （開始 2026-11-05 持ち主 f1・PR 本件：A2O LITE に site=a2olite.world・A2O LITE だけ emblem_headv 12（BROKEN_V は上げない）。この環境は a2olite.world に出られない〔proxy 遮断〕ので、合併後 library_emblem を workflow_dispatch で回し、state/ と要約
  - [~] （開始 2026-11-05 14:20 JST・持ち主 f1f1・最終 2026-11-05 14:50 JST）E15 案 B 続き 5：A2O LITE の VORA・XILI・MERCI が切り抜きの検査で外れる根。手元で同じ鎖（rembg→check_whole→save_cut）を回した結果＝VORA は check_whole を通るが save_cut が 420 幅に
  - [~] （同上 f1f1）漫威电影の公式の源：根＝marvel.com/characters の一覧は 48 人だけ（Thor・Hulk もいない）。サイトの地図（sitemap-14〜23 に人物 3467 ページ）から探す・別の版（ultimate・earth-…）は除き、決まらない名前（Captain America・Black Panther）は取らない。手元で名簿の 9 人（Stev
  - [?] FROM の公式の源（聞きたいこと）：公式（mgmplus.com/series/from）は作品の絵 2 枚だけで人ごとの絵がない（sitemap も同じ）。
  - [?] 【店長に聞く】「402 通し点検」を必須チェックにする設定（2026-11-04 f1f1）：fake402.yml は PR で毎回チェック名が出る（触っていない PR は判定の step で飛ばして緑）が、ブランチ保護の API が 403（Resource not accessible）で、必須になっているか見えず・設定もできない。必須でなければ赤でも合併できる。
  - [~] （開始 2026-11-04 14:10 JST・持ち主 f1・#878 合併済み（未検証：合併後の photo_cache は保存した回がまだ無い）＋続きの PR（f1f1）：掃除を changed に関わらず毎回・run_id キー 4 名前（ask-state・wishlist-http・wd-facts も。枠は共有）・失敗は警告・要約に残り合計・tests/test_cach
  - [~] （別の目の指摘後 2026-11-04 f2f2・PR 本件：既定を逆に〔sbread は 10 分の写し・ttl=0 は photo_cache_fill だけ・鍵は JWT の sub〕・版面の config 丸ごと読みを 3 つの箱に絞る・ブラウザの Supabase の読み（GET と browser.READ_RPC）も 10 分の写し〔WL_SB_BROWSER=cache
  - [?] 【E10・E15 の最大の理由は「別人」：実写の版面で基準の写真を小元素にしてよいか】（f1 2026-11-04 聞く）E10（11 版面）の外した 4 理由の合計は 別人 143・顔なし 85・何人も写る 66（残りは出尽くし・重複 約 230）。E15 の 3 版面（漫威・FROM・A2O LITE）は 顔なし〔遠景 20 を含む〕34・別人 15・何人も写る 9＝**E15 の
  - [?] 【E15 の最大の理由は「顔なし／遠景」（A2O LITE の YOUNG・HIMEKI）：アイドルの候補を増やす道】（f1f1 2026-11-04 聞く）根：A2O LITE の候補は YouTube の自動の場面（hq1〜3＝480×360、`emblem_fill.YT_FRAMES`）だけで、ステージの fancam は顔が画像の高さの 10% 未満（＝36px 未満）に写り
  - [~] 【(2)(3)(4)(5)＝PR #796・持ち主 r1・最終 2026-11-03 07:25 JST：SB_DEG_JS・sbstate・管理ページ 1 行・harness/sb_down_check.py。本番の abort 確認 OK（2026-11-03 08:10 JST・16 ページ×1400/390）。続き PR #799＝入口・本人の殻・見本の審査にも SB_DEG（
  - [~] （開始 2026-11-02 09:20 JST・持ち主 r1・依頼の係・最終 2026-11-02 10:30 JST・①②は PR #773＋続き〔urllib の storage 読みも browser.py で止め・写しは読む時に作る・Playwright MCP の --init-page・test_browser_guard が JS と urllib も数える〕。③毎日の
  - [?] 【計画 2026-11-03 plan1b・聞きたいこと】**公開で読むだけの表（nav_schemes・sizes・版面の設定）を Pages の JSON から読む**（DB の形は変えない。読み口が増えるので聞く）。今の egress の大半は「みんなが同じものを読む」API の呼び出し（nav_schemes 507・sizes・boards 459／日）。
  - [~] （開始 2026-11-03 18:30 JST・持ち主 f1f1・最終 2026-11-03 19:30 JST・別の目の指摘で [x] を取り消し：下の「確認のみ」は写しが空の灰色で測った ✓ で、写真の形で出る空きを見ていなかった。f1f1 が壁を写真の形ごとに手元の画像で測ると、壁が右の列より 12〜30% 低い組み合わせが 10 中 8 あった〔HOLE_JS の wallP
  - [~] （開始 2026-11-02 08:25 JST・持ち主 r1・依頼の係・最終 2026-11-02 08:50 JST・1 段目の見本は PR 合併後 https://cxelegy.github.io/Wishlist/testground/face-size.html ：394 枚を 4 分類で並べ押して直す・保存は review_save〔店長ログイン〕→ review_ans
  - [?] （r2 2026-11-02 15:45 JST・PR #793：見本 https://cxelegy.github.io/Wishlist/testground/wishes.html ・ https://cxelegy.github.io/Wishlist/testground/product-head.html を出した＝審査待ち。答えは review_answers〔page=
  - [~] （開始 2026-11-02 13:40 JST・持ち主 r1・依頼の係・最終 2026-11-02 16:00 JST・第三版〔r1f2：dota2 の「画像なし」4 は先頭が 7→16 本に増えた分の比〔4/16=25%・前は 1/7〜2/10=14〜20%〕で壊れではない・本番の札の下の空きは HOLE_JS ②が section.sec の全カードで数えている〕・第二版〔r1f
  - [?] 【依頼・聞きたいこと】（r3 2026-11-02：記事の並べ方〔ランキング〕の変更は範囲が大きいので作らず聞く。入口の会話の指示）**製品の版面は、作っている会社の話を先頭に（iPhone なら Apple）**（2026-11-02 ユーザー：test-a の iPhone の版面のスクショ「iPhone だったら、Apple と関連するだろう」）。今の iPhone の版面の先頭
  - [?] 【聞きたいこと】**お客さまの「欲しい物」の置き場**（r1f1 2026-11-02。「ユーザーのページは店長に従う」の最後の 2 件：目次の「欲しい物」・見出しの「欲しい物リスト」ボタン。店長の欲しい物は wishlist.yaml〔リポジトリ〕と写真の依頼で、お客さまの分を置く所がない＝本番のデータベースに表を足す話なので、作る前に聞く）
  - [?] 【聞きたいこと】**人物の顔の大きさの基準（型ごとの px）**（r2 2026-11-02。下の【依頼】「小元素の大きさをそろえる」の続き。店長の items.yaml の人物 283 枚を今の CSS の式で測った：胸像 156 枚＝顔 50px 前後でそろっている／上半身に切った立ち絵 56 枚＝11〜58px〔中央 32〕／全身 71 枚＝8〜86px〔中央 16〕。ばらつくの
  - [~] （開始 2026-11-02 02:20 JST・持ち主 r1・依頼の係・最終 2026-11-02 02:20 JST・r3 は 60 分書き込みなしで取り直し：今回は testground の全体見本〔layout-v2〕まで） 【依頼】**いちばん先・まとめの段**：記事の並べ方の部品を、考え（DESIGN G・L1〜L10）から**1 つの仕組みとして全部書き直す**（2026
  - [?] 審査待ち（r1 2026-11-02 02:50 JST）：全体見本 https://cxelegy.github.io/Wishlist/testground/layout-v2.html （scripts/layout_sample.py。本物のデータで 今日の場所 7 つ：滑雪・猫用品・チェーンソーマン・ほかの注目・気になるかも・Astrae・BLEACH MH）。割り当て 1 
  - [?] Pages の Source を「GitHub Actions」に切り替える（ユーザーの手作業・2026-11-01 r1f1 別の目の指摘で追記）：`python harness/pages_health.py` が今「✗ Source は未切り替え：標準の回 24h で 100 回以上・失敗 8」と出す（標準の「pages build and deployment」が push の
  - [?] 【依頼】複数の人に配ったときの運用・保守（2026-10-31 ユーザー：「ユーザー視点でこのサイトを複数人に配った時の運用保守もしないといけない。ネット上で情報を集めて何ができるか考えてほしい」）。入口の会話がネットで集め、今の数字と照らした案（**どれから作るかユーザーに聞いている**）：
  - [?] 【依頼】名前・メールを引数に取る公開の関数（anon が実行できる SECURITY DEFINER）を「呼んだ人本人の分だけ」に限る（2026-10-31 r2f1，別の目の指摘）。本番の関数：user_leave(p_name)・user_set_prefs(p_name, p_prefs)・user_agree(p_name, p_version)・user_login(p_na
  - [~] （開始 2026-10-31 17:45 JST・持ち主 r2・依頼の係・最終 2026-10-31 19:10 JST〔r2f2 #680 合併：先頭の点検はお客さま〔test-a・b・c の DOM〕にも当たった。合併後の本番で test-a は先頭 6 件が置き場の外＝render が photo_store の状態より前に作ったお客さまのページ〔render 手動 1 回で 0
  - [~] 【依頼】（開始 2026-10-31 14:25 JST・持ち主 r3・依頼の係・最終 2026-10-31 19:10 JST〔r3 hr31 続き：release_head_rejects は実写なら先頭が埋まっていても札を全部 1 回解く（哈利波特剧集・The Mandalorian の名簿の後ろの人の札）・emb_check E26「実写の札が古い版のまま」〔本番 items.
  - [~] （開始 2026-11-01 17:00 JST・持ち主 r3・依頼の係・最終 2026-11-01 17:00 JST）【ux_check 本番 2026-11-01 r1f2 で見えた】ログインなしの dota2 版面の頭（17173 の png、data-fb に置き場の webp あり）が実行時に .nophoto へ落ちる（1400/390 とも nohead 1）。元の U
  - [~] 外した画像の札（emblem_reject）の見直しを実写以外の版面とお客さまの版面にも（開始 2026-10-31 JST・持ち主 r3f2：根＝due が ok・失敗同材料の版面を飛ばし release_head_rejects に着かなかった→reject_release_due を due に。お客さまの版面は board_item→fill_one が同じ・E26 に boa
  - [~] 【依頼】小カード案 2：.nx（縦長の主写真の横の「同じ版面の次のニュース」）のサムネが 3:2 に切られるのに cropAt を通っていなかった（開始 2026-11-01 JST・持ち主 r1f2）。data-m を引き継ぎ cropAt／残らなければ .whole・ux_check pkcut に .nx・tests。残り：未測定 240 枚は photo_store の回のあと
  - [?] 入口の足に「試験の版（2026-10-19〜21）」と「テストグラウンド」を出し続けるか（2026-10-26：全員に見える入口の足に開発用の 2 つのリンク。初めて来た人は何か分からず、test2 の旧ページ・試作ページへ入る） — 案 A：全員に残す（今のまま。良い点：探しやすい／困る点：初めての人に意味が通じない）、案 B：店長でログインしたときだけ出す（おすすめ：店長は今までど
  - [~] 【依頼】元から小さい小元素（短い辺 <256px、BLEACH 34 枚ほか）（開始 2026-10-27 19:10 JST・持ち主 r3・依頼の係・最終 2026-10-27 19:10 JST）を取り方の規則で直す（2026-10-26 入口の会話・#537 の続き：入れ替えでなく取った時点で小さい画像。ux_check／emb_check E18 が数える）— ①Fandom 
  - [~] 【依頼】名簿の先頭 3 人に小元素がない版面を全部直す（開始 2026-10-29 10:30 JST・持ち主 r1f1・依頼の係・最終 2026-10-29 12:40 JST〔r1f2 続き：#605〕。2026-10-29 r1f1 別の目の指摘：縮めた幅の reject を実データで数える点検 E24 を足した〔harness/emb_check.py narrow_small
  - [~] 【依頼】同じ考えでほかに直せる所（開始 2026-10-26 23:58 JST・持ち主 r3・依頼の係・最終 2026-10-26 23:58 JST。今回は「一部の版面にしか値がない手書きの設定」の点検から。2026-10-26 r3：emblem_rules.sparse_keys＋CLI で洗い出し〔店長 12 項目〕。次：管理ページ・ux_check に出す／要らない値を外す
  - [~] 【依頼】小元素の管理を本番に作る：押して「どうしたい？」を選ぶ（**最優先**・2026-10-25 ユーザー 2 回目：「押して『どうしたい？』を選ぶを優先して実装して」。前：「これは実装していいじゃない、実装した?」→ 決めることは全部決まっている〔下の①②③〕ので見本で止めずに本番へ。いまは見本 testground/emblem-manage.html だけで本番の管理ページに
  - [?] 【依頼】test-a の呪術廻戦に E11「何人も写っている」1（Q55522899-fef6948465.webp 顔 2）と版面の頭が写真なし（2026-10-26 r2 の ux_check）— 一度消えた E11 が戻った。個別に直さず規則で（EMBLEM_PLAYBOOK の型：なぜ戻ったか＝作り直しの回が前の規則で入れ直したか、を library_emblem の記録で確か
  - [?] 【依頼】小元素の「人を足す」（2026-10-25，用户定的：今の人数ではこの版面をカバーしきれないと思ったら、管理ページで足せる） — まず**テストグラウンドの見本** `docs/testground/emblem-manage.html` に足して `[?]` で見せる（見た目の決めごと）。形：版面の欄に「＋ 人を足す」→ 候補の一覧（名簿 roster・emblem_pool
  - [~] 【依頼】（開始 2026-10-29 12:37 JST・持ち主 r2・依頼の係・最終 2026-10-29 12:48 JST）（**DB の許可 2026-10-26 入口の会話**：本番のデータベースは「足すだけ」〔create table・create function・RLS で読むのは is_admin・insert だけの RPC〕なら作ってよい＝ユーザーの決まり「足すだ
  - [~] 【依頼】（開始 2026-11-01 08:00 JST・持ち主 r1・依頼の係・最終 2026-11-01 08:00 JST）小元素は枠からはみ出して立体に（**決まった 2026-10-31 ユーザー：審査待ちの emblem-pop.html「小元素のはみ出し・立体感 3 案」→「案A」＝はみ出し控えめ 15%。390 と 1400 を並べた見本を見て選んだので、スマホも見本の
  - [?] 【点検用の店長アカウント】ux_check の「管理ページの網羅」を毎回走らせるため、強いパスワードの管理者を Secrets（UX_ADMIN_EMAIL・UX_ADMIN_PASSWORD）に置くか、サービス鍵で数えるか — ユーザーに聞く（案 A：強いパスワードを Secrets に置く＝毎回走る・管理者が 1 人増える。案 B：サービス鍵で RPC を直接数える＝管理者は増えな
  - [~] 【依頼】（開始 2026-10-29 12:59 JST・持ち主 r3・依頼の係・最終 2026-10-29 12:59 JST）👍 の演出（イイネ!・飛び散るもの）が画面の外へ切れる（2026-10-25 ユーザー指摘：狭い画面〔分割した窓・スマホ〕で版面の左端の 👍 を押すと「イイネ!」の札が画面の左へはみ出して切れる） — 根（会話の Claude が見たところ）：scripts
  - [~] 【依頼】（開始 2026-10-29 14:05 JST・持ち主 r2・依頼の係・最終 2026-10-29 14:50 JST）小元素を待たせない作り直し（2026-10-25，用户定的：AI を使わないので待つ理由がない。「起きたらすぐ＋空になるまで」「届かない版面は待たず取れない理由を出す」） — ①**起きたらすぐ**：版面を足した（items.yaml・follows）・管理
  - [~] 人ごとの 👍👎・欲しい物・気になるかも？ — 👍👎 と気になるかも？は済〔https://github.com/CxElegy/Wishlist/pull/765 ・ https://github.com/CxElegy/Wishlist/pull/766 、2026-11-02 r1f1。本番：test-a の票が u_ の行に入り test-b・店長と混ざらない・guest は拒否
  - [~] 後台の記事集めを正しく — コードだけの合併で全体の収集を走らせない（push は items.yaml・wishlist.yaml だけ）・お客さまは 1 人 100 版面・1 回 10 版面・1 回 80 版面。test-a の 40 版面が 8 時間以内に全部探した状態、cancelled が続かない
  - [?] Hermes agent を作る係にする（案 B、hermes/README.md） — 決定：常時動くサーバー・モデルは Claude（Anthropic の API、2026-10-24）。あなた待ち：サーバーの契約と、~/.hermes/.env の鍵（ANTHROPIC_API_KEY・GITHUB_TOKEN・SUPABASE_ACCESS_TOKEN・DISCORD_BOT
  - [?] サイトの名前 — 方向：英語の短い造語・P5／ゲーム風・新聞／雑誌・店長／お店（全部）。出した案（マイ号外・推し便・トピカ・NEWSHOP・Calling Card・Daily Heist・Stash Times）はどれも決め手なし。案を 15〜20 個の一覧（意味・ロゴの見本つき）にして、時間のあるときに選んでもらう。決まるまで題字は「ウォッチリスト通信」、目次は TBD
  - [~] （2026-10-26・#410：SPAM_URL に ?&xml=data:…;base64 を足した。userfeed の 1 回は版面の一部しか引き継がないので、本番の user_boards 13→12 件。残りは回ごとに消える・0 を確かめ待ち）【依頼】記事の網址が `?&xml=data:video/mp4;base64,…` の迷惑リンク（fctokyo.co.jp・to
- 最近の main：
  d64154af6 后台作業 2026-11-05 17:37
  ae674fed2 后台作業 2026-11-05 17:16
  795fe4bc3 重新生成网页（render）
  6524ea493 写真の一時保管：状態
  466e6fdf0 后台作業 2026-11-05 16:48
- 作業ツリー（claude/wonderful-bardeen-tukzjj）：変更なし
