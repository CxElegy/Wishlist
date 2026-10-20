-- 取消邀请・退会（会删账号）。Supabase 连接器执行带 delete 的语句要你点确认，云端会话里没人点会超时，
-- 所以这个文件请你自己在 Supabase → SQL Editor 里整段运行一次（先要运行过 db/auth.sql）。

-- 管理者：把某个邮箱从邀请名单拿掉；已经注册的账号一起删（他的数据跟着 on delete cascade 删掉）。不能删自己。
create or replace function public.admin_uninvite(p_email text)
returns text
language plpgsql security definer set search_path = ''
as $$
declare
  addr text := lower(trim(p_email));
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  if addr = (select lower(u.email) from auth.users u where u.id = (select auth.uid())) then
    raise exception '自分自身は外せません';
  end if;
  delete from public.invites where email = addr;
  delete from auth.users where lower(email) = addr;
  return addr;
end;
$$;

-- 退会：自己的账号和数据一起删。
create or replace function public.delete_my_account()
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if (select auth.uid()) is null then raise exception 'ログインしていません'; end if;
  delete from auth.users where id = (select auth.uid());
end;
$$;

revoke all on function public.admin_uninvite(text) from public, anon;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.admin_uninvite(text) to authenticated;
grant execute on function public.delete_my_account() to authenticated;
