# 版面模版手册（给 AI 编辑看的）

首页上每个关注项一个版面。版面的**配色**来自作品自己（封面取色或 `items.yaml` 的 `theme`），
版面的**模版**（底纹、题字形状、照片边框、标题旁的装饰字）按题材来：`items.yaml` 里关注项的 `motif` 写模版 id，
模版的样子在 `templates/<id>.css`，一览在 `templates/index.yaml`。

现在模版库里有 **30 套主题**（背景花纹 + 题字形状 + 照片边框 + 点 👍 时的演出），一览和试玩在网页的「テーマ見本」
（`docs/themes.html`，https://cxelegy.github.io/Wishlist/themes.html）。
规矩：**每个新关注项加进来时，AI 都要把它的版面设计一遍**，下面四样都要定，写进 `items.yaml`：

| 要定的 | 写在哪 | 怎么定 |
|---|---|---|
| ① 主题（背景花纹·题字·照片框） | `motif` | 从 30 套里挑最合气质的；挑不到就新做一套（下面「步骤」），很像就合并 |
| ② 配色（底色明暗·强调色） | `theme` | 有角色绘：`scripts/emblem.py --tone dark/light` 从小元素取色；人物/产品照片：`--palette keep` 保留原配色。见「配色的协调」 |
| ③ 小元素（右上的贴纸，可多张，每次打开随机一张） | `emblem`（不贴就写 `emblem_skip: "理由"`） | `scripts/emblem.py`：主要角色（AniList 主角／Wiki 分类里链接多的／AI 挑的代表角色），只有一个角色就挑几个有名场景；不自己画，不改原图；认不出主题的综合类别不硬贴 |
| ④ 点 👍 的演出 | `like_fx`（不写＝用主题的 `fx`） | 从 `scripts/likefx.py` 的 20 种里挑和作品最搭的（例：少年漫画 → `manga`「ドン！」，星战 → `rocket`，偶像 → `hearts`） |

**判断规则只有一张表**：`scripts/emblem_rules.py`（①要几张 → ②去哪找 → ③能不能用 → ④人物照片 → ⑤选哪张 → ⑥抠图 → ⑦统一 → ⑧凑不够），
每一行写「判断・数字・AI 还是ルール・代码位置」，数字直接读代码里的常量（改代码，表跟着变）。管理页「小元素の自動補完」流程图下面的「判断の一覧」就是这张表。
**全身・半身**：官方立绘（透明背景）= 全身，按「眼睛到脚底」统一身高、脚底对齐、重心对齐；照片・格子・场面 = 半身（脸占 32%）。
可在 `items.yaml` 写 `emblem_framing: full / bust`（版面）或小元素的 `framing:`（单张）。Logo 去纯色底、不裁。
**加新判断时在这里加一行**（测试会检查代码里每个淘汰理由都在表里）。下面的说明是补充，数以表为准。

抠图：`python scripts/emblem.py --cut 作品名 drawn`（rembg 的 birefnet-general-lite，存到 `docs/emblems/`，原网址留在 `source`）。
要装 `pip install "rembg[cpu]" "opencv-python-headless<5"`。抠完自动检查、不合格的不用：
① 脸被画面边缘切掉（只切掉头发顶部可以）；**上边缘一半以上都是人**的也不用——那是漫画格子 / 脸部特写连框一起切的，
抠掉对话框、背景后会留下奇怪的缺口（チャド的例子）② 身体在左右边缘的上 65% 被切掉 ③ 只留主体，旁边的小碎块去掉 ④ 边缘发虚（半透明多）
⑤ 同一版面取景要统一：有半身像就去掉全身像。抠完一定要用眼睛看一遍（侧脸、蒙面等检测不到脸的会提示「目で確認」）。

**选图的顺序（角色）**：Fandom 的角色页，代表图常常是漫画格子或动画截图，不直接用——
先找同一页里的**透明背景官方立绘**（`cutout_on_page`），再是代表图；代表图检查不合格时，自动在同一页找**官方插画**（游戏立绘、宣传图，
`find_bust`，名字的姓或名出现在文件名里都算：「Yasutora Sado」→ `BBSSado.png`）抠成胸像。刘海挡住眼睛、检测不到脸的角色，
取检查合格的最大一张、提示「目で確認」。
实拍剧 / 电影翻拍：用**这一版的演员页**的照片，不用角色页（多是旧版的剧照）。

