# エンブレム（小元素）の直し方の学習帳（emblem_playbook.md）

2026-10-24 調べ。読んだもの：`git log --all -i --grep="小元素\|emblem\|エンブレム"`（87 件）と主なコミットの本文・差分、
`docs/rules/emblem.md`・`TEMPLATES.md`・`scripts/emblem_rules.py`（`rules()`・`REJECT_REASONS`・`EXAMPLES`）・`emblem.py`・`emblem_fill.py`・`face_id.py`・`render.py` の `.emb`。

HARNESS.md は `EMBLEM_PLAYBOOK.md`（リポジトリの直下）を読むことになっているが、**まだ無い**（a9274791 で参照だけ足された）。この文書がその元になる。

## 0. 「違う」の理由の集計（state/emblem_rejects.json）

- **ファイルが無い = まだ 1 回も「違う」が押されていない**（dbc12bc9、2026-10-22 に仕組みは入った）。理由から規則を締める道はまだ使われていない。
- 代わりに使える手がかり：items.yaml の `emblem_reject`（目で見て外した・検査で外れた画像）＝ 漫威电影 8・FROM 8・The Mandalorian 6・ILLIT 3・周杰伦 3・Astrae Oratio 1・A2O LITE 1（計 30）。実写の作品に集中している（役の姿の取り方がいちばん外れやすい）。
- `state/emblem_progress.json` の `funnel.rejected`（後台が自動で落とした理由）：哈利波特剧集「別人 34・顔なし 12・何人も 11」、A2O LITE「遠景 12・顔なし 10・何人も 3」、あつ森・Astrae Oratio「確かでない取り方 9 / 7」。

## 1. 壊れ方 → 原因 → 直した規則 → コミット

