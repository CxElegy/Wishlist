-- 管理ページの「ライブログ」に、裏の作業（小元素の自動補完など）の 1 行 1 行をその場で流す（2026-10-22，用户定的：
-- 「今すぐ再挑戦」を押したら、AI を使わない作業なので資源を気にせず、何をしているかをログで見せる）。
-- 書く人：GitHub Actions（secret key で直接 insert。digest.supabase が account を入れる）。
-- 網页は live_log_since() で読むだけ（publishable key）。表そのものは網页から読めない・書けない。
-- 古い行（2 日より前）は書く側（emblem_fill.background の始め）が消す。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（Claude 可以用 Supabase 连接器代为执行）。

create table if not exists public.live_log (
  id      bigint generated always as identity primary key,
  account text not null default 'test1',
  at      timestamptz not null default now(),
  proc    text not null check (length(proc) <= 20),        -- emblem など（livelog.PROCS）
  board   text check (length(board) <= 80),                -- 関注項の名前（なければ全体の行）
  level   text not null default 'info' check (level in ('info', 'ok', 'warn', 'error')),
  text    text not null check (length(text) <= 400)
);
create index if not exists live_log_account_id on public.live_log (account, id);
alter table public.live_log enable row level security;   -- ポリシーなし = 網页からは直接触れない

-- p_after より新しい行（最新 300 行まで、古い順）。最初は p_after = 0 で直近の分
create or replace function public.live_log_since(p_account text, p_after bigint default 0)
returns table (id bigint, at timestamptz, proc text, board text, level text, text text)
language sql stable security definer set search_path = '' as $$
  select * from (
    select l.id, l.at, l.proc, l.board, l.level, l.text from public.live_log l
    where l.account = private.acct(p_account) and l.id > coalesce(p_after, 0) and l.at > now() - interval '2 days'
    order by l.id desc limit 300) x
  order by x.id $$;
revoke all on function public.live_log_since(text, bigint) from public;
grant execute on function public.live_log_since(text, bigint) to anon, authenticated;