小元素选什么（按作品的种类，枚数的规矩在 `scripts/emblem_fill.py` 的 `RULES`，管理页「小元素」能看到每个版面的现状）：

| 种类（`emblem_kind`） | 收什么 | 目标枚数（最少〜最大） |
|---|---|---|
| `person` 本人（周杰伦、Vaundy） | 同一个人的**不同照片**（年代、造型、场合） | 6（3〜10） |
| `group` 偶像团（ILLIT、A2O LITE） | **所有主要成员**各 1 张，名字写在 `emblem_who` | 成员数（最多 20） |
| `character` 动画 / 游戏 / 剧 | 动画：主角团 + 人气高的角色（AniList）；游戏、剧：主要角色 / 主要演员，名字写在 `emblem_who`（实拍剧用这一版的演员） | **主要角色的数量**（最多 20；不知道时 6） |
| `brand` 品牌 | 官方 Logo，1 种就够 | 1 |
| `topic` 主题 / 赛事 | **先想这个版面「下一层」是什么**：类别（MMORPG 新作）→ 代表作品（剑灵、AION 2…）；运动 → 有名的选手・大会；用品 → 代表品牌。写进 `emblem_examples`（用户喜欢的放第一个），每个取 Logo 或 Wikipedia 记事的主视觉 / 包装图各 1 张；其次是主题的专属物（Logo、奖杯、官方用球、场地），Twemoji 图标只用来垫底 | 代表作的数量（最多 10；没写时 3） |

- **上限由内容决定，不按游戏 / 动画写死**：上限 = 这个内容的「主要元素」有多少（1 个元素 1 张），天井 `CEIL`（角色・团 20、主题 10、本人 10、品牌 1）。
  角色多的游戏（绝区零 60 个可玩角色、dota2 126 个英雄、あつ森 81 个特殊角色）→ 20 张；主角只有 4 人的动画 → 4 张；两个主角的 GTA6 → 2 张。
  元素数写在 `emblem_pool`，由 `emblem_fill.py --roster` 自动数：`emblem_category`（Fandom 等的分类，例：`Playable Agents`）的人数，
  没有就数 AniList 的主角（role MAIN）；同时按「被其他页面引用多 → 记事长」的顺序把名字补进 `emblem_who`（目标 = 已列出的名字数）。
  数不到的（官方站直接给图的 dota2）由 AI 手写 `emblem_pool` 和名字。后台遇到还没有 `emblem_pool` 的版面会先数。
  `emblem_max` 只用来手动压低（ぐでたま 只有 1 个角色 → 3 个场景）。
- **不再有 `emblem_skip` 这条退路**：种类的取法顺序里最后是 Twemoji 图标，所以不会是 0 张。取不到好图就换下一种取法，不是放弃。
- 在 `items.yaml` 里写：`emblem_kind`（种类）、`emblem_who`（要收的名字：成员 / 角色 / 演员）、`emblem_subject`（本人或品牌的搜索名）、
  `emblem_fandom` / `emblem_api`（Fandom 的 wiki 名 / 其他 MediaWiki 的 api.php）、`emblem_icon`（Twemoji 的编码，空格分隔）、`emblem_urls`（直接指定的官方图）、
  `emblem_examples`（主题的下一层：代表作品 / 品牌 / 选手，写成 `en:Blade & Soul` 指定记事；那一版没图时顺着**语言间链接**找同一记事的别的语言版，
  不用搜索——搜索会撞到别的记事，例：「Odin: Valhalla Rising」搜到 FF13、「Chrono Odyssey」搜到人物）。
  没写 `emblem_kind` 时按 `type` 推定（anime / game / show → character，event → person，product → brand，category → topic）。

### 补齐的流程（AI 编辑每次都先做；流程图在管理页「プロセス → 小元素の選定」）

```bash
python scripts/emblem_fill.py --audit                  # 全部版面：种类、目标、现有枚数（足りない順）
python scripts/emblem_fill.py "作品名"                  # 候选图 → /tmp/wishlist-emblem/<名>.jpg（带编号的一览）和 .json
python scripts/emblem_fill.py "作品名" --commit 1,3,5   # 看过一览后选编号：写进 items.yaml，人物自动抠图、统一脸的大小（--replace 置换）
python scripts/emblem_fill.py --auto                   # 不看一览，按固定顺序选（Web 搜索只是最后手段）
python scripts/emblem_fill.py --background --minutes 40 # 定时任务用：时间预算内按缺口大小 4 本并行补（--workers），进度写进 state/emblem_progress.json
python scripts/emblem_fill.py --progress               # 只把 items.yaml 的现有枚数同步进进度文件（不联网）
```

