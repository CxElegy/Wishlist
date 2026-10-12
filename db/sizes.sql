-- 每个关注项在网页上的篇幅。在 Supabase → SQL Editor 里整段粘贴、运行一次即可。
--
--   S  少：每期最多 3 条，网页上大约一行
--   M  中等：每期最多 5 条（表里没有的关注项也按 M）
--   L  多：每期最多 8 条，网页上满满一整屏
--
-- 以后要改，直接在 Supabase 的 Table Editor 里改 size 那一格（或新加一行，item 填 items.yaml 里的 name），
-- 下一次定时任务（每 2 小时）出刊时生效。网页上不显示篇幅。
-- GitHub Actions 用 secret key（仓库 Secret SUPABASE_SERVICE_KEY）读；网页（publishable key）读不到也写不了。

create table if not exists public.sizes (
  item        text primary key,                               -- 关注项（items.yaml 的 name）
  size        text not null default 'M' check (size in ('S', 'M', 'L')),
  updated_at  timestamptz not null default now()
);

alter table public.sizes enable row level security;   -- 不设任何规则：只有 secret key 能读写

insert into public.sizes (item, size) values
  ('Astrae Oratio', 'L'),
  ('BLEACH Mirrors High', 'M'),
  ('GTA 6', 'M'),
  ('MMORPG 新作', 'M'),
  ('滑雪', 'L'),
  ('漫威电影', 'M'),
  ('FROM', 'S'),
  ('ILLIT', 'L'),
  ('星巴克马克杯', 'M'),
  ('猫用品', 'M'),
  ('日本顶级网球赛事', 'L'),
  ('三星手机', 'M'),
  ('gelato pique', 'M')
on conflict (item) do nothing;
