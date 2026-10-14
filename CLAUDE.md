# 给 Claude 的约定

## 主动告诉我有哪些 MCP 连接器能用

- 任务能靠某个 MCP 连接器更方便地完成时（比如改数据库用 Supabase、看 PR 用 GitHub），**先告诉我有这个连接器**，
  不要让我自己去 SQL Editor / 网页手动操作。
- 连接器已经连上：直接说「可以用 XX 连接器帮你做」，然后去做。
- 还没连上：说清楚是哪个连接器、能帮上什么，并给出连接地址 https://claude.ai/customize/connectors
  （连好后要开新会话才会加载）。
- 已连上的连接器：Supabase（项目 `bzokpnbcjscbcehdxtjq`，表 `feedback` / `news` / `sizes` / `item_requests`）、GitHub。

## 篇幅 S / M / L

每个关注项的篇幅存在 Supabase 的 `sizes` 表，我自己在网页的 ⚙ 设置页（docs/settings.html，不用口令）也能改。
我说「把 XX 改成 L」时，用 Supabase 连接器直接改表；
连接器不可用时改 `items.yaml` 里的 `size`，下次出刊会自动同步进数据库。

## 每次回复都贴链接

- 回复里只要提到网页、PR、设置页，就把可以直接点开的链接贴上：
  简报 https://cxelegy.github.io/Wishlist/ 、设置页 https://cxelegy.github.io/Wishlist/settings.html 、
  愿望清单 https://cxelegy.github.io/Wishlist/wishlist.html 、PR 用完整网址。
- 合并 PR 后网页大约 1 分钟更新（`.github/workflows/render.yml` 只重新生成网页）；
  确认网页已经更新了再告诉我，并附上链接。收集新闻、发通知仍由「关注清单通信」慢慢跑。

## 完善关注项

设置页上「新增关注项」（一问一答的向导，docs/additem.js）加进来的关注项，`notes` 里写着「从网页设置页加进来的」。
我说「完善关注项」时，找出这些项，检查向导生成的 `match`、`urgent_patterns`（正则是按选项拼的，可能太宽或太窄），
补上 `similar`、`status`、`theme`，缺的 `steam_appid` / `anilist_id` / `tmdb` / `site` 也补上，并把 `notes` 改成真正的背景说明。
向导的问题和选项（关注哪方面、要紧消息的词、不想看的词）都在 `docs/additem.js` 开头的 KINDS / EXCLUDES 里，要加选项改那里。
选项上 `rec: true` = 「不确定，你帮我定」时替我选它；`when: about(/…/)` = 只在名字或维基数据说明里有这些词时才出现（比如「猫相关的」只给跟猫有关的东西），别再给所有东西都出同一套选项。
