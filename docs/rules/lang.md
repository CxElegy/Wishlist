# 读者的语言

## 读者的语言：主言語・副言語（2026-10-17）

- 设置在 `items.yaml` 的 `settings.languages`：`primary: ja`（主言語，网页 UI 也用它），`secondary: [en, zh, ko]`（副言語，按顺序）。以后每个用户在 ⚙ 设置页自己选（还没做）。
- **同一件事有几种语言的报道，只留主言語那条**；没有主言語的按副言語顺序挑；主言語・副言語以外的语言不上版面。
- 三处把关：① AI 编辑（`EDITING.md`「不同语言的同一件事只写一条」，跨天也算）② 出刊 `publish`（`lang.prefer_ref` 把标题换成更好语言的出典原题、`lang.dedupe`）
  ③ 生成网页 `render.collect`（跨期去重）+ `_agenda`（同作品・同日・同标签只出一次）。规则全在 `scripts/lang.py`（不用 AI）：
  语言按文字种类判断；同一件事 = 同作品、10 天内、版本号 / 标题里的月日 / event 日期相同。误判时改 `lang.py`，在 `tests/test_lang.py` 加例子。