**后台模式（GitHub Actions「后台作業」，后台ゲート判断有缺口时，不用 AI）**：自动选图只用确かな取法——人物 / 团体 / 演员（`emblem_people: true`）必须过本人识别，
画的角色只用 `直接指定` / Fandom（名字是普通词的角色在 Wikipedia・Commons 会撞到别的东西，例：dota2 的 Juggernaut 撞到乐队照片），
brand 先 Wikidata P154 / 官网 Logo，topic 先 Wikidata / Commons / Twemoji。**Web 图片搜索只收集、不自动选**。
补不到目标的标「失敗」（24 小时后再试），没选的候选按规则写明理由（遠景・何人も写っている・別人・切り抜きの穴・重複・確かでない取り方），
管理页「小元素の探し方」能看到；想手动补就 `emblem_fill.py "名" --commit 番号`，或把确实的图写进 `emblem_urls`。
Wikipedia 连续 429 时那个主机休 5 分钟，不在一个关注项上耗光预算。官方立绘能直接拿到时写进 `emblem_urls`（dota2 用 Steam 的英雄立绘）。
看过觉得不行的图（别人、抠图有洞）：从 `emblem` 里删掉，把它的原图网址写进 `emblem_reject`，后台就不会再选它。
进度在管理页「バックグラウンド」（版面 × 流程的表、下次几点・还剩几分钟）和「小元素 → 進捗」。

取法的顺序（足りるまで次へ）：直接指定 → AniList → Fandom → Wikipedia → Commons → 集めた新闻的配图 → 公式サイト → YouTube → Web 图片搜索 → Twemoji。
团体成员・出演者的名字常是普通单词（A2O LITE 的 YOUNG・VORA・OA，ILLIT 的 Moka），**Commons 一定带上作品名搜**，不然会搜到村子、瀑布、咖啡壶。
**YouTube**（③ 段，人物用）：搜「作品名 + 名字」，只收标题里两个都有的视频，fancam・직캠・teaser 优先，用 YouTube 从视频里自动截的画面（hq1〜3，480×360；投稿者做的封面图有大字，抠图会留字，不用）。抠完的图里还有别人的脸（背景的人）就不用；本人确认照常走脸的规则。
**本人确认**（`scripts/face_id.py`）：人物 / 团体的照片要检测到脸，并且和记事的代表图是同一个人（YuNet + SFace，相似度 ≥ 0.363；代表图不对时按「最大的同脸集团」多数决）。
观众席、画作、荧光棒、别人的照片会自动落掉。**还要用眼睛看一览图再选号码**：Web 搜索和新闻配图的出处不确定，别人 / 广告图也会混进来。
刚出道的团（Wiki 没有）：先用集めた新闻的配图（标题里有成员名）和公式サイト，成员名写进 `emblem_who`。

## 什么时候做

`items.yaml` 里 `notes` 有「从网页设置页加进来的」、但还没有 `motif` 的关注项。
设置页一加进来，工作流就叫你（AI 编辑）来；每天两次的定时编排也先检查一遍。
在你设计好之前，这一项先按 `type` 借用 `index.yaml` 里 `defaults` 对得上的模版（见 `render.template_for`），所以首页不会是光板。

## 配色的协调（重要）

版面的底色、强调色要和这个作品**最有代表性的颜色**搭：作品的主视觉、角色、以及版面上贴的作品小元素。
例：チェーンソーマン 的小元素是橙色的ポチタ → 版面用「橙 + 墨黑 + 米白」，不要用和橙色打架的深蓝。

- 先找作品的代表色（主视觉 / 角色 / 小元素的主色），版面的 `accent` 用它或它的邻近色，`bg` 用和它搭的中性色（米白、墨黑、同色系的深色）。
- **底色的明暗按作品的气质分，不要一律米白**：热血、暴力、恐怖、科幻 → 墨色的暗底；可爱、治愈、日常 → 米白的浅底。
  有小元素的作品用 `scripts/emblem.py --tone dark|light` 自动算（代表色取自小元素的第一张）。
