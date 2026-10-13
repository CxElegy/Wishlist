-- 编排后的报道（reports/ 里网页上显示的那些）和价格 / 状态的历史。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可。两张表都只有 secret key（GitHub Actions）能读写。

-- 每一期的报道：同一期重新编排后整期替换。pos 是这一项在这一期里的顺序（从 0 开始）
create table if not exists public.stories (
  issue_date  date not null,                 -- 哪一期（reports 的日期）
  item        text not null,                 -- 关注项
  pos         smallint not null,
  headline    text not null,                 -- 编排后的中文标题
  highlight   text,                          -- 标题里加粗的关键字
  blurb       text,                          -- 一两句摘要（头条 / 重大才有）
  weight      text,                          -- hero / lead / normal
  url         text,
  image       text,
  story_date  date,                          -- 消息本身的日期
  synced_at   timestamptz not null default now(),
  primary key (issue_date, item, pos)
);
create index if not exists stories_item_issue on public.stories (item, issue_date desc);
alter table public.stories enable row level security;

-- 价格 / 状态的历史：值变了才新增一行（第一次看到也记一行）。
-- kind：steam（Steam 价格）、anilist / tmdb（播出状态）、wishlist（愿望清单里写的价格）
create table if not exists public.price_history (
  id          bigint generated always as identity primary key,
  observed_at timestamptz not null default now(),
  item        text not null,
  kind        text not null,
  label       text,
  value       text not null,                 -- 显示用的文字，如「¥ 4378」「连载中 · 第 3 集」
  amount      numeric,                       -- 能看出数字时的价格
  currency    text
);
create index if not exists price_history_item on public.price_history (item, label, observed_at desc);
alter table public.price_history enable row level security;
