# 版面模版手册（给 AI 编辑看的）

首页上每个关注项一个版面。版面的**配色**来自作品自己（封面取色或 `items.yaml` 的 `theme`），
版面的**模版**（底纹、题字形状、照片边框、标题旁的装饰字）按题材来：`items.yaml` 里关注项的 `motif` 写模版 id，
模版的样子在 `templates/<id>.css`，一览在 `templates/index.yaml`。

现在的规矩：**每个新关注项都设计一个模版；和已有的相似就合并成一个**。
等模版库里的样本够多了，新关注项就直接从库里选（`index.yaml` 的 `for` 就是选的依据）。

## 什么时候做

`items.yaml` 里 `notes` 有「从网页设置页加进来的」、但还没有 `motif` 的关注项。
设置页一加进来，工作流就叫你（AI 编辑）来；每天两次的定时编排也先检查一遍。
在你设计好之前，这一项先按 `type` 借用 `index.yaml` 里 `defaults` 对得上的模版（见 `render.template_for`），所以首页不会是光板。

## 步骤

1. **看清这一项是什么气质**：读 `items.yaml` 里它的 `type`、`subtitle`、`keywords`、`priority`、`notes`、`site`，
   和今天 `inbox/日期.json` 里它的标题。用三个词概括（例：「热血 · 黑白漫画 · 暴力美学」「慵懒 · 黄色 · 治愈角色」）。
2. **先找能合并的**：对照 `templates/index.yaml` 每个模版的 `for`。
   - 气质一样 → **直接用**：`motif` 写那个 id，并在那个模版的 `for` 里补上这个题材。
   - 差一点 → **改那个模版**让它能兼容两者，但不能让已经在用它的作品变难看（改完把用它的版面都看一遍）。
   - 都不像 → **新做一个**。
   模版太多（超过 12 个）时，优先合并。
3. **新做模版**：
   - 写 `templates/<id>.css`。id 用小写英文（如 `lazy`、`noir`）。第一行注释写「版面模版「id」：一句话说明」。
   - 只写 `.m-<id>` 开头的规则，**只用作品的配色变量**：`--bg --fg --acc --abg --afg --aacc --line`（和 `--font-sans` 等字体变量）。
     不写死颜色——同一个模版换个作品就是另一套颜色，这样才能合并。
   - 能改的：版面底纹（`.m-<id>{background-image:…}`）、题字形状（`.m-<id> .band .title`）、照片边框和裁切（`.m-<id> .card .pic`）、
     标题旁的装饰字（`.m-<id> .deco`）、日期角标（`.m-<id> .when b`）。
     不改的：网格、卡片排列、字号（不小于 10px）、行数——版面的骨架所有作品一样。
   - 参照现有的五个：`retro`（星星 + 角丸题字）、`manga`（网点 + 斜分格 + 擬音字）、`pop`（水玉 + 圆角）、
     `film`（胶片孔 + 粗黑边）、`street`（斜体 + 警示条纹）。
   - 在 `templates/index.yaml` 加一条：`id`、`name`（中文名）、`for`（适合什么题材，一句话）、`deco`（标题旁的装饰字，可空）、
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
6. **提交**（和编排一起提交也行）：
   ```bash
   git add templates items.yaml docs
   git commit -m "版面模版：<关注项> → <id>"
   git pull --rebase && git push origin main
   ```
