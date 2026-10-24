# エンブレム（小元素）の今の状態の点検（emblem_audit.md）

2026-10-24 16:30〜17:30 JST、読むだけ。本番 https://cxelegy.github.io/Wishlist/home/ を Playwright（Chromium）で 1400px・390px。
網页は開くたびに候補から 1 枚をランダムに出す（`render.EMB_JS`）ので、**各版面の候補を全部 1 枚ずつ同じ枠に差し替えて**測った（店長 23 版面・176 枚 × 2 幅）。

使った道具（scratchpad、リポジトリには入れていない）：
- `/tmp/claude-0/-home-user-Wishlist/f7d58757-0f4f-51ac-a935-26a6fc91a366/scratchpad/emb_probe.py`（版面ごとの右上の切り出しと、出ている 1 枚の位置）
- `/tmp/claude-0/-home-user-Wishlist/f7d58757-0f4f-51ac-a935-26a6fc91a366/scratchpad/emb_alts.py`（全候補を差し替えて測る・撮る）→ `alts/alts-1400.json`・`alts/alts-390.json`・`alts/<幅>-<版面>-<候補>.png`
- `/tmp/claude-0/-home-user-Wishlist/f7d58757-0f4f-51ac-a935-26a6fc91a366/scratchpad/emb_users.py`（test-a・b・c でログインして me.html）→ `users/users.json`・`users/*.png`
- 写真の一覧：`alts/sheet-a.png`（漫威〜Astrae）・`alts/sheet-b.png`（绝区零 60）・`alts/sheet-c.png`（あつ森・dota2）・`alts/sheet-d.png`（ILLIT〜猫用品）・`alts/sel.png`（壊れたもの 10 枚）・`emb/sheet-1400.png`（版面の右上の切り出し）

## 1. まとめ

- **読み込めない画像：0 枚**（176 枚すべて naturalWidth > 1、1400・390 とも。390 で 1 回だけ MMORPG の Project TL ロゴが時間切れ → 取り直しで 200、たまたま）。白い四角・ロゴの白地も見当たらない。
- **いちばん大きい壊れ方は「出ない」：お客さまの版面 41 個すべてにエンブレムが無い**（test-a 40 版面・test-b 広島旅行 1・test-c は 0 版面で「はじめに」の静かな版面）。原因は規則：`scripts/user_pages.py` の `user_items` が店長と同じ名前の版面にだけ店長の `emblem` を写し、ほかの版面は `emblem` を作らない（emblem_fill はお客さまの版面を見ない）。
- 店長の 23 版面は全部エンブレムが出る。ただし**目標に届かず止まっている 4 版面**（毎時の後台で 0 枚足して失敗をくり返す）と、**中身が違う・崩れている 14 枚**（9 版面）がある。
- `state/emblem_rejects.json` は無い（「違う」はまだ 1 回も押されていない）。

## 2. 壊れ方の分類（数と版面名）

