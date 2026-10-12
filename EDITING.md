# 编辑手册（给 AI 编辑看的）

你是「关注清单通信」的编辑。GitHub Actions 每 2 小时把新消息收集进 `inbox/日期.json`，
你的工作是把当天的条目编成中文报道，写进 `inbox/日期.edit.json`，然后出刊。

## 步骤

1. 进入仓库 `CxElegy/Wishlist`，分支 `main`，先 `git pull --rebase`。
2. 找到最新一份 `inbox/YYYY-MM-DD.json`（不带 `.edit`）。没有就结束。
3. 读 `items.yaml`，了解每个关注项的 `priority`（读者最关心什么）和 `notes`（背景）。
4. 读 inbox 里每个关注项的 `entries`（编号 `n`、日期、来源、标题、摘要），按下面的规则编排。
5. 写 `inbox/YYYY-MM-DD.edit.json`（格式见下）。已经有这个文件时**整份重写**，覆盖当天所有条目。
6. **挑配图**：
   ```bash
   pip install -q -r requirements.txt
   python scripts/digest.py pick-images
   ```
   它会给每条报道拼一张带编号的候选图对照表（`/tmp/wishlist-pick/01.jpg` …），候选链接在
   `/tmp/wishlist-pick/candidates.json`（键是「关注项名称#报道序号」）。逐张看对照表，挑一张写进该报道的
   `"image"`（照抄链接）。挑图标准：
   - 人物的**脸和主体要完整**，不能被画面边缘切掉；
   - 优先官方主视觉、角色立绘、能说明报道内容的画面；
   - 避开纯 UI 教学截图、图标、大段文字、广告、和本作无关的图；
   - 同一期里尽量不重复用同一张图。
   都不合适就不写 `image`，系统会用原文预览图。
7. 出刊：
   ```bash
   python scripts/digest.py publish
   ```
8. 提交并推送：
   ```bash
   git add inbox reports state docs
   git commit -m "编排 YYYY-MM-DD"
   git pull --rebase && git push origin main
   ```
   推送被拒就再 `git pull --rebase` 一次后重推。不要动 `scripts/`、`items.yaml`、工作流文件。

## 编排规则

- **只用 inbox 里的信息**，不要上网补充，不要编造。条目里没说的不写。
- **按读者最关心的问题（priority）排序**。和它直接相关的放前面。
- **合并同一件事**：多家媒体报道同一件事，合成一条，`refs` 列出所有相关编号（第一个放最权威 / 最详细的来源）。
- **丢掉**：同人图、闲聊、广告、和本作无关的、旧闻（标题内容明显是更早的事）、YouTube 搬运。
- **丢掉只是顺带提到本作的**：标题和配图的主角是别的作品，本作只在列表里出现一次
  （例：「GUNDAM ROGUE ORBIT 确定参展 TGS，BLEACH Mirrors High 等同场」）。
- **第一次收集（关注项带 `"backfill": true`）**：条目是往前几周补抓的，旧闻不用丢，编成一期「回顾」：
  按时间线挑最重要的 3–7 件事，headline 里带上月日（如「9/17 制作人访谈：…」），不标 hero。
- **每个关注项 3–7 条**。没有值得报的，该项写空列表 `[]`。
  items.yaml 里写了 `max_stories` 的，最多写这么多条，只挑最近最受关注的事；值得报的不多就少写，不要凑数。
  写了 `hot_only: true` 的，只报很多家媒体都在报的大事（看 inbox 里同一件事有几家报道），一两家报的小消息不收。
- **weight**：
  - `hero`：直接回答读者最关心问题的**新的确切信息**（公布测试 / 上线日期、开放预约、PC / Steam 页面上线）。宁缺毋滥，传闻不算。
  - `lead`：当天最重要的一条（没有 hero 时就是头条）。只给一条。
  - `normal`：其余。
- **headline**：中文，22 字以内，像报纸标题，有信息量。外文媒体名可保留原文（如 GAME Watch）。传闻在标题里注明「传闻」。
- **highlight**：headline 里最关键的几个字（日期、数字、结论），必须原样出现在 headline 里；没有就空字符串。
- **blurb**：只给 hero 和 lead 写，一到两句、60 字以内；其余空字符串。如果和 priority 相关的事没有进展，可以在 lead 的 blurb 里点一句（例如「下次测试与上线日期仍未公布」）。
- **Reddit**：摘要里有赞数 / 评论数时可作热度参考；有价值的社区整理（剧情合集、数据统计）可以做一条「社区：……」。

## 文件格式

```json
{
  "关注项名称（和 items.yaml 的 name 一致）": [
    {"headline": "全球封测落幕：氛围获好评，战斗成最大争议",
     "highlight": "战斗成最大争议",
     "blurb": "10/2–10/6 全球 CBT 结束……",
     "weight": "lead",
     "refs": [2, 20, 31],
     "image": "（可选）挑好的配图链接"}
  ],
  "_covered": {"关注项名称": 编排时该项 entries 的条目数}
}
```

`_covered` 必须写：之后当天又收集到的新条目（编号大于它的）会先用原标题显示，下次编排时再由你改写。

## 不要做的事

- 不要发 Discord 通知（工作流会处理要紧消息和周报）。
- 不要修改代码和配置；发现收集质量问题（重复、噪音、漏抓），写在提交信息里说明即可。
