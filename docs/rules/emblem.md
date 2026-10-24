# 小元素（emblem）

## 小元素（原「管理ページ」の一部）

- **小元素の「違う」（2026-10-21，用户定的）**：「版面ごとの状態」の小元素（行のサムネ・「小元素の探し方」の中）を押す → **理由を選ぶ**（`emblem_rules.REJECT_REASONS` の 10 種＋ひとこと）→ 下の帯の「外す」。
  版面ごとに `submit_item` の edit ＋ `{_emblem_reject: [{image, reason, note}]}`（DB の変更なし）→ `requests.yml` の `take-items` が `digest.reject_emblems` で items.yaml から外し、元の画像を `emblem_reject` に（二度と自動で選ばない）、倉庫の webp も消す。足りなくなった分は次の後台で別の画像。
  **理由は今後の規則の手がかり**：`state/emblem_rejects.json` に理由・取り方（why）・網域・種類と一緒に残り、管理ページ「「違う」の理由」で数える。同じ理由・同じ取り方が溜まったら、`REJECT_REASONS` の 3 つ目（近い判断）を締める。規則がまだない理由（「そのほか」）が溜まったら `rules()` に 1 行足す。
- **全身还是半身（用户定的）**：游戏・动画的官方立绘（原图透明背景）先按全身测量，再裁成上半身（`emblem.bust_from_body`：从眼睛往下「眼睛到脚底」的 40%，腰附近）——全身贴纸太小看不清脸；**只有正常人体比例才裁**（`emblem.real_body`：姿势模型量腰的位置，腰在「头顶到脚底」60% 以上 = 正常比例；3D 卡通・Q 版大头（腰更低）、动物・吉祥物（姿势模型认不出人体，あつ森的居民・ポチタ）保持全身，用户定的）；
  照片・漫画格子・视频画面按脸裁成半身（`emblem.want_full`）。
  测量：「眼睛到脚底」长度每个角色一样（裁后脚底在图外，网页仍按这个长度缩放 → 体的同一处切开、脸和其他半身像一样大）、按重心对齐（`body_marks`：YOLOv8m-pose 找眼睛和脚踝，从脚踝往下找脚底；尾巴・武器・裙摆・台座不算脚；蹲着的按面积量）。
  Logo 不裁（去掉纯色底存进仓库）；作品主图若是纯文字标题 logo（The Mandalorian）不做卡片，去底后当 logo 贴、横长的按宽度放大（`emblem.wordmark_local` / `render.WIDE_LOGO`）；卡片只在比例接近 4:5 时裁。**只改规则、从头重跑，不单独修某一张图**。
  **实拍作品贴角色的样子（用户定的）**：剧・电影不用演员生活照，用角色页的剧照・作品视频的画面（`emblem_fill.gather_roles`，演员照片只做人脸比对的基准），不够时补作品海报。
  横长・躺着的形象（高 < 宽×1.3）不量身高不裁，整张显示；全身显示高度有上限。
  管理页「小元素の判断の例」用真实图片放「前 → 後」对比（`emblem_rules.EXAMPLES`，图在 `docs/emblems/examples/`）：加新判断或修了一个坏例子时，把那次的前后图也放进去。
- **小元素（emblem）**：每个版面右上的贴纸。规矩（种类 → 目标枚数 → 取法的顺序 → 本人确认）在 `scripts/emblem_fill.py`、`scripts/face_id.py`，说明在 `TEMPLATES.md`；
  **选图先想「下一层」**：类别・题材（MMORPG 新作、猫用品、滑雪）贴的是它下面的具体作品 / 品牌 / 选手（`emblem_examples`，我喜欢的放第一个，例：剑灵），
  记号（Twemoji）只垫底。角色不用漫画格子・截图，先找官方立绘 / 插画；抠图后上边缘一半以上是人（连框切的特写）就不用；
  **枚数的上限由内容的主要元素数决定**（用户定的，不只是游戏）：1 个元素 1 张，天井 200（用户定的：主要角色全员，绝区零 60 人就 60 张；一次后台只补 10 人 `emblem_fill.STEP`，慢慢补齐）——角色多的游戏有多少角色就多少张、主角 4 人的动画 4 张、5 人团 5 张、
  主题按代表作数。元素数是 `emblem_pool`（`emblem_fill.py --roster` 从 `emblem_category` 分类或 AniList 主角数出来，并补名字）；
  管理页「小元素」列出每个版面的种类・目标・现有枚数，没到目标的 AI 编辑会自动补（`python scripts/emblem_fill.py --audit`）。
- **お客さまの版面の小元素（2026-10-24，用户定的）**：店長と同じ `emblem_fill.fill_one` を、ライブラリの版面ごとに 1 回（`scripts/library_emblem.py`・`library_emblem.yml`、2 時間ごと）。版面 1 つだけの items.yaml を一時の場所に作って走らせる（本物の items.yaml に触れない）。種類は規則（`kind_for`：グループ → group・人（Wikidata P31=Q5）・演出のソロ → person・游戏/影视 → character・好物 → brand・ほか → topic）。題材（topic）は記号も規則で（`icons_for`：名前・小分類の言葉 → Twemoji、当たらなければ板块の記号）、Wikidata の画像は版面の番号で直接引き、字だけ・説明の図・1950 年より前の写真や絵はファイル名で外す（`emblem_fill.not_emblem`）。キャラの名簿は分類の続き・参照 500 超えも数え、分類の説明の記事と下位のページを除く（`emblem.category_top`）。規則の版（`RULES`）を上げると済みの版面も作り直す（`REDO`）。画像は Supabase Storage の公開の箱 `emblems`（`db/emblems.sql`、ファイル名は番号と指紋だけ）、結果は `boards.config.emblem`、`user_pages.py` がそれを版面に。ログ・帯に版面の名前を出さない。