| # | 壊れ方 | 原因 | 直した規則（関数・閾値） | コミット |
|---|---|---|---|---|
| 1 | 丸いバッジで顔が切れる・写真がただの四角 | 枠の形が固定 | 透明な立ち絵を先に、なければ P5 風の傾いた四辺形カード（`clip-path`） | 46adab1a（10-16） |
| 2 | カードの窓に顔が入らない | 取景なし | `emblem.face_crop`（OpenCV＋lbpcascade_animeface）で 4:5 の範囲 `crop` | 8565d18e |
| 3 | 人物の背景が四角く残る | 切り抜きなし | rembg（birefnet-general-lite）で輪郭どおり＋`check_whole`（顔が端で切れる・左右 65% で体が切れる・小片・にじみ） | f53cd7d6 |
| 4 | 版面ごとに顔の大きさがばらばら・下のニュースに重なる | 画像の高さでそろえていた | `face_fit`：顔 = 高さの `FACE_SHARE` 32%、アップは `fs` で網页が縮める（`--k`）。帯の中に置き下端を帯に | c7a12d32 |
| 5 | 顔だけのアップ（BLEACH） | 代表画像がアップ | 顔 > `CLOSEUP` 50% は `find_bust` で同じページの胸像 | de2d6821 |
| 6 | 漫画のコマの切り抜きで吹き出しの跡がえぐれる（チャド） | Fandom の代表画像 = コマ | `check_whole` の `TOP_MAX` 50%（上の端の半分以上が人物 = コマ）→ 同じページの透明な立ち絵（`cutout_on_page`）→ 公式イラスト（`find_bust`、姓・名どちらでもファイル名一致） | 5cc12367（#130） |
| 7 | ジャンルの版面が記号（Twemoji）だけ | 「下の一段」を見ていない | `emblem_examples`（代表作）を 1 作 1 枚、Twemoji は垫底。別言語は言語間リンク（検索は別記事に当たる） | 5cc12367 |
| 8 | メンバー名（YOUNG・VORA・OA）で村・滝が出る | Commons を名前だけで検索 | グループ・出演者は「名前＋作品名」で検索。YouTube の場面を ③ 段に | 108ff2ef |
| 9 | YouTube の題名の字が切り抜きに残る・後ろの人が一緒に切れる | 投稿者サムネイル hq720 | 自動の場面 hq1〜3（`YT_FRAMES`）・`video_frame` で黒帯と下 `SUBTITLE` 18% を切る・`other_faces`（2 つ目の顔 ≥ `OTHER_FACE` 20%）で外す | 25388389 |
| 10 | 角色の多いゲームが数枚で止まる／主役 4 人のアニメが 6 枚 | 目標が固定 | 上限 = 主要な要素の数（`emblem_pool`／`roster`、`CEIL`）。`keep_framing` で前からの小元素を消さない | 21e1bca7（#147）、8a316a63（CEIL 200・`STEP` 10） |
| 11 | 全身の立ち絵がキャラごとに背の高さ・地面がばらばら（dota2 の武器・Slark のしゃがみ） | 画像の高さでそろえた | `body_marks`（YOLOv8m-pose：目・足首→足の裏、尻尾・武器・台座 `PEDESTAL` 1.6 を除く）、網页は目〜足の裏を 116px に、しゃがみは `render._body_len`（`BODY_CROUCH` 1.15）。ロゴは `is_logo` で地を抜き切らない | df3e598c（#153） |
| 12 | 全身だと小さく貼ったとき顔が見えない | 全身のまま | `bust_from_body`：目から足の裏の `BUST_CUT` 40% で切る。網页は `--legc` | 014f5631（#156） |
| 13 | Wikipedia の 403・429 で止まる | ブラウザのふりの UA・並列 | `wikihttp.py`：名乗った UA・ホスト 1 本・maxlag・Retry-After・キャッシュ | dede92b6（#158） |
| 14 | 実写の作品に出演者の私服写真 | 人物として探していた | `gather_roles`：出演者 → 役（Fandom）→ 役の記事の剧照・作品の動画の場面。出演者の写真は本人確認の基準だけ。`STAND_RATIO` 1.3 未満（寝そべり：ぐでたま）は測らない、全身の高さに上限 | 79fecc3d（#164） |
| 15 | ちびキャラ・動物・マスコットが顔だけになる | すべて腰で切った | `real_body`：腰が頭〜足の `HIP_MAX` 60% より上・目印の確かさ ≥ `BODY_CONF` 0.6 のときだけ上半身 | addf8c85 |
| 16 | タイトルロゴが白いカードで小さい | ロゴをカード扱い | `wordmark_local`：縁が透明・一色ならロゴとして貼る、横長（高さ÷幅 < `WIDE_LOGO` 0.5）は幅で大きく | 8a316a63 |
| 17 | 実写の暗い場面で何かわからない・横長の写真に白い余白 | 場面を区別しない | `role_images` は poster・promo・render の名前を先に（`POSTER_NAME`）、`DARK_MAX` 16%、比率外の写真は `badge.whole` | e4c4a57e |
| 18 | 濃い地のロゴの字が白フチに埋もれる・同じ写真が 4 枚（周杰伦） | 地を抜いた／網址違いを別物扱い | `PLATE_LUM` 80% 未満は板ごと（`plate`）、`file_key` で Wikimedia の thumb・元・FilePath を同じに | c2546ae2 |
| 19 | 新しいキャラの関注項でずっと失敗 | `emblem_fandom` が AI 頼み | `find_sources`：名前・副題・英語の搜索词 → `<名>.fandom.com`（wiki 名に作品名）→ 分類 → 名簿 | 417b61c2（#229） |
| 20 | 顔が見つからない控えで漫画のコマを拾う | 控えの条件が緩い | `find_bust(clear_bg)`：顔なしの控えは元が透明な立ち絵だけ。名簿の上（`HEAD` 5 人）を毎回先に | e5a933a3（#230） |
| 21 | 小元素が字・ボタンに重なる／足が切れる | 浮く動き・固定の空き | 上へだけ浮く・帯の線より下は `clip-path` で見せない（-14px）・本当の幅だけ帯を空ける（`EMB_JS` の `room`）・全身の下端を帯の線に | f725a442・cc028588 |
| 22 | 失敗した版面が何時間も止まる | 待ちが長い・指紋なしを「同じ」扱い | 段 ①標準 → ②名前を広げる → ③公式・記事のページ、`material` 指紋、`RETRY_HOURS` 6 → 1 | fd706d55・e96f5575・c602936d |
| 23 | 見て「違う」と思っても直す道がない | 手で消すだけ | 管理ページで理由を選んで外す → `emblem_reject`・`state/emblem_rejects.json` | dbc12bc9（#238） |
| 24 | お客さまのキャラの版面が字の順の脇役（原神 Aino・Albedo…、ゼルダ Agahnim…）・分類の説明の記事「Character」が 1 枚 | `categorymembers` が頭の 200 人（A〜B）だけ・参照 `lhlimit` 500 で頭打ち（主役が同じ数で並ぶ）・広すぎる分類 Characters（NPC 込み） | `category_top` が続き（cmcontinue 1000 人・lhcontinue 2000）で数え、分類名の記事と「…/Storyline」を除く・`CHAR_CATEGORIES` に Playable Characters。京都の字だけのロゴ・生成AI の図・大相撲の 1890s は `not_emblem`。`library_emblem.RULES` 4 で済みの版面も作り直し（`REDO`） | #332 |
| 25 | 京都の「ロゴ」が決済の案内板・電車の写真、iPhone が Linksys のロゴ | Commons の「名前 logo」の検索で logo の名前のファイルを SKIP_NAMES が落とし、残った写真を名前の一致だけで通した | `commons_photos(logo=True)` はロゴのファイルだけ・`own_logo`：名前とロゴの言葉を除いて何も残らないものだけ。`RULES` 5。ロゴのない製品（iPhone、P154 なし）は 0 枚になった → P18 を使う（届かなかった版面なので版は上げず 24 時間後に） | #333・（この PR） |
| 26 | キャラの版面の人数が版面ごとにばらばら（Astrae Oratio 29 人・BLEACH Mirrors High 6 人） | 名簿（emblem_pool）は emblem_category を手で書いた版面だけ。find_sources は AniList の番号があると分類を探さず、目標に届いた版面では呼ばれず、実写は数えない | `find_sources`：書いた Fandom が開けなければ Wikidata の P4073・作品の名前の付いた分類（`work_category`）→ その作品の wiki だけ汎用の分類（`own_wiki`）・AniList より分類・`roster` の実写は Wikidata の出演者（`wd_cast`）・そろった版面も `NAMES_V` で 1 回数え直す（`due`・ライブラリの `emblem_state.nv`） | このPR（2026-10-25） |
| 27 | 実写の版面が 6 人止まり（漫威电影：フランチャイズの Wikidata に出演者 P161 がない、哈利波特剧集：新しい剧で P161 が 12 人だけ） | 名簿は作品の P161 だけ | `live_cast`：作品の P161 → `wiki:` の記事の作品の P161（Avengers: Doomsday）→ 記事の「Cast」の節の「X as 役」（`wiki_cast`・`CAST_LINE`、役は `emblem_roles` へ）。`NAMES_V` 3 で数え直す | （この PR、2026-10-25） |
| 28 | 小元素が 60×10・209×45 の切れ端（紫の帯）・0 バイトで読めない（漫威电影 Black Panther・BLEACH Mirrors High 2 枚） | 合併のたびに fit_all が前の切り抜き（emblems/ の自分の出力）を切り詰め直して縮む。書き出しに大きさの検査がなかった | `emblem.save_cut`（短い辺 ≥ `CUT_MIN` 64px・横 ≤ 縦×`CUT_WIDE` 3、だめなら書かず前の画像を残す）＋`emblem_fill.drop_broken`（前からの切れ端・0 バイトを外して emblem_reject へ、`due` にも入る） | 2026-10-25 |
| 29 | 実写の名簿がそろって見えて Cast の節が一度も読まれない（哈利波特剧集 12 のまま）・同じ人が 2 回（Tenoch Huerta／Tenoch Huerta Mejía） | `fill_one` は pool＝who だと roster を呼ばない・wiki: のない版面は記事がない・`_name_key` は名字の足し書きを別人に | `_recount`（NAMES_V が上がった回は必ず roster）・`wd_enwiki`（Wikidata の英語の記事）・`_same_person`・役の `<!-- -->` を消す。NAMES_V 7 | 2026-10-25 |
| 30 | 作り直しの剧（哈利波特剧集）の小元素が 3/65 で止まる・別人 55 | 役の記事（Harry Potter・Hermione Granger）の画像も「作品名＋役名」の動画も前の映画の役者（Radcliffe・Watson）で、本人確認で全部落ちる | `actor_role_images`：出演者の Fandom の記事の画像＋ファイル検索（"出演者"）で、ファイル名に役の名前がある写真（「Nick Frost as Rubeus Hagrid」「HPTV BTS John Lithgow as Dumbledore」）を役の記事より先に（`PICK_ORDER`・`ROLE_WHY`） | 2026-10-25 |
| 31 | 名簿 65 人のうち 30 人に一度も順が来ない・もう小元素のいる主役（Harry／Dominic McLaughlin）を毎回試し直す・額で切れた 197×101 が版面の先頭に残る | `subjects` のずらしが STEP ずつ（60 人の後ろなら 0,10,…,50 だけ）・`have` が「役（出演者）」のままで名簿の出演者名と当たらない・`check_whole` の額の判断が haar の顔の上端だけで、ux_check（YuNet の目と口）と違った。前からの小元素は大きさしか見ていなかった | ずらしは 1 回に試す幅（STEP−HEAD）ずつ・`_who_of`（「役（出演者）」→ 出演者も）・`emblem.forehead_cut`（目の高さ < 目〜口 × `EYE_TOP` 1.4）を `check_whole` と `broken_cuts`（drop_broken）に。店長の版面で 11 枚が外れて取り直し | この PR |
| 32 | 頭のてっぺんが切れた切り抜き（BLEACH Mirrors High の髪）・ぼやけた知らない人の顔（哈利波特剧集 Oliver Wood＝名簿の人だが拡大した剧照） | `check_whole` は上の端に少し当たっても顔が全部入っていれば通した（「髪だけなら可」）・写真の鋭さ・顔の大きさを見ていなかった | `emblem.head_cut`（上 `HEAD_ROWS` 3px に横幅の `HEAD_EDGE` 20% 以上 = ✗、顔があっても）・`face_sharp`（写真：切り抜く前の顔の幅 ≥ `FACE_PX_MIN` 80px、書き出す大きさで顔の輪郭の鋭さ ≥ `SHARP_MIN` 1.0）を `check_whole` と `broken_cuts` に。店長 52 枚（BLEACH 31）を外して次の候補へ・お客さまは `library_emblem.RULES` 7 で作り直し・ux_check E7 に「頭のてっぺん」 | 2026-10-25 |
| 33 | 前からの小元素で頭が全部入った The Mandalorian Gideon（上の端 1.0%）・Mayfeld（0.3%）が「額で切れた」で外れた（9/17） | `broken_cuts` が上の端に当たっていないものにも `forehead_cut`（EYE_TOP 1.4 は顔いっぱいの切り抜きに厳しい）。check_whole は上の端 >3% のときだけ見る | `broken_cuts` も `top_share > TOP_TOUCH` のときだけ額を見る。外したものは `state/emblem_broken.json` に控え、規則の版 `BROKEN_V` を上げると `unbreak` が今の規則で見直して戻す（emblem_reject からも抜く） | （この PR） |
| 34 | 作り直しの剧で別人：哈利波特剧集 Padma Patil（Anjula Murali）に映画の Padma（PadmaPatil.png、2022 年） | 出演者の記事の写真が集合写真（Ravenclaw students）で顔の基準がなく、役の記事の代表画像と剧照（どちらも映画の役者）の 2 枚が「同じ顔の多数決」で本人になった | 出演者の顔の基準がないときは、ファイル名・題名に出演者の名前か作品の略号（HPTV）がなく、作品の始まり（Wikidata P580）の 2 年前より前に上がった（Fandom の cb=日付）役の記事・動画の画像は数えない（`emblem_fill.tied`・check の untied）。前からの小元素も `untied_roles` で外す | （この PR） |
| 35 | お客さまの版面（ライブラリ）だけ頭が切れた小元素が残る（ポケットモンスター 2・Mrs. GREEN APPLE 1、店長は 0） | `broken_cuts` は手元の `emblems/` の画像だけ見る → 公開の箱へ上げた前の回の小元素は一度も見ない・作り直しで 0 枚なら前のものをそのまま残していた | `emblem_fill.broken_image`（broken_cuts と同じ式）を `library_emblem.unbroken` で公開の箱の画像に・emblem_state.bv が BROKEN_V より古い版面は失敗の待ちも待たずに 1 回（型：同じ規則を店長とお客さまの両方の入口に、片方だけ直さない） | （この PR） |
| 36 | 哈利波特剧集 Hermione（Arabella Stanton）194×92：額から上の髪だけで顔がない（下の端が額の途中） | 顔の割り当て（剧照 cos 0.60）は通るが、切り抜き側の点検は「顔が見つかったら」しか見ない（forehead_cut・face_sharp は顔なしなら False/None で通す）。兜の顔なしと区別がなかった | `emblem.faceless_scrap`：写真で YuNet の顔がなく横が縦の 1.3 倍超 → check_whole ✗・broken_image ✗・BROKEN_V 3。縦長の兜（Din Djarin 396×492）は残る。1 枚ずつ外さない | 2026-10-26 |
| 37 | 切り抜きの形がおかしい（哈利波特剧集 Gregory Goyle：左右の下がまっすぐ縦に切れて「右下が四角く」体が途中で終わる）・かぎ形の出っぱり | 顔の大きさをそろえる `face_fit` が横幅 `bw` で切って体の横に垂直の切り口ができ、`check_whole` の左右の端の検査は下 35%（肩）を許していた。凹みを測る物差しもなかった | `cutshape`：左右の端にそって高さの `FLAT_RUN` 15% を超える直線は切り口が始まる行で下を切り落として半身（`trim_flat`・`FLAT_KEEP` 40%・顔の下まで）、上の端は横幅の `FLAT_TOP` 25%、`SOLID_MIN` 0.45 未満の凹みは ✗。前からの小元素は `repair_flat` で直し直せないものは `drop_broken`（`BROKEN_V` 4）。点検 E12 | #409 |