| 壊れ方 | 数 | 版面（どの 1 枚） | 通した規則（原因） |
|---|---|---|---|
| **出ない（エンブレムが無い）** | **41 版面** | お客さまの全版面（test-a：葬送のフリーレン・呪術廻戦・原神・YOASOBI・大谷翔平…40、test-b：広島旅行） | `user_pages.user_items` は店長の版面にしか `emblem` を付けない。お客さまの版面に emblem_fill を回す段がない |
| **足りない（目標に届かず毎時失敗）** | 4 版面 | あつ森 17/81・哈利波特剧集 3/6・Astrae Oratio 5/6・A2O LITE 8/9 | 下の 2-1〜2-4 |
| 別の作品の絵（大乱闘のフィギュア・金の台座） | 3 枚 | あつ森（Redd・Gulliver・Tortimer） | `emblem.cutout_on_page` が同じページの透明画像の**いちばん大きいもの**を取る（`*_SSBB_Trophy.png`）。Sable・Pascal も次に同じものが入る（手元で確かめた） |
| 人違い（別人） | 1 枚 | Vaundy（`vaundy-vaundy-6.webp`、YouTube の場面の女性） | person の YouTube の場面を多数決の本人確認で通した |
| 同じ画像の重複 | 3 本 → 1 枚 | Vaundy（`vaundy-vaundy.webp` を 3 本の小元素が指す。Wikipedia・Wikidata・本人の 3 網址）＋ほぼ同じ場面 2 枚（`-1`・`-2` は同じ動画の hq1・hq3） | `file_key` より前の書き込み。今の規則で前からの行を見直す段がない |
| ほかの人も写っている | 1 枚 | A2O LITE（`a2o-lite-a2o-lite.webp`、2 人） | 「ユーザーが一覧で選んだ」もので、切り抜きの顔の数の検査を通っていない |
| 何かわからない（顔のない部分だけ・空撮） | 2 枚 | 漫威电影（Black Panther：黒い頭頂の帯だけ）、日本顶级网球赛事（有明テニスの森の空撮） | 兜の役の「顔なしでも残す」（trust_noface）／topic の Commons 写真に「主役がない風景」を落とす規則がない |
| 切れている（顔の上・枠） | 2 枚 | 哈利波特剧集（Harry：動画の上端で頭が平らに切れた）、漫威电影（同上の Black Panther） | `check_whole` の `FACE_TOP` が場面の上端（動画の枠）を見ていない |
| 小さすぎ | 2 枚 | A2O LITE（RADA：1400 で 81×88px、同じ版面の中央値 174px の半分）、Astrae Oratio（Erin：寝そべりの横長で人が小さい） | 縮める `--k`（顔が大きい）と横長の幅の上限 190px が重なる |
| 遠景（顔が小さい全身写真） | 2 枚 | 周杰伦（コンサートの全身 2 枚、`1-*.webp`・`2-*.webp`） | `FACE_MIN_RATIO` は切り抜く前の写真に掛かるが、切り抜いた後の顔の大きさを見ない |
| 横に画面からはみ出す（390px） | 5 枚 | 绝区零（Seth・Cissia・Nangong Yu・Yixuan、1〜11px）・dota2（Crystal Maiden 1px） | 上半身に切った武器の横幅。`.emb` の `right:8px` と幅の上限なし（`img.body` は `max-width:none`） |
| 記号だけ（ジャンルの「下の一段」が無い） | 3 版面 | 猫用品（Twemoji 3 枚）・滑雪（Twemoji 2＋写真 1）・日本顶级网球赛事（Twemoji 2＋空撮） | `emblem_examples` が書かれていない（MMORPG 新作だけ書いてある） |
| 位置ずれ・字に重なる | 0（要確認 1） | — スマホで横長のロゴ・写真（哈利波特の HBO 板 215px・マンダロリアンのロゴ 225px）は画面の 6 割近くを占める。帯の右の空き（`EMB_JS` の `room`）は効いている | — |

## 3. 店長の 23 版面

数：items.yaml の `emblem` の本数・目標（`emblem_fill.rule`）・`emblem_pool`・`emblem_reject`・`state/emblem_progress.json` の状態と最後の試み。網页の高さは全候補の最小〜最大（px、1400／390）。

| 版面 | 種類 | 本数／目標 | pool | reject | 状態（最後の試み UTC） | 1400 高さ | 390 高さ | 見た目の問題 |
|---|---|---|---|---|---|---|---|---|
| 漫威电影 | character（実写） | 6/6 | - | 8 | ok（10-18 10:23） | 117–183 | 75–116 | Black Panther が黒い頭頂だけ |
| チェーンソーマン | character | 6/6 | 4 | 0 | ok（10-17） | 132–168 | 84–108 | なし |
| FROM | character（実写） | 6/6 | - | 8 | ok（10-18） | 115–174 | 73–112 | なし |
| 哈利波特剧集 | character（実写） | 3/6 | - | 0 | **failed**（10-24 07:37） | 140–175 | 113–131 | Harry の頭が上で平ら |
| The Mandalorian | character（実写） | 4/4 | - | 6 | ok | 85–170 | 85–109 | なし（ロゴは板ごと） |
| MMORPG 新作 | topic | 6/5 | - | 0 | ok | 120–175 | 77–114 | なし |
| BLEACH Mirrors High | character | 6/6 | - | 0 | ok | 170–173 | 109–111 | なし |
| GTA 6 | character | 2/2 | - | 0 | ok | 169 | 108–109 | なし |
| Astrae Oratio | character | 5/6 | - | 1 | **failed**（10-24 07:36） | 158–184 | 101–118 | Erin が横長で小さい |
| 绝区零 | character | 60/60 | 60 | 0 | ok | 111–172 | 71–110 | 390 で 4 枚が右に 1〜11px はみ出す |
| あつ森 | character | 17/81 | 81 | 0 | **failed**（10-24 07:37） | 129–175 | 83–114 | 大乱闘のフィギュア 3 枚 |
| dota2 | character | 20/20 | 126 | 0 | ok | 147–175 | 93–114 | 390 で 1 枚 1px |
| ILLIT | group | 5/5 | - | 3 | ok | 167–175 | 107–114 | Iroha が白黒の寝そべり（許容） |
| A2O LITE | group | 8/9 | - | 1 | **failed**（10-24 07:36） | 88–175 | 56–114 | 2 人の 1 枚・RADA が小さい |
| 周杰伦 | person | 6/6 | - | 3 | ok | 163–175 | 105–113 | 遠景 2 枚 |
| Vaundy | person | 6/6（中身は 4 種） | - | 0 | ok | 168–175 | 108–114 | 同じ画像 3 本・別人 1 |
| 日本顶级网球赛事 | topic | 3/3 | - | 0 | ok | 120–150 | 77–129 | 空撮・記号だけ |
| 滑雪 | topic | 3/3 | - | 0 | ok | 120–170 | 77–126 | 記号が主 |
| gelato pique | brand | 1/1 | - | 0 | ok | 111 | 71 | なし |
| 三星手机 | brand | 1/1 | - | 0 | ok | 112 | 77 | なし |
| ぐでたま | character | 3/3 | - | 0 | ok | 168–175 | 108–114 | なし |
| 星巴克马克杯 | brand | 1/1 | - | 0 | ok | 106 | 68 | なし |
| 猫用品 | topic | 3/3 | - | 0 | ok | 120 | 77 | 記号だけ |

