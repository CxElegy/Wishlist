-- 登录・身份（2026-10-20，第 1 步）
-- 访客（没登录）= 只能看；一般用户 = 谁都能用邮箱登录（2026-10-21 定：不做邀请制，第 2 步起有自己的一套）；管理者 = 最多 5 个账号，能进管理页、管所有人。
-- 只加不改：新表・新函数。现有的写函数要不要检查身份由 private.auth_flags 的 enforce 开关决定（切换到新网站时再打开，见 db/auth_enforce.sql）。
-- 做法照 Supabase 官方：身份放在 user_roles 表（用户自己改不了），不放 user_metadata。
-- 在 Supabase → SQL Editor 里整段运行一次（Claude 可以用 Supabase 连接器代为执行）。
-- hook_invite_only（邀请制）做好了但不接到 Authentication → Hooks（用户定的：不做邀请制）。

-- ① 管理者的邮箱（名字是 invites，因为最初做成了邀请制；2026-10-21 起不拦人，只用 role=admin 决定管理者）。
create table if not exists public.invites (
  email      text primary key check (email = lower(email) and position('@' in email) > 1),
  role       text not null default 'user' check (role in ('user', 'admin')),
  note       text,
  created_at timestamptz not null default now()
);
alter table public.invites enable row level security;   -- 规则只给登录服务读；网页走下面的管理者函数

insert into public.invites (email, role, note)
values ('c.elegy@outlook.com', 'admin', '运营者（2026-10-20）')
on conflict (email) do nothing;

-- ② 身份：每个账号一行。
create table if not exists public.user_roles (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  role       text not null default 'user' check (role in ('user', 'admin')),
  created_at timestamptz not null default now()
);
alter table public.user_roles enable row level security;
create policy "自己的身份只能看" on public.user_roles for select to authenticated using (user_id = (select auth.uid()));

-- ③ 资料：昵称・头像（管理页只显示昵称，不显示邮箱）。
create table if not exists public.profiles (
  user_id      uuid primary key references auth.users (id) on delete cascade,
  display_name text check (length(display_name) <= 40),
  avatar_url   text check (avatar_url is null or avatar_url ~ '^https://'),
  created_at   timestamptz not null default now()
);
alter table public.profiles enable row level security;
create policy "自己的资料能看" on public.profiles for select to authenticated using (user_id = (select auth.uid()));
create policy "自己的昵称能改" on public.profiles for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
grant select, update (display_name) on public.profiles to authenticated;

-- ④ 开关：enforce = false 时现有的写函数照旧（旧网站还在用）；切到新网站时改成 true。
create table if not exists private.auth_flags (
  key text primary key,
  on_ boolean not null
);
alter table private.auth_flags enable row level security;
insert into private.auth_flags values ('enforce', false) on conflict (key) do nothing;

-- ⑤ 判断函数
create or replace function public.is_admin()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (select 1 from public.user_roles r where r.user_id = (select auth.uid()) and r.role = 'admin');
$$;

create or replace function public.my_role()
returns text
language sql stable security definer set search_path = ''
as $$
  select coalesce((select r.role from public.user_roles r where r.user_id = (select auth.uid())),
                  case when (select auth.uid()) is null then 'guest' else 'user' end);
$$;

-- 改运营者（你）的关注清单・篇幅・按钮这些：开关没开 = 照旧谁都行；开了 = 只有管理者。
create or replace function public.can_write()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select case when coalesce((select f.on_ from private.auth_flags f where f.key = 'enforce'), false)
              then public.is_admin() else true end;
$$;

revoke all on function public.is_admin() from public;
revoke all on function public.my_role() from public;
revoke all on function public.can_write() from public;
grant execute on function public.is_admin() to anon, authenticated;
grant execute on function public.my_role() to anon, authenticated;
grant execute on function public.can_write() to anon, authenticated;

-- ⑥ 注册前的检查（Before User Created Hook）：邀请名单外 → 拒绝。
-- 照官方建议不用 security definer，只给登录服务（supabase_auth_admin）读邀请名单的权限。
create or replace function public.hook_invite_only(event jsonb)
returns jsonb
language plpgsql
as $$
declare
  addr text := lower(coalesce(event->'user'->>'email', ''));
begin
  if addr <> '' and exists (select 1 from public.invites i where i.email = addr) then
    return '{}'::jsonb;
  end if;
  return jsonb_build_object('error', jsonb_build_object(
    'http_code', 403,
    'message', '招待制です。管理者に招待を依頼してください。'));
end;
$$;
grant usage on schema public to supabase_auth_admin;
grant execute on function public.hook_invite_only(jsonb) to supabase_auth_admin;
revoke execute on function public.hook_invite_only(jsonb) from authenticated, anon, public;
grant select on public.invites to supabase_auth_admin;
create policy "登录服务读邀请名单" on public.invites for select to supabase_auth_admin using (true);

