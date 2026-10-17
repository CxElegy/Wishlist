-- 版面の「更新中」の帯（render.BUSY_JS）が読む：いま裏でどの版面を作り直しているか。
-- 収集（GitHub Actions）が版面ごとに書く（digest.live_mark）：探し始め → 新着あり / なし → 出刊。
-- 網页は live_status() で読むだけ（publishable key）。表そのものは網页から読めない・書けない。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（Claude 可以用 Supabase 连接器代为执行）。

create table if not exists public.live_status (
  board text not null,              -- 関注項の名前（items.yaml の name）
  proc text not null,               -- collect / edit / emblem …
  state text not null,              -- fetch（記事を探している）/ found（新着あり・反映待ち）
  found int not null default 0,     -- 新着の件数
  started_at timestamptz not null default now(),
  eta_at timestamptz,               -- 網页に出るまでの予想時刻
  updated_at timestamptz not null default now(),
  primary key (board, proc)
);
alter table public.live_status enable row level security;   -- ポリシーなし = 網页からは直接触れない

create or replace function public.live_status()
returns table (board text, proc text, state text, found int, started_at timestamptz, eta_at timestamptz)
language sql stable security definer set search_path = public as $$
  select board, proc, state, found, started_at, eta_at from public.live_status
  where updated_at > now() - interval '45 minutes'
  order by started_at;
$$;

revoke all on function public.live_status() from public;
grant execute on function public.live_status() to anon;
