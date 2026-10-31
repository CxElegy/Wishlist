-- 管理ページ②：全アカウントの「置き方・関注項の中身」を店長が読む（2026-10-31）。店長（is_admin）だけ。足しただけ（表の形は変えない）。
-- 名前・メールは出さない。follows の section（置く板块）・subs（小分類）・media（見たい種類）・also（乗換駅）を account ごとに数える。
-- 戻し方：drop function public.admin_follow_detail();
create or replace function public.admin_follow_detail()
returns table (account text, boards int, sections int, with_subs int, with_media int, with_also int)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query
    select f.account, count(*)::int,
           count(distinct f.section)::int,
           (count(*) filter (where f.subs is not null and f.subs <> '{}'::jsonb))::int,
           (count(*) filter (where f.media is not null and f.media <> '[]'::jsonb))::int,
           (count(*) filter (where f.also is not null and f.also <> '{}'::jsonb))::int
      from public.follows f group by f.account order by 1;
end;
$$;
revoke all on function public.admin_follow_detail() from public;
revoke all on function public.admin_follow_detail() from anon;
grant execute on function public.admin_follow_detail() to authenticated;
