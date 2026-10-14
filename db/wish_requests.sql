-- 新闻卡片上「♥ 加入心愿单」的请求。在 Supabase → SQL Editor 里整段粘贴、运行一次即可。
--
-- 网页（publishable key）只能新增请求（读不到、改不了）；GitHub Actions 每次运行用 secret key 读出待处理的，
-- 加进 wishlist.yaml 后标成 done（已经在愿望清单里的标成 skipped）。

create table if not exists public.wish_requests (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  url         text not null check (length(url) <= 2000),     -- 新闻链接
  title       text not null check (length(title) <= 500),    -- 新闻标题（先当愿望的名字，之后再整理）
  work        text check (length(work) <= 200),              -- 来自哪个关注项
  image       text check (length(image) <= 2000),            -- 新闻配图
  source      text check (length(source) <= 200),
  status      text not null default 'pending' check (status in ('pending', 'done', 'skipped')),
  handled_at  timestamptz
);

alter table public.wish_requests enable row level security;

drop policy if exists "网页只能新增加入心愿单的请求" on public.wish_requests;
create policy "网页只能新增加入心愿单的请求" on public.wish_requests
  for insert to anon with check (status = 'pending' and handled_at is null);

grant insert (url, title, work, image, source) on public.wish_requests to anon;
