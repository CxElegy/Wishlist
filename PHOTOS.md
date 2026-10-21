# 照片加愿望（给 Claude 定时任务看的）

愿望清单页的「📷 拍照加愿望」把照片存进数据库；GitHub Actions 每 2 小时把新照片导出到 `inbox/photos/`：
每张一对文件 `<编号>.jpg` + `<编号>.json`（`status`：想要 / 纠结，`note`：上传时写的备注，`uploaded`：上传时间）。
你的工作是认出照片里的东西，加进 `wishlist.yaml`，然后删掉处理过的照片文件。

## 步骤

> 跑得久的命令直接在前台运行（Bash 的 timeout 设 600000），不要放到后台再用 `pgrep` / `sleep` 循环去等。

1. 进入仓库 `CxElegy/Wishlist`，分支 `main`，先 `git pull --rebase origin main`，再 `pip install -q -r requirements.txt`。
2. 看 `inbox/photos/` 里有没有 `.json`。**没有就什么都不改，直接结束。**
3. 每一张照片：
   1. 用 Read 看 `<编号>.jpg`，结合 `.json` 里的 `note`，认出是什么东西：品牌、型号 / 系列、颜色、规格。
      照片里有价签、包装、商品页截图时，把价格和货币也读出来；拿不准就在 `note` 里写明是推断。
   2. 按 `.claude/skills/wishlist/SKILL.md` 的「加一件」整理：
      - **图片**：用 Pillow 从照片里只裁出这件东西（去掉背景杂物和文字），存成 `docs/home/wishlist/<英文短名>.jpg`，质量 90；裁完用 Read 看一眼。
      - **字段**：`name`、`price` / `currency`、`specs`、`shop`、`url`（能确定商品页就填，找不到可以不填）、`added`（今天，北京时间）、
        `likes` / `basics`（喜好标签，「我会喜欢？」靠它推荐）、和某个关注项有关就填 `watch`。
      - **`status`**：照抄 `.json` 里的（想要 / 纠结）。纠结的再按 SKILL.md 帮忙找 2–3 个类似的好产品写进 `alternatives`。
      - **`photo`**：写这张照片的编号（数字），网页的排队列表靠它显示「已加入」。
      - **`note`**：一句话备注；用户的备注要保留意思（例如「在表参道看到的，想要黑色」）。
   3. 实在认不出（照片太糊、看不出是什么）：照样加一条，`name` 写你看到的样子（如「白色陶瓷杯（照片里认不出品牌）」），
      `note` 写明认不出、请用户补充，`photo` 照填。不要跳过。
   4. 删掉这张照片的 `.jpg` 和 `.json`。
4. 运行 `python scripts/digest.py render` 重新生成网页，确认 `docs/home/wishlist.html` 里有新加的东西。
5. 提交并推送：
   ```bash
   git add wishlist.yaml docs inbox/photos
   git commit -m "照片加愿望：<名字>、<名字>"
   git pull --rebase origin main && git push origin main
   ```
   推送被拒就再 `git pull --rebase` 一次后重推。

## 不要做的事

- 不要修改 `scripts/`、`items.yaml`、`.github/`。
- 不要发 Discord（推送后工作流会发愿望清单通知）。
- 不要开 PR。
- 不要去动数据库：网页上的「已加入」由下一次 Actions 按 `photo` 编号自动标记。
