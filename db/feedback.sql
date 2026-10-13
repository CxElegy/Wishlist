-- 「我会喜欢？」的 👍 / 👎 投票表。在 Supabase → SQL Editor 里整段粘贴、运行一次即可。
--
-- 网页用公开的 publishable key（anon）只能「新增」投票，读不到、改不了、删不掉；
-- GitHub Actions 用 secret key（存在仓库 Secret SUPABASE_SERVICE_KEY）读出全部投票来学习。
-- 每次点击新增一行，同一条消息以最后一票为准：1 = 喜欢，-1 = 不感兴趣，0 = 撤销。

create table if not exists public.feedback (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  url        text not null check (length(url) <= 2000),
  vote       smallint not null check (vote in (-1, 0, 1)),
  kind       text check (kind in ('wish', 'follow', 'hesitate', 'story')),
                 -- wish = 按愿望清单挑的，follow = 同类新发现，hesitate = 纠结中那件的同类，story = 版面上的普通消息
  title      text check (length(title) <= 500),
  work       text check (length(work) <= 200),           -- 消息来自哪个关注项
  because    text check (length(because) <= 200),        -- 推荐理由里的那件愿望 / 关注项
  hits       text[] check (cardinality(hits) <= 20),     -- 命中的喜好标签
  words      text[] check (cardinality(words) <= 20)     -- 命中的具体关键词
);

alter table public.feedback enable row level security;

drop policy if exists "网页只能新增投票" on public.feedback;
create policy "网页只能新增投票" on public.feedback for insert to anon with check (true);

grant insert on public.feedback to anon;

-- 早先建的表（kind 只允许 wish / follow）：运行下面两行放宽
alter table public.feedback drop constraint if exists feedback_kind_check;
alter table public.feedback add constraint feedback_kind_check check (kind in ('wish', 'follow', 'hesitate', 'story'));