## 2. よく効いた直し方の型（手順）

### 型 A　壊れた 1 枚 → 「どの判断がそれを通したか」→ その判断の数か条件を締める
1. 壊れた小元素の `why`（取り方）・`source`（網域・ファイル名）を items.yaml で読む。
2. `emblem_rules.rules()` の段（③〜⑦）から、それを通した判断を 1 つ選ぶ（例：チャド → 「コマ・アップの切り抜き」`TOP_MAX`）。
3. その判断の定数か条件を変える（新しい判断なら `rules()` に 1 行＋落とす理由の言葉。`tests/test_emblem_fill.py` が理由の言葉の抜けを見る）。
4. 同じ取り方で取った**全部の版面**を新しい規則で最初から処理し直す（`emblem_fill.py "名前" --replace` か、該当の小元素を外して後台に任せる）。ちいかわ・実写 4 版面・キャラ全版面がこの形（e5a933a3・e4c4a57e・014f5631）。
5. 前 → 後の画像を `docs/emblems/examples/` に置き、`EXAMPLES` に 1 組。

### 型 B　「取り方」を正しい出どころに替える（何を探すかを変える）
- コマ → 同じページの透明な立ち絵（`cutout_on_page`）→ 公式イラスト（`find_bust`）。
- 実写 → 役の記事の剧照・作品の動画の場面（`gather_roles`）。出演者の写真は基準だけ。
- YouTube → 投稿者サムネイルでなく自動の場面（hq1〜3）。
- ジャンル → 下の一段（`emblem_examples`）。
- 出どころが見つからない → 規則で探して書く（`find_sources`）。AI の設計に頼らない。