- **字一定要看得清**：不只配色本身 4.5:1，网页上实际叠出来的也要量（带透明度的小字、底纹上的字、NEW 角标都算）。
  量的方法：Playwright 打开网页，取每段文字的颜色（乘上祖先的 opacity）和背后最近的底色算对比度，普通字 ≥ 4.5、大字 ≥ 3。
- 不要同时出现两个互相打架的强色（橙 × 深蓝、红 × 绿 这类补色当主色）。补色只能当很小的点缀。
- 定好写进 `items.yaml` 的 `theme:`（封面自动取色和代表色不搭时，必须手写）；文字和底色对比度至少 4.5:1（`render._legible` 会兜底，但先自己选对）。
- 改完在 1400 / 390 px 截图，把小元素和版面放在一起看一眼再提交。

## 步骤

1. **看清这一项是什么气质**：读 `items.yaml` 里它的 `type`、`subtitle`、`keywords`、`priority`、`notes`、`site`，
   和今天 `inbox/日期.json` 里它的标题。用三个词概括（例：「热血 · 黑白漫画 · 暴力美学」「慵懒 · 黄色 · 治愈角色」）。
2. **先找能合并的**：对照 `templates/index.yaml` 每个模版的 `for`。
   - 气质一样 → **直接用**：`motif` 写那个 id，并在那个模版的 `for` 里补上这个题材。
   - 差一点 → **改那个模版**让它能兼容两者，但不能让已经在用它的作品变难看（改完把用它的版面都看一遍）。
   - 都不像 → **新做一个**。
   模版太多（超过 40 个）时，优先合并。
3. **新做模版**：
   - 写 `templates/<id>.css`。id 用小写英文（如 `lazy`、`noir`）。第一行注释写「版面模版「id」：一句话说明」。
   - 只写 `.m-<id>` 开头的规则，**只用作品的配色变量**：`--bg --fg --acc --abg --afg --aacc --line`（和 `--font-sans` 等字体变量）。
     不写死颜色——同一个模版换个作品就是另一套颜色，这样才能合并。
   - 能改的：版面底纹（`.m-<id>{background-image:…}`）、题字形状（`.m-<id> .band .title`）、照片边框和裁切（`.m-<id> .card .pic`）、
     标题旁的装饰字（`.m-<id> .deco`）、日期角标（`.m-<id> .when b`）。
     不改的：网格、卡片排列、字号（不小于 10px）、行数——版面的骨架所有作品一样。
   - 参照现有的 30 套（`templates/*.css`），例如：`retro`（星星 + 角丸题字）、`manga`（网点 + 斜分格 + 擬音字）、`pop`（水玉 + 圆角）、`chainsaw`（锯齿边 + 墨点）、`porcelain`（青海波）、
     `film`（胶片孔 + 粗黑边）、`street`（斜体 + 警示条纹）。
   - 在 `templates/index.yaml` 加一条：`id`、`name`（中文名）、`ja`（日语名，「テーマ見本」上显示）、`fx`（点 👍 的演出，
     从 `scripts/likefx.py` 的 `FX` 里挑最合气质的；20 种都不合适就在那里新加一种）、`for`（适合什么题材，一句话）、`deco`（标题旁的装饰字，可空；
     用网页字体里有的字符，泰文、表情符号之类会显示成乱码）、
     `defaults: []`（以后有把握了再写这个模版适合当哪种 type 的默认）。
4. **写回关注项**：`items.yaml` 里这一项加 `motif: <id>`；封面取色不好看时可以手写 `theme:`（字段见 `items.yaml` 开头，
   文字和底色对比度至少 4.5:1）。`notes` 开头的「从网页设置页加进来的」留着，后面补一句「版面模版：<id>（AI 设计，日期）」。
5. **检查**：
   ```bash
   python -m unittest discover -s tests      # test_design / test_templates 会查模版文件、配色变量、对比度
   python scripts/digest.py render           # 重新生成网页
   grep -c 'class="sec m-<id>' docs/index.html
   ```
   能截图就用 Playwright 截 1400 / 390 px 宽看一眼这个版面：字没有被装饰压住、照片没有被切掉脸。
   再打开 `docs/themes.html` 按一下这套主题的 👍，看演出和版面的气质合不合。
6. **提交**（和编排一起提交也行）：
   ```bash
   git add templates items.yaml docs
   git commit -m "版面模版：<关注项> → <id>"
   git pull --rebase && git push origin main
   ```
