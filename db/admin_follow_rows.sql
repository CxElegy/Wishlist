-- 管理ページ②：全アカウントの「置き方・関注項の中身」を 1 行ずつ、画面の言語を account ごとに店長が読む（2026-10-31）。店長（is_admin）だけ。足しただけ。
-- admin_follow_rows：follows の 1 行 = 1 行（版面名・置いた板块・並び pos・篇幅・小分類・見たい種類・乗換駅）＋その板块の分け方（nav_schemes）。メールは出さない。
-- admin_account_langs：app_users.email から private.user_account で account を出し、画面の言語を結ぶ（メールそのものは返さない）。
-- 戻し方：drop function public.admin_follow_rows(); drop function public.admin_account_langs();
create or replace function public.admin_follow_rows()
returns table (account text, board_id bigint, name text, section text, pos int, size text, subs jsonb, media jsonb, also jsonb, scheme text)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query
    select f.account, f.board_id, b.name, f.section, f.pos, f.size, f.subs, f.media, f.also, n.scheme
      from public.follows f join public.boards b on b.id = f.board_id
      left join public.nav_schemes n on n.account = f.account and n.section = f.section
     order by f.account, f.section, f.pos, f.board_id;
end;
$$;
create or replace function public.admin_account_langs()
returns table (account text, lang text)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query select private.user_account(u.email), coalesce(u.ui_lang, '（未設定）') from public.app_users u
    where u.left_at is null and coalesce(u.email, '') <> '' order by 1;
end;
$$;
revoke all on function public.admin_follow_rows() from public;
revoke all on function public.admin_follow_rows() from anon;
grant execute on function public.admin_follow_rows() to authenticated;
revoke all on function public.admin_account_langs() from public;
revoke all on function public.admin_account_langs() from anon;
grant execute on function public.admin_account_langs() to authenticated;