### 型 C　網页で測る長さを決め、全員を同じ物差しで
- 顔 = 高さの 32%（`FACE_SHARE`）、全身 = 目〜足の裏 116px（`--leg`）、上半身 = 目〜足の裏 290px（`--legc`）、横長ロゴ = 幅 220px。
- 物差しに合わないもの（しゃがみ・寝そべり・ちび・横長）は**例外の規則**で外す（`BODY_CROUCH`・`STAND_RATIO`・`HIP_MAX`・`WIDE_LOGO`）。1 枚ずつの大きさは決して書かない。

### 型 D　人物は「顔のモデル」で機械的に落とす
- YuNet（顔あり・遠景 `FACE_MIN_RATIO` 10%・何人も `CROWD_RATIO` 60%）→ SFace（基準と ≥ 0.363、基準が怪しければ最大の同じ顔の集団）→ 切り抜き後に `other_faces`・`lost_face`・`hole_share`。
- 落とした理由は必ず言葉で残す（ライブログ・`funnel.rejected`）。理由が多い順に、次に締める判断が分かる。

### 型 E　ロゴは切らない・地だけ抜く
- `is_logo` → `clear_flat_bg`（縁につながる一色の地、差 `FLAT_TOL` 28）→ 濃い地（`PLATE_LUM` < 0.8）は板ごと → 横長は幅で大きく。

