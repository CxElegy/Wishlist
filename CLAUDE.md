# 给 Claude 的约定

## 主动告诉我有哪些 MCP 连接器能用

- 任务能靠某个 MCP 连接器更方便地完成时（比如改数据库用 Supabase、看 PR 用 GitHub），**先告诉我有这个连接器**，
  不要让我自己去 SQL Editor / 网页手动操作。
- 连接器已经连上：直接说「可以用 XX 连接器帮你做」，然后去做。
- 还没连上：说清楚是哪个连接器、能帮上什么，并给出连接地址 https://claude.ai/customize/connectors
  （连好后要开新会话才会加载）。
- 已连上的连接器：Supabase（项目 `bzokpnbcjscbcehdxtjq`，表 `feedback` / `news` / `sizes`）、GitHub。

## 篇幅 S / M / L

每个关注项的篇幅存在 Supabase 的 `sizes` 表，我自己在网页的 ⚙ 设置页（docs/settings.html，要口令）也能改。
我说「把 XX 改成 L」时，用 Supabase 连接器直接改表；
连接器不可用时改 `items.yaml` 里的 `size`，下次出刊会自动同步进数据库。

## 每次回复都贴链接

- 回复里只要提到网页、PR、设置页，就把可以直接点开的链接贴上：
  简报 https://cxelegy.github.io/Wishlist/ 、设置页 https://cxelegy.github.io/Wishlist/settings.html 、
  愿望清单 https://cxelegy.github.io/Wishlist/wishlist.html 、PR 用完整网址。
- 合并 PR 后网页大约 1 分钟更新（`.github/workflows/render.yml` 只重新生成网页）；
  确认网页已经更新了再告诉我，并附上链接。收集新闻、发通知仍由「关注清单通信」慢慢跑。
