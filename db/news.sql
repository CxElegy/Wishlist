-- 收集到的每条消息（inbox/ 里的原始条目）。在 Supabase → SQL Editor 里整段粘贴、运行一次即可。
--
-- GitHub Actions 每次收集后用 secret key（仓库 Secret SUPABASE_SERVICE_KEY）写进来；
-- 第一次运行会把 inbox/ 里已有的全部消息补进来。网页（publishable key）读不到也写不了这张表。
-- 同一个关注项的同一条链接只存一行，再次收集到时更新标题、摘要等，first_seen 保留第一次收集的时间。

create table if not exists public.news (
  item          text not null,                 -- 关注项（items.yaml 的 name）
  url           text not null,
  title         text not null,
  source        text,                          -- 媒体名
  summary       text,
  image         text,                          -- 配图链接
  published_at  timestamptz,                   -- 原文发布时间
  collected_on  date not null,                 -- 收进哪一期（inbox 的日期）
  urgent        boolean not null default false,  -- 要紧消息（当天发 Discord 的那种）
  backfill      boolean not null default false,  -- 新加关注项时往前补抓的旧闻
  first_seen    timestamptz not null default now(),
  primary key (item, url)
);

create index if not exists news_collected_on on public.news (collected_on desc);
create index if not exists news_item_published on public.news (item, published_at desc);

alter table public.news enable row level security;   -- 不设任何规则：只有 secret key 能读写