## 3. やってはいけないこと

- **1 枚ずつ手で直す**：items.yaml の 1 行の `body`・`crop`・`fs` を手で書き換えて見た目を合わせる、特定の版面だけの分岐（`if name == "あつ森"`）を足す。→ 規則（定数・条件・取り方）を直して全部の版面で作り直す（HARNESS.md「一番大事な決まり」1、docs/rules/emblem.md「只改规则、从头重跑，不单独修某一张图」）。
- **画像を手で描く・作る**（イラストを生成する、文字を書き足す）。TEMPLATES.md「不自己画」。
- **原図を変える**（色を塗る・合成する・別の画像とつなぐ）。許されているのは切り抜き・地を抜く・取景（crop）・縮めることだけ。
- Web 画像検索の結果を後台で自動で選ぶ（出どころが確かでない）。`AUTO_SOURCES` を緩めて数をそろえない。
- 失敗を `emblem_skip` で逃げる（その道は無くした。最後は Twemoji）。
- 「違う」と言われた画像（`emblem_reject`）をもう一度選ぶ。
- お客さまのアカウントだけ・テスト用の 1 人だけに効く直し。

## 4. 今回の点検で見つけた「規則の穴」（次に直す候補、詳しくは emblem_audit.md）

| 壊れ方 | 版面 | 通した規則 | 締め方の案 |
|---|---|---|---|
| 大乱闘のフィギュア（金の台座つき）が「公式の立ち絵」として入る | あつ森（Redd・Gulliver・Tortimer の 3 枚。Sable・Pascal も次に入る） | `emblem.cutout_on_page`：同じページの透明画像のうち**いちばん大きいもの** | ファイル名に `Trophy|SSBB|SSB4|amiibo|figure|statue|sticker` を含むものを除く。作品の略号（`_NH`）付きを先に |
| Fandom が見つからない | Astrae Oratio（`astrae-oratio.fandom.com` があるのに） | `fandom_api` の slug が `[^a-z0-9]` を全部消す → `astraeoratio` | 空白をハイフンにした slug（`astrae-oratio`）も試す |
| 後台で Nookipedia が全部 403 | あつ森（17/81 で止まる） | Actions からの取得（UA か IP） | `wikihttp` と同じ名乗った UA を MediaWiki 全般に、403 が続くホストは控え（Fandom の animalcrossing wiki）へ |
| 名簿に人でない名前（Player・Parents） | あつ森 | `roster`：分類の項目を全部名前に | 分類の項目のうち、ページに画像・キャラの情報箱があるものだけ |
| 役の記事の写真が前のシリーズの俳優（映画版）で「別人」 | 哈利波特剧集（3/6 で止まる） | `role_images`：役の記事の画像を全部候補に | 画像の名前・説明に作品名（HBO・年）か出演者名があるものを先に |
| 3 本の小元素が同じファイル | Vaundy（`vaundy-vaundy.webp` を 3 本） | 昔の書き込み（`file_key` より前） | 書き込みと点検で「同じ image は 1 本」、前からの重複も外す |
| 別人（女性）が本人として入る | Vaundy（`vaundy-vaundy-6`、YouTube の場面） | 本人の写真の基準・多数決 | 本人（person）の YouTube の場面は基準（Wikidata P18）との類似度を必須に（多数決にしない） |
| 2 人の切り抜き | A2O LITE（`a2o-lite-a2o-lite`、ユーザーが一覧で選んだ） | 手で選んだものは `other_faces` を通らない | 手で選んだものにも切り抜きの検査（顔の数）をかけ、外れたら知らせる |
| 顔のない部分だけの切り抜き（黒い頭頂部） | 漫威电影（Black Panther） | 兜・仮面の役の「顔なしでも残す」（trust_noface） | 顔なしで残すときは、切り抜きの縦横比・面積（`AREA_MIN`）と上の端の検査を厳しく |
| 空撮の写真（テニスコート）で何かわからない | 日本顶级网球赛事 | topic の Commons の写真 | topic は `emblem_examples`（選手・大会のロゴ）を書く。風景の写真（人も物も主役でない）は落とす |
| お客さまのキャラの版面が 0 枚（確かでない取り方だけ） | 呪術廻戦・SPY×FAMILY・鬼滅の刃・ポケモン・ゼルダ・モンハン・スプラ 3（ライブラリ） | 店長の版面は anilist_id・emblem_fandom を手で持つが、ライブラリの版面にはない。名前からの Fandom の推測はハイフン（spy-x-family）・「:」のあと（kimetsu-no-yaiba）を作れなかった | library_emblem.wd_entity が Wikidata の AniList（P8729→P8731）・Fandom（P4073→シリーズ P179 の P4073）を引く。fandom_api はハイフンの形・「:」のあと・転送先の名前も。規則の版 RULES を上げると届かなかった版面を待たずに取り直す（手元で SPY×FAMILY 0→3 枚） |
| お客さまの題材の版面が 0 枚（候補なし・確かでない取り方だけ） | サッカー日本代表・将棋・宇宙・ロケット・台風・天気・美術館の企画展・広島旅行（ライブラリ） | 店長の題材は emblem_icon・emblem_examples を手で持つが、ライブラリの版面にはない。Wikidata の画像は名前で検索していて「将棋」が当たらなかった | library_emblem.icons_for が名前・小分類の言葉 → Twemoji の記号（なければ板块の記号）を emblem_icon に。wikidata_images は版面の番号（Q…）で直接引く。RULES 3（手元で 6 版面すべて 0→1〜2 枚） |
| 作り直したのに前の規則の脇役（字の順の Aino・Albedo…）が残る・同じ画像が 2 回・Player が入る | 原神・ポケモン・モンハン・スプラ 3（ライブラリ） | ① 作り直しの「名簿にいる人は残す」が、名簿＝分類の全員（139 人）なので全部残した ② 新しい規則の値が前と同じだと null にしていた（emblem_who が null） ③ 名簿にまとめ・Player・別の作品の姿 | library_emblem RULES 6：新しい規則で取れれば前のものは残さない・前と同じ値は消さない・同じ網址は 1 本・emblem.not_character を名簿と結果に |
| 別の作品のキャラが名簿・小元素に入る（GTA 6 に GTA IV・V の主役）・名簿に戻したのに分類で足した人が残る（dota2 の伝承キャラ 6 枚） | GTA 6・dota2（店長） | own_wiki は wiki の名前が合うだけで通る（grand-theft-auto-vi は 2014 年の予想 wiki、Playable characters に Jason・Lucia がいない）・名簿を戻しても小元素は消さなかった | 分類は作品の登場人物（Wikidata P674）が 1 人は入っているものだけ（cat_fits）。通らなければその分類の名前を名簿から抜き、Wikidata の wiki（gta）の分類へ・手で数えた人数があれば ±10% の分類（dota2 Heroes 127）・名簿にいない人の小元素は外す（off_roster）。NAMES_V 4 で全部の版面を 1 回数え直す |
| 名前のない端役（Unnamed Officer 1・Unnamed Interrogator）が小元素に | GTA 6（店長、#361 で Characters in GTA VI に替えたあと） | 分類の全員を名簿にした（NPC のページも分類に入る） | emblem.NOT_CHAR に ^Unnamed（名簿・取る対象・ライブラリの結果から外れる）・off_roster が名簿にいても人でない名前の小元素を外す |
| 集まり（バンド・ギャング）が名簿と人数に入り、目標が届かない（15/39）・Unnamed を外したのに名簿の数が古いまま | GTA 6（店長・ライブラリ 3） | 名前の形では分からない（Gutless Wonders）・#369 で NAMES_V を上げず数え直されなかった | emblem.groups：ページの分類が集まり（Music bands・Gangs…）なら外す・NAMES_V 6・ライブラリの届かなかった版面の数え直しを途中より先（1.5）。GTA 6 の分類 39 → 27 |
| 作り直しの剧で出演者の役の姿が集まらない（2/65、役の記事も動画も前の映画の役者） | 哈利波特剧集（店長） | 作品の記事の剧照（HBO Max Still 01〜23）はファイル名にだれが写っているかなく、どの出演者の候補にもならなかった（gather_roles） | emblem_fill.assign_stills：作品の記事の画像の顔を名簿の出演者ぜんぶの基準と比べ、cos ≥ 0.363 かつ 2 番目と 0.08 以上の差の人へ（子役どうしは 0.4 前後まで似るので差も見る）。PICK_ORDER で役の記事より先（PR #この段） |
