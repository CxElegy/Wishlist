# account・test1 / test2 の詳細

## test1 / test2（2026-10-19，用户定的）

- **test1 = 店長のページ（2026-10-21，用户定的：以前做的 test1 的内容现在归到 admin 的店长下）**：前の test1 の中身（ちいかわ 等の関注項・623 票・愿望清单）を本番に戻した。`items.yaml`・`wishlist.yaml`・`inbox/`・`reports/`・`state/` が店長のもの。
  **网址里不出现 test1，也不出现人名・「店長」**（用户定的：照一般网站的做法，网址不带用户名；店長只是世界观的设定）：网页生成は `docs/home/`（`sitedir.SLUG = "home"`、https://cxelegy.github.io/Wishlist/home/ ），**大家都是同一个网址，内容由登录的人决定**（现在 = 店長的；以后一般用户登录后在同一页读自己的，见 `LOGIN.md` 第 2 步）。旧 `/test1/…`・`/shop/…` 只是跳到 `/home/` 的页。Supabase 的 account 名还是 `test1`（`sitedir.NAME`，只在库里；以后换成登录的号码 `user_id`）。店長は `c.elegy@outlook.com` でログイン。
- **test2** = 2026-10-19〜21 の試験の版，冻结在 `docs/test2/`（`python scripts/freeze_test1.py test2 test1 …` で「アーカイブ」の帯・写 Supabase を止める），数据存档在 `archive/test2/`。不再生成、后台不跑。test2 で決めた**規則**（一个名字一个版面・向导・入口）は店長のページでもそのまま使う（`docs/home/additem.js` は同じもの）。
- 根 `docs/index.html` 是**入口**（2026-10-21 起由 `scripts/welcome.py` 生成，`digest.py render` 时超过 24 小时就重做：产品介绍・店长页面的真实截图・新しく始める／ログイン／店長のページを見る；新建账号 = 邮箱和条款 → 新闻语言 → 喜欢的大类 → 左右滑的卡片（気になる／パス，2026-10-22 用户说「Tinder 風の前の版を戻して」改回来了，之后再细调） → 最初的版面 → `user_signup`；浏览器记得的人直接跳过入口），旧网址（settings.html・/test1/・/shop/ 等）跳到 /home/。
- **test1・test2 = 两个 account（用户定的，2026-10-19）**：以后的一般用户也按同样的形状加。每个 account 的东西从一开始就各自分开、互不相通：
  关注清单・愿望清单・收集的记事・state（推荐・口味・日志…）——本仓库里现在的 account（test1 = 店長，2026-10-21 起）用 `items.yaml`・`wishlist.yaml`・`inbox/`・`reports/`・`state/`，test2 的冻结在 `archive/test2/`；
  Supabase 的自己的表（投票 `feedback`・篇幅 `sizes`・目录分法 `nav_schemes`・请求 `item_requests`・照片 `photo_inbox`・AI 编辑开关 `edit_control`・更新中的条 `live_status`・记事的副本 `news`/`stories`/`price_history`）都有 `account` 列（`db/accounts.sql`）。
  网页只用带 `p_account` 的函数（`window.WL_ACCOUNT`，`render._account_tag`），Actions 的 `digest.supabase` 经 `scope_account` 只读写自己 account 的行；旧的不带 `p_account` 的函数只给冻结的 test1 用。
  现在的 account 名 = `sitedir.NAME`。新加一个 account：在 `sitedir` 换名字、Supabase 不用改表（行按 account 分开）。
  **以后加 Google 登录时（用户定的，2026-10-19）**：① 分 account 的列统一成登录的号码（`user_id`），现在的 `account` 只是测试用的过渡；
  ② test1 的内容（关注项・623 张投票・愿望清单等）算作用户本人（管理者）的东西；③ 网址（入口・`/test1/`・`/test2/`）只是现在测试用的分法，以后可以改。
- 现在的页面里也不留别的 account 的痕迹：运行日志只有自己的（test2 的在 `archive/test2/state/log/`）；愿望清单的 `watch` 指向现在没有的版面时不出「版面 →」；「気になるかも？」不出别的版面的候选（`current_picks`）；
  「小元素の判断の例」只出现在关注项的例子；ライブログ的浏览器缓存键是 `wl-term-<account>`（同一个域名）；说明文字里的例子不写具体作品名。
- **test2 的加关注项规则（只改逻辑）**：一个名字默认只开一个版面，放在它「本身是什么」的板块（选的维基数据条目当依据的面的板块：ちいかわ = 漫画条目 → 作品 › シリーズ）；
  其他面（グッズ・イベント…）只扩大搜索词、在目录里是枝（`media`）；不放乗換站（板块一问只选一个）；确认画面上默认不勾的「グッズ・イベントを別の版面にする」勾了才把其他板块的面做成下级（parent = 本体，和本体同一个板块）。
