-- 左の目次・版面の並びで使う「小分類の分け方」を、板块ごとに設定ページ（docs/settings.html）で選ぶ。
-- 分け方の候補は sections.yaml の schemes（ゲームなら「状態」「プラットフォーム」…）。表にない板块は候補の 1 番目。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（需要先运行过 db/instant.sql：选了就立刻重新生成网页）。
-- GitHub Actions は secret key で表を読む。網页（publishable key）は下の 2 つの関数だけ使える。

create table if not exists public.nav_schemes (
  section     text primary key,                 -- 板块（items.yaml の section：游戏 / 影视 …）
  scheme      text not null,                    -- 分け方の id（sections.yaml の schemes の id）
  updated_at  timestamptz not null default now()
);

alter table public.nav_schemes enable row level security;   -- 規則なし：secret key だけが直接読み書きできる

create or replace function public.get_nav_schemes()
returns table (section text, scheme text)
language sql stable security definer set search_path = ''
as $$ select n.section, n.scheme from public.nav_schemes n order by n.section $$;

create or replace function public.set_nav_scheme(p_section text, p_scheme text)
returns text
language plpgsql security definer set search_path = ''
as $$
begin
  if length(coalesce(p_section, '')) not between 1 and 40 or p_scheme !~ '^[a-z][a-z0-9_]{0,30}$' then
    raise exception '板块か分け方の名前が不正';
  end if;
  insert into public.nav_schemes (section, scheme, updated_at) values (p_section, p_scheme, now())
  on conflict (section) do update set scheme = excluded.scheme, updated_at = now();
  perform private.kick_github();   -- 立刻叫 GitHub 重新生成网页（db/instant.sql）
  return p_scheme;
end
$$;

revoke all on function public.get_nav_schemes() from public;
revoke all on function public.set_nav_scheme(text, text) from public;
grant execute on function public.get_nav_schemes() to anon, authenticated;
grant execute on function public.set_nav_scheme(text, text) to anon, authenticated;
