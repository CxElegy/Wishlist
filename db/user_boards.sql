-- お客さまの版面（2026-10-22，用户定的：お客さまが選んだもののうち店長の関注項にないものも、本人のために記事を集める。AI なし・規則だけ）。
-- 書くのは GitHub Actions（secret key、scripts/userfeed.py）だけ。読むのはログインした本人だけ（my_boards()）。
-- リポジトリ（公開）・GitHub Pages（公開）には入れない（LOGIN.md 第 2 步「本人のページは本人だけ」）。
-- account = 'u_' || md5(小文字のメール) の先頭 16 字（private.user_account）。店長の account（test1）とは混ざらない。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（Claude 可以用 Supabase 连接器代为执行）。
-- 戻し方（データごと消える・破壊的なので運営者が SQL Editor で）：
--   drop function if exists public.my_boards(); drop function if exists public.userfeed_users(int, int);
--   drop function if exists private.user_account(text); drop table if exists public.user_boards;

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
-- 足したもの（2026-10-22 の見直し）：state = ok（探した）／ limit（1 人 30 版面の上限を超えたので集めない、userfeed.MAX_BOARDS_PER_USER）
alter table public.user_boards add column if not exists state text not null default 'ok' check (state in ('ok', 'limit'));
-- 足したもの（2026-10-23）：続けて取れなかった回数（取れたら 0）。0 件で FAIL_SHOW（userfeed.py、5）回未満なら網页は「集めています」のまま
alter table public.user_boards add column if not exists fails int not null default 0;

alter table public.user_boards enable row level security;   -- ポリシーなし：secret key だけが読み書きする（網页は my_boards() で）
revoke all on public.user_boards from anon, authenticated;

create or replace function private.user_account(p_email text)
returns text language sql immutable set search_path = '' as $$
  select 'u_' || left(md5(lower(btrim(coalesce(p_email, '')))), 16) $$;

-- だれのために集めるか（userfeed.py が secret key で読む。網页からは呼べない）：
-- Supabase Auth のユーザーがいて（止められていない）、一度はログインした人だけ。だれでも呼べる登録の関数（user_signup）で作っただけの行・
-- 他人のメールで書き換えた好みでは、Actions の検索を使わせない。登録の古い順（大量の新しい登録が、先にいる人を押し出さない）。PostgREST の上限 1000 行に合わせて p_limit・p_offset で読む
create or replace function public.userfeed_users(p_limit int default 1000, p_offset int default 0)
returns table (email text, prefs jsonb, created_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select u.email, u.prefs, u.created_at
    from public.app_users u
   where u.left_at is null and u.email is not null
     and exists (select 1 from auth.users a
                  where lower(a.email) = lower(u.email) and (a.banned_until is null or a.banned_until < now())   -- 止める期間が終わった人は戻す
                    and a.last_sign_in_at is not null)
   order by u.created_at, u.name_key
   limit least(greatest(coalesce(p_limit, 1000), 1), 1000) offset greatest(coalesce(p_offset, 0), 0) $$;

-- ログインした本人の版面だけ。いま選んでいるもの（prefs.picks）の順に返す。名前は前後の空白（半角・全角・タブ・改行・NBSP）を取って 80 字まで
-- （userfeed.pick_name・TRIM と同じ文字。btrim の既定は半角の空白だけなので、文字を並べて渡す）、
-- 空白・大小だけ違う同じ名前は最初の 1 つ。板块は本人が選んだもの（p.sec）を先に。
-- state：wait = まだ行がない（集めています）／ none = 探したが 0 件／ ok = 記事あり／ limit = 上限を超えたので集めない。
-- 店長のページに版面があるものは行がない（網页は店長の版面を出す。AUTH_JS の shopHit）。
-- 返り値：{"boards": [{"name", "sec", "state", "stories": [...], "found", "checked", "updated"}]}。ログインしていなければ null
create or replace function public.my_boards()
returns jsonb language sql stable security definer set search_path = '' as $$
  with me as (
    select u.prefs, private.user_account(u.email) as acct
    from public.app_users u
    where (select auth.uid()) is not null
      and lower(u.email) = lower((select auth.jwt()) ->> 'email') and u.left_at is null
    limit 1
  ), raw as (
    select left(btrim(x.value ->> 'name', E' \t\n\r\f\x0b\u3000\u00a0'), 80) as name, x.value ->> 'sec' as sec, x.ordinality as pos
    from me, jsonb_array_elements(case when jsonb_typeof(me.prefs -> 'picks') = 'array' then me.prefs -> 'picks' else '[]'::jsonb end)
         with ordinality as x(value, ordinality)
    where jsonb_typeof(x.value) = 'object' and btrim(coalesce(x.value ->> 'name', ''), E' \t\n\r\f\x0b\u3000\u00a0') <> ''
  ), picks as (
    select distinct on (lower(regexp_replace(r.name, '\s', '', 'g'))) r.name, r.sec, r.pos
    from raw r order by lower(regexp_replace(r.name, '\s', '', 'g')), r.pos
  )
  select case when not exists (select 1 from me) then null else jsonb_build_object('boards', coalesce((
    select jsonb_agg(jsonb_build_object(
             'name', p.name, 'sec', coalesce(p.sec, b.sec),
             'state', case when b.account is null then 'wait' when b.state = 'limit' then 'limit'
                           when jsonb_array_length(b.stories) = 0 and b.fails between 1 and 4 then 'wait'   -- 取れなかっただけ：まだ集めている
                           when jsonb_array_length(b.stories) = 0 then 'none' else 'ok' end,
             'stories', coalesce(b.stories, '[]'::jsonb),
             'found', coalesce(b.found, 0), 'checked', b.checked_at, 'updated', b.updated_at) order by p.pos)
    from picks p cross join me
    left join public.user_boards b on b.account = me.acct and b.item = p.name
  ), '[]'::jsonb)) end $$;

-- 好みの書き換え（db/auth.sql の user_set_prefs）はログインなしで呼べる：Auth のユーザーがいる人の picks は、ここでは変えさせない
-- （本人がログインして my_keywords_set で変える）。言語など picks 以外はそのまま
create or replace function public.user_set_prefs(p_name text, p_prefs jsonb)
returns void language plpgsql security definer set search_path = '' as $$
declare n text := lower(btrim(coalesce(p_name, ''))); v jsonb := coalesce(p_prefs, '{}'::jsonb);
begin
  if jsonb_typeof(v) <> 'object' or length(v::text) > 8000 then
    raise exception '設定の形が正しくありません';
  end if;
  if exists (select 1 from auth.users a where lower(a.email) = n) then v := v - 'picks'; end if;
  update public.app_users set prefs = prefs || v, last_seen = now()
   where name_key = n and left_at is null;
end $$;

revoke all on function public.my_boards() from public, anon;
revoke all on function public.userfeed_users(int, int) from public, anon, authenticated;
revoke all on function private.user_account(text) from public, anon, authenticated;
grant execute on function public.my_boards() to authenticated;
grant execute on function public.userfeed_users(int, int) to service_role;
