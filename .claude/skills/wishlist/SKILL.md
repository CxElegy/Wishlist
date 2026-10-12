---
name: wishlist
description: 把用户喜欢的东西加进愿望清单（wishlist.yaml），网页上会显示、Discord 会通知。用户说「加进 wishlist」「加到愿望清单」「这个我想要」并附上截图或链接时使用；也用于把某件标成已入手 / 没买到、或删掉。
---

# 愿望清单

数据在仓库根目录的 `wishlist.yaml`，图片放在 `docs/wishlist/`。推送到 `claude/sharp-gauss-osunmb` 后，
工作流会自动重新生成网页（子页面 `docs/wishlist.html`，主页报头右上角和左侧目录底部有入口）并在 Discord 发一条带大图的通知。

## 加一件

1. **找准是什么**：从截图 / 链接里读出名字、价格、规格（容量、尺寸、颜色……）、在哪里卖。
   - 货币要有依据（繁体字 + 「毫升」+ 星巴克 → 多半是台湾 NT$）；拿不准就在 `note` 里写明是推断。
   - 可以在 `inbox/*.json` 里搜一下，收集到的消息里常常有原文链接，填进 `url`。
2. **图片**：
   - 用户给了截图：用 Pillow 只裁出商品本身（去掉文字和留白），存成 `docs/wishlist/<英文短名>.jpg`，质量 90。
   - 只有网址：下载商品图同样存进 `docs/wishlist/`（别直接引用外站图，可能防盗链或失效）。
   - 裁完用 Read 看一眼，确认商品完整、没被切掉。
3. **写进 `wishlist.yaml`**（字段说明在文件顶部），`added` 填今天，`status: 想要`。
   和某个关注项有关（如星巴克马克杯）就填 `watch`，版面上会顺带显示那个关注项的最新消息。
4. 运行 `python scripts/digest.py render`，截图检查 `docs/wishlist.html`，然后提交并推送。
   不要自己发 Discord：推送触发的工作流会发（`state/known_wishlist.json` 记录已通知的）。

## 改状态 / 删除

- 买到了：`status: 已入手`；没买到：`status: 没买到`。
- 删除：直接从 `wishlist.yaml` 里删掉那一项（图片也可以一起删）。
