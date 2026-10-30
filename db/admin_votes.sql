-- 管理ページ②投票（2026-10-31）：全アカウントの 👍👎 を店長が読む。account ごとに「今の票」（同じ記事は最後の票・撤銷 0 は数えない）の 👍 と 👎、
-- この 7 日に押した回数、最後の投票、最近の票 8 件。店長（is_admin）だけ。足しただけ（表の形は変えない）。
-- 戻し方：drop function public.admin_votes();
create or replace function public.admin_votes()
returns table (account text, up int, down int, week int, last_at timestamptz, recent jsonb)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query
    with cur as (
      select distinct on (f.account, f.url) f.account, f.url, f.vote, f.title, f.work, f.kind, f.created_at
        from public.feedback f order by f.account, f.url, f.created_at desc, f.id desc),
    live as (select * from cur where cur.vote <> 0)
    select a.account,
           (select count(*)::int from live l where l.account = a.account and l.vote > 0),
           (select count(*)::int from live l where l.account = a.account and l.vote < 0),
           (select count(*)::int from public.feedback f where f.account = a.account and f.created_at > now() - interval '7 days'),
           (select max(f.created_at) from public.feedback f where f.account = a.account),
           coalesce((select jsonb_agg(jsonb_build_object('vote', r.vote, 'title', r.title, 'work', r.work, 'url', r.url, 'at', r.created_at))
                       from (select * from live l where l.account = a.account order by l.created_at desc limit 8) r), '[]'::jsonb)
      from (select distinct f.account from public.feedback f) a
     order by 2 desc, 1;
end;
$$;
revoke all on function public.admin_votes() from public;
revoke all on function public.admin_votes() from anon;
grant execute on function public.admin_votes() to authenticated;
