-- 管理ページ②：全アカウントの「欲しい物と写真・篇幅・関注項の依頼」と画面の言語を店長が読む（2026-10-31）。店長（is_admin）だけ。足しただけ（表の形は変えない）。
-- 名前・メールは出さない（account の符号だけ）。画面の言語は app_users に account との結びがないので、言語ごとの人数だけ。
-- 戻し方：drop function public.admin_accounts(); drop function public.admin_ui_langs();
create or replace function public.admin_accounts()
returns table (account text, boards int, sz_s int, sz_m int, sz_l int, photos int, photos_done int, reqs int, reqs_wait int)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query
    with sz as (   -- 篇幅：店長・旧 test2 は sizes 表、ライブラリで追う人は follows.size（同じ account に両方あれば sizes 表）
      select s.account, s.size from public.sizes s
      union all select f.account, f.size from public.follows f where not exists (select 1 from public.sizes s where s.account = f.account))
    select a.account,
           (select count(*)::int from public.follows f where f.account = a.account),
           (select count(*)::int from sz where sz.account = a.account and sz.size = 'S'),
           (select count(*)::int from sz where sz.account = a.account and sz.size = 'M'),
           (select count(*)::int from sz where sz.account = a.account and sz.size = 'L'),
           (select count(*)::int from public.photo_inbox p where p.account = a.account),
           (select count(*)::int from public.photo_inbox p where p.account = a.account and p.state = 'done'),
           (select count(*)::int from public.item_requests r where r.account = a.account),
           (select count(*)::int from public.item_requests r where r.account = a.account and r.status is distinct from 'done' and r.status is distinct from 'skipped')
      from (select f.account from public.follows f union select s.account from public.sizes s
            union select p.account from public.photo_inbox p union select r.account from public.item_requests r) a
     order by 1;
end;
$$;
create or replace function public.admin_ui_langs()
returns table (lang text, n int)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query select coalesce(u.ui_lang, '（未設定）'), count(*)::int from public.app_users u where u.left_at is null group by 1 order by 2 desc, 1;
end;
$$;
revoke all on function public.admin_accounts() from public;
revoke all on function public.admin_accounts() from anon;
grant execute on function public.admin_accounts() to authenticated;
revoke all on function public.admin_ui_langs() from public;
revoke all on function public.admin_ui_langs() from anon;
grant execute on function public.admin_ui_langs() to authenticated;