### 2-1〜2-4　止まっている 4 版面の原因（ライブログ `live_log` と `emblem_progress.json` から）

1. **あつ森 17/81**：毎時、名簿の 10 人（Sable・Player・DJ KK・Gullivarrr・Pascal・Farley・Parents・Jack・Harriet・Gracie）を Nookipedia（`emblem_api`）に聞くが、**Actions からは全部 HTTP 403**（手元からは 200 で画像も取れる）。残りは Wikipedia・Commons（キャラでは「確かでない取り方」）で 0 枚。さらに名簿に人でない名前（Player・Parents）。公式サイトは `CERTIFICATE_VERIFY_FAILED`。
2. **哈利波特剧集 3/6**：HBO の新しい出演者（Arabella Stanton・Paapa Essiedu・John Lithgow・Nick Frost）を基準に、役の記事（Harry Potter Wiki = 映画版の写真）と予告編の場面を比べて「別人 34・顔なし 12・何人も 11」。役の記事の写真が前のシリーズ（映画版）のもの。
3. **Astrae Oratio 5/6**：`emblem_fandom` が無く、`find_sources` の推測 slug が `astraeoratio`（404）。本当は `astrae-oratio.fandom.com`（今の 5 枚もここから）。対象が「Astrae Oratio」1 つだけになり、記事の画像は「確かでない取り方 7」。
4. **A2O LITE 8/9**：YouTube・記事のページの場面が「遠景 12・顔なし 10・何人も 3」。新しいグループで Wiki がない（規則どおりの失敗。1 時間ごとに同じ材料を見直している）。

## 4. お客さまのページ（test-a・test-b・test-c、合言葉 0000、me.html 経由）

| だれ | 版面 | エンブレムのある版面 | 様子 |
|---|---|---|---|
| test-a | 40（店長と同じ名前は 0） | 0 | 1400・390 とも、版面の帯は主題・配色つきで出るが右上は空 |
| test-b | 1（広島旅行、記事 8） | 0 | ポスター・頭条は出る。版面の右上は空 |
| test-c | 0（「はじめに」の静かな版面） | 0 | 版面 0 個の人は規則どおり |

- ライブラリ（Supabase `boards`）で数えると：店長の版面 23 行は 23 行とも `config.emblem` あり、お客さまの版面 41 行（`created_by = user`）は **0 行**。41 行のうち 36 行は Wikidata の番号（`wd`）がある → emblem_fill の手がかり（記事名・P18・P154）はすでにある。
- 店長と同じ名前の版面を追いかけた人には、店長の `emblem` がそのまま写る（`user_pages.user_items` → `render.render` の emblem 引数）。今のテスト用アカウントには該当なし。
- 写真：`users/test-a-1400-me.html.png`・`users/test-b-1400-me.html.png`・`users/test-c-1400-me.html.png`（と 390）。
- 注意：test-a で /home/ を開いた直後（15 秒）は店長の 23 版面が見えた回があった（me.html への差し替えが遅い）。エンブレムとは別の話なので、点検では me.html を直接開く。