-- ⑦ 注册后：按邀请写身份和资料（Google 的名字・头像）。
create or replace function private.on_auth_user_created()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
  inv_role text;
begin
  select i.role into inv_role from public.invites i where i.email = lower(new.email);
  insert into public.user_roles (user_id, role) values (new.id, coalesce(inv_role, 'user'))
    on conflict (user_id) do nothing;
  insert into public.profiles (user_id, display_name, avatar_url)
  values (new.id,
          left(coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)), 40),
          case when new.raw_user_meta_data->>'avatar_url' ~ '^https://' then new.raw_user_meta_data->>'avatar_url' end)
    on conflict (user_id) do nothing;
  return new;
end;
$$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function private.on_auth_user_created();

-- ⑧ 管理者用：邀请名单的读・加（取消邀请・退会会删账号，在 db/auth_delete.sql，要在 SQL Editor 里自己运行），用户一览（只出昵称，不出邮箱）。管理者最多 5 个。
create or replace function public.admin_list_invites()
returns table (email text, role text, note text, created_at timestamptz, joined boolean)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query
    select i.email, i.role, i.note, i.created_at,
           exists (select 1 from auth.users u where lower(u.email) = i.email)
    from public.invites i order by i.created_at;
end;
$$;

create or replace function public.admin_invite(p_email text, p_role text default 'user', p_note text default null)
returns text
language plpgsql security definer set search_path = ''
as $$
declare
  addr text := lower(trim(p_email));
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  if addr !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then raise exception 'メールアドレスの形が正しくありません'; end if;
  if p_role not in ('user', 'admin') then raise exception 'role は user か admin'; end if;
  if p_role = 'admin' and (select count(*) from public.invites where role = 'admin' and email <> addr) >= 5 then
    raise exception '管理者は 5 人までです';
  end if;
  insert into public.invites (email, role, note) values (addr, p_role, left(p_note, 100))
    on conflict (email) do update set role = excluded.role, note = coalesce(excluded.note, public.invites.note);
  -- 已注册的人身份跟着改
  update public.user_roles r set role = p_role
    from auth.users u where u.id = r.user_id and lower(u.email) = addr;
  return addr;
end;
$$;

create or replace function public.admin_list_users()
returns table (display_name text, role text, created_at timestamptz, last_sign_in_at timestamptz)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query
    select p.display_name, r.role, r.created_at, u.last_sign_in_at
    from public.user_roles r
    join auth.users u on u.id = r.user_id
    left join public.profiles p on p.user_id = r.user_id
    order by r.created_at;
end;
$$;

revoke all on function public.admin_list_invites() from public, anon;
revoke all on function public.admin_invite(text, text, text) from public, anon;
revoke all on function public.admin_list_users() from public, anon;
grant execute on function public.admin_list_invites() to authenticated;
grant execute on function public.admin_invite(text, text, text) to authenticated;
grant execute on function public.admin_list_users() to authenticated;

-- ⑩ 投票记上是谁投的（没登录的旧投票 = 运营者的，user_id 空着）。
alter table public.feedback add column if not exists user_id uuid default auth.uid() references auth.users (id) on delete set null;

-- ⑪ 每个 account 的主人（db/accounts.sql 的 account 列 → 登录的人）。owner 空 = 运营者（管理者）的 account。
--    一般用户注册后第 2 步给他开一个自己的 account（owner = 他）。
create table if not exists public.accounts (
  account    text primary key check (account ~ '^[a-z0-9_-]{1,40}$'),
  owner      uuid references auth.users (id) on delete cascade,
  created_at timestamptz not null default now()
);
comment on column public.accounts.owner is '空 = 运营者（管理者）的 account（test1・test2）';
alter table public.accounts enable row level security;
insert into public.accounts (account) values ('test1'), ('test2') on conflict (account) do nothing;

-- 这个 account 我能改吗：开关关着 = 都能（跟以前一样）；开着 = 管理者・主人本人
create or replace function public.can_edit(p_account text)
returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when not coalesce((select f.on_ from private.auth_flags f where f.key = 'enforce'), false) then true
    when (select auth.uid()) is null then false
    when public.is_admin() then true
    else exists (select 1 from public.accounts a where a.account = p_account and a.owner = (select auth.uid()))
  end;
$$;
revoke all on function public.can_edit(text) from public;
grant execute on function public.can_edit(text) to anon, authenticated;

create or replace function public.auth_enforced()
returns boolean language sql stable security definer set search_path = '' as $$
  select coalesce((select f.on_ from private.auth_flags f where f.key = 'enforce'), false);
$$;
revoke all on function public.auth_enforced() from public;
grant execute on function public.auth_enforced() to anon, authenticated;
