-- お客さまの版面（2026-10-22，用户定的：お客さまが選んだもののうち店長の関注項にないものも、本人のために記事を集める。AI なし・規則だけ）。
-- 書くのは GitHub Actions（secret key、scripts/userfeed.py）だけ。読むのはログインした本人だけ（my_boards()）。
-- リポジトリ（公開）・GitHub Pages（公開）には入れない（LOGIN.md 第 2 步「本人のページは本人だけ」）。
-- account = 'u_' || md5(小文字のメール) の先頭 16 字（private.user_account）。店長の account（test1）とは混ざらない。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（Claude 可以用 Supabase 连接器代为执行）。
-- 戻し方（データごと消える・破壊的なので運営者が SQL Editor で）：
--   drop function if exists public.my_boards(); drop function if exists private.user_account(text); drop table if exists public.user_boards;

create table if not exists public.user_boards (
  account     text not null check (account ~ '^u_[0-9a-f]{16}$'),
  item        text not null check (length(item) between 1 and 80),   -- 選んだものの名前（prefs.picks の name）
  sec         text,                                                  -- 板块（prefs.picks の sec）
  stories     jsonb not null default '[]'::jsonb,                    -- [{title, url, source, date, image, summary}]（新しい順・12 件まで）
  found       int not null default 0,                                -- この回に新しく見つかった件数
  checked_at  timestamptz not null default now(),                    -- 最後に探した時刻
  updated_at  timestamptz,                                           -- 最後に記事が増えた時刻（まだ 1 件もなければ null）
  primary key (account, item)
);

alter table public.user_boards enable row level security;   -- ポリシーなし：secret key だけが読み書きする（網页は my_boards() で）
revoke all on public.user_boards from anon, authenticated;

create or replace function private.user_account(p_email text)
returns text language sql immutable set search_path = '' as $$
  select 'u_' || left(md5(lower(btrim(coalesce(p_email, '')))), 16) $$;

-- ログインした本人の版面だけ。いま選んでいるもの（prefs.picks）の順に、まだ探していないものは stories 空・checked null で返す。
-- 返り値：{"boards": [{"name", "sec", "stories": [...], "found", "checked", "updated"}]}。ログインしていなければ null
create or replace function public.my_boards()
returns jsonb language sql stable security definer set search_path = '' as $$
  with me as (
    select u.prefs, private.user_account(u.email) as acct
    from public.app_users u
    where (select auth.uid()) is not null
      and lower(u.email) = lower((select auth.jwt()) ->> 'email') and u.left_at is null
    limit 1
  ), picks as (
    select x.value ->> 'name' as name, x.value ->> 'sec' as sec, x.ordinality as pos
    from me, jsonb_array_elements(case when jsonb_typeof(me.prefs -> 'picks') = 'array' then me.prefs -> 'picks' else '[]'::jsonb end)
         with ordinality as x(value, ordinality)
    where coalesce(x.value ->> 'name', '') <> ''
  )
  select case when not exists (select 1 from me) then null else jsonb_build_object('boards', coalesce((
    select jsonb_agg(jsonb_build_object(
             'name', p.name, 'sec', coalesce(b.sec, p.sec), 'stories', coalesce(b.stories, '[]'::jsonb),
             'found', coalesce(b.found, 0), 'checked', b.checked_at, 'updated', b.updated_at) order by p.pos)
    from picks p cross join me
    left join public.user_boards b on b.account = me.acct and b.item = p.name
  ), '[]'::jsonb)) end $$;

revoke all on function public.my_boards() from public, anon;
revoke all on function private.user_account(text) from public, anon, authenticated;
grant execute on function public.my_boards() to authenticated;
