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

-- ⑫ 一般用户：只填邮箱就用（2026-10-21，用户定的：不确认、不要密码、浏览器记住）。只有管理者的邮箱才在这个浏览器第一次发确认邮件。
create table if not exists public.visitors (
  email      text primary key check (email = lower(email) and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' and length(email) <= 200),
  first_seen timestamptz not null default now(),
  last_seen  timestamptz not null default now()
);
alter table public.visitors enable row level security;

create or replace function public.remember_user(p_email text)
returns void language plpgsql security definer set search_path = '' as $$
declare addr text := lower(trim(coalesce(p_email, '')));
begin
  if addr !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' or length(addr) > 200 then return; end if;
  insert into public.visitors (email) values (addr)
    on conflict (email) do update set last_seen = now();
end $$;

create or replace function public.is_admin_email(p_email text)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.invites i where i.email = lower(trim(coalesce(p_email, ''))) and i.role = 'admin');
$$;

create or replace function public.admin_list_visitors()
returns table (email text, first_seen timestamptz, last_seen timestamptz)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query select v.email, v.first_seen, v.last_seen from public.visitors v order by v.last_seen desc limit 500;
end $$;

revoke all on function public.remember_user(text) from public;
revoke all on function public.is_admin_email(text) from public;
revoke all on function public.admin_list_visitors() from public, anon;
grant execute on function public.remember_user(text) to anon, authenticated;
grant execute on function public.is_admin_email(text) to anon, authenticated;
grant execute on function public.admin_list_visitors() to authenticated;

-- ⑬ 用户名登录（2026-10-21，用户定的，取代 ⑫ 的「只填邮箱」）：用户名（邮箱也行）・不能重复（不分大小写）・不要密码。
--    第一次要同意利用規約・プライバシーポリシー（docs/<account>/terms.html，render.TERMS_VERSION），记下哪一版・什么时候；版本升了再问一次。
--    管理者 = 用户名是 invites 里 role=admin 的邮箱，这个浏览器第一次要点确认邮件。退会不用 delete：名字空出来、同意记录清掉。
create table if not exists public.app_users (
  name_key       text primary key,
  name           text not null,
  created_at     timestamptz not null default now(),
  last_seen      timestamptz not null default now(),
  agreed_version int,
  agreed_at      timestamptz,
  left_at        timestamptz
);
alter table public.app_users enable row level security;

create or replace function private.user_name_ok(p text)
returns text language plpgsql immutable as $$
declare n text := btrim(coalesce(p, ''));
begin
  if char_length(n) < 2 or char_length(n) > 40 then raise exception '名前は 2〜40 文字にしてください'; end if;
  if n ~ '[[:space:][:cntrl:]<>"''`/\\]' then raise exception '名前に空白や < > " '' ` / \ は使えません'; end if;
  return n;
end $$;

create or replace function public.name_available(p_name text)
returns boolean language plpgsql stable security definer set search_path = '' as $$
declare n text;
begin
  begin n := private.user_name_ok(p_name); exception when others then return false; end;
  return not exists (select 1 from public.app_users u where u.name_key = lower(n));
end $$;

create or replace function public.user_register(p_name text, p_agree_version int)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare n text := private.user_name_ok(p_name);
begin
  if coalesce(p_agree_version, 0) < 1 then raise exception '利用規約への同意が必要です'; end if;
  if exists (select 1 from public.app_users u where u.name_key = lower(n)) then
    raise exception 'その名前はもう使われています' using errcode = '23505';
  end if;
  insert into public.app_users (name_key, name, agreed_version, agreed_at) values (lower(n), n, p_agree_version, now());
  return jsonb_build_object('name', n, 'agreed_version', p_agree_version);
end $$;

create or replace function public.user_login(p_name text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare n text := btrim(coalesce(p_name, '')); r public.app_users;
begin
  select * into r from public.app_users u where u.name_key = lower(n) and u.left_at is null;
  if not found then raise exception 'その名前は見つかりません（はじめての方は「新しく始める」）' using errcode = 'P0002'; end if;
  update public.app_users set last_seen = now() where name_key = r.name_key;
  return jsonb_build_object('name', r.name, 'agreed_version', r.agreed_version);
end $$;

create or replace function public.user_agree(p_name text, p_version int)
returns void language plpgsql security definer set search_path = '' as $$
begin
  update public.app_users set agreed_version = p_version, agreed_at = now(), last_seen = now()
   where name_key = lower(btrim(coalesce(p_name, ''))) and left_at is null and p_version >= 1;
end $$;

create or replace function public.user_leave(p_name text)
returns void language plpgsql security definer set search_path = '' as $$
declare k text := lower(btrim(coalesce(p_name, '')));
begin
  update public.app_users set name_key = '~left~' || md5(k || now()::text), name = '（退会）', agreed_version = null, left_at = now()
   where name_key = k and left_at is null;
end $$;

create or replace function public.admin_list_app_users()
returns table (name text, created_at timestamptz, last_seen timestamptz, agreed_version int, agreed_at timestamptz)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query select u.name, u.created_at, u.last_seen, u.agreed_version, u.agreed_at
    from public.app_users u where u.left_at is null order by u.last_seen desc limit 500;
end $$;

revoke all on function public.name_available(text) from public;
revoke all on function public.user_register(text, int) from public;
revoke all on function public.user_login(text) from public;
revoke all on function public.user_agree(text, int) from public;
revoke all on function public.user_leave(text) from public;
revoke all on function public.admin_list_app_users() from public, anon;
grant execute on function public.name_available(text) to anon, authenticated;
grant execute on function public.user_register(text, int) to anon, authenticated;
grant execute on function public.user_login(text) to anon, authenticated;
grant execute on function public.user_agree(text, int) to anon, authenticated;
grant execute on function public.user_leave(text) to anon, authenticated;
grant execute on function public.admin_list_app_users() to authenticated;

-- ⑭ 新しく始める（入口 docs/index.html の流れ，2026-10-21）：名前・規約の同意・好み（言語・ジャンル・最初の版面）を一度に登録。
--    prefs = {lang: {primary: ja, also: [en, …]}, genres: [板块], picks: [{name, sec}]}。第 2 步で本人の版面を作るときに使う。
alter table public.app_users add column if not exists prefs jsonb not null default '{}'::jsonb;

create or replace function public.user_signup(p_name text, p_agree_version int, p_prefs jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare n text := private.user_name_ok(p_name);
begin
  if coalesce(p_agree_version, 0) < 1 then raise exception '利用規約への同意が必要です'; end if;
  if jsonb_typeof(coalesce(p_prefs, '{}'::jsonb)) <> 'object' or length(coalesce(p_prefs, '{}'::jsonb)::text) > 8000 then
    raise exception '設定の形が正しくありません';
  end if;
  if exists (select 1 from public.app_users u where u.name_key = lower(n)) then
    raise exception 'その名前はもう使われています' using errcode = '23505';
  end if;
  insert into public.app_users (name_key, name, agreed_version, agreed_at, prefs)
  values (lower(n), n, p_agree_version, now(), coalesce(p_prefs, '{}'::jsonb));
  return jsonb_build_object('name', n, 'agreed_version', p_agree_version);
end $$;

create or replace function public.user_set_prefs(p_name text, p_prefs jsonb)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if jsonb_typeof(coalesce(p_prefs, '{}'::jsonb)) <> 'object' or length(coalesce(p_prefs, '{}'::jsonb)::text) > 8000 then
    raise exception '設定の形が正しくありません';
  end if;
  update public.app_users set prefs = prefs || p_prefs, last_seen = now()
   where name_key = lower(btrim(coalesce(p_name, ''))) and left_at is null;
end $$;

revoke all on function public.user_signup(text, int, jsonb) from public;
revoke all on function public.user_set_prefs(text, jsonb) from public;
grant execute on function public.user_signup(text, int, jsonb) to anon, authenticated;
grant execute on function public.user_set_prefs(text, jsonb) to anon, authenticated;

-- ⑮ 店長の名前（2026-10-21，用户定的）：CxElegy でログイン → 店長のメールに換えて確認のリンクを送る
alter table public.app_users add column if not exists email text check (email is null or email = lower(email));
insert into public.app_users (name_key, name, agreed_version, agreed_at, email, prefs)
values ('cxelegy', 'CxElegy', 1, now(), 'c.elegy@outlook.com',
        '{"lang":{"primary":"ja","also":["en","zh-Hans","zh-Hant","ko"]},"role":"shop","from":"owner"}'::jsonb)
on conflict (name_key) do update set email = excluded.email;

create or replace function public.admin_email_for(p_name text) returns text
language sql stable security definer set search_path = '' as $$
  select u.email from public.app_users u
    join public.invites i on i.email = u.email and i.role = 'admin'
   where u.name_key = lower(btrim(coalesce(p_name, ''))) and u.left_at is null
   limit 1;
$$;
revoke all on function public.admin_email_for(text) from public;
grant execute on function public.admin_email_for(text) to anon, authenticated;

-- ⑯ ログインはメールアドレス（2026-10-21，用户定的：ユーザー名から変えた）。app_users の name = メールアドレス（小文字で重ならない）。
--    ⑮ の店長の名前 CxElegy は、店長のメールの行にする（admin_email_for は残すが網页はもう使わない）。
create or replace function private.user_name_ok(p text)
returns text language plpgsql immutable as $$
declare n text := lower(btrim(coalesce(p, '')));
begin
  if char_length(n) > 120 or n !~ '^[^@[:space:][:cntrl:]<>"''`/\\]+@[^@[:space:][:cntrl:]<>"''`/\\]+\.[^@[:space:][:cntrl:]<>"''`/\\]+$' then
    raise exception 'メールアドレスを入れてください（例：name@example.com）';
  end if;
  return n;
end $$;

create or replace function public.user_login(p_name text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare n text := btrim(coalesce(p_name, '')); r public.app_users;
begin
  select * into r from public.app_users u where u.name_key = lower(n) and u.left_at is null;
  if not found then raise exception 'このメールアドレスはまだ登録されていません（はじめての方は「新しく始める」）' using errcode = 'P0002'; end if;
  update public.app_users set last_seen = now() where name_key = r.name_key;
  return jsonb_build_object('name', r.name, 'agreed_version', r.agreed_version);
end $$;

create or replace function public.user_register(p_name text, p_agree_version int)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare n text := private.user_name_ok(p_name);
begin
  if coalesce(p_agree_version, 0) < 1 then raise exception '利用規約への同意が必要です'; end if;
  if exists (select 1 from public.app_users u where u.name_key = n) then
    raise exception 'このメールアドレスはもう登録されています（右上の「ログイン」から）' using errcode = '23505';
  end if;
  insert into public.app_users (name_key, name, agreed_version, agreed_at, email) values (n, n, p_agree_version, now(), n);
  return jsonb_build_object('name', n, 'agreed_version', p_agree_version);
end $$;

create or replace function public.user_signup(p_name text, p_agree_version int, p_prefs jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare n text := private.user_name_ok(p_name);
begin
  if coalesce(p_agree_version, 0) < 1 then raise exception '利用規約への同意が必要です'; end if;
  if jsonb_typeof(coalesce(p_prefs, '{}'::jsonb)) <> 'object' or length(coalesce(p_prefs, '{}'::jsonb)::text) > 8000 then
    raise exception '設定の形が正しくありません';
  end if;
  if exists (select 1 from public.app_users u where u.name_key = n) then
    raise exception 'このメールアドレスはもう登録されています（右上の「ログイン」から）' using errcode = '23505';
  end if;
  insert into public.app_users (name_key, name, agreed_version, agreed_at, email, prefs)
  values (n, n, p_agree_version, now(), n, coalesce(p_prefs, '{}'::jsonb));
  return jsonb_build_object('name', n, 'agreed_version', p_agree_version);
end $$;

update public.app_users set name_key = 'c.elegy@outlook.com', name = 'c.elegy@outlook.com'
 where name_key = 'cxelegy' and not exists (select 1 from public.app_users x where x.name_key = 'c.elegy@outlook.com');

-- ⑰ 店長はメール＋パスワード（2026-10-21，用户定的：毎回のメール確認はやめる・パスワードの再発行は要らない）。
--    はじめの 1 回だけ網页で自分で決める（pw_setup が開いている間だけ、決めたら閉じる）。変えるのはログイン中のメニューから（auth.updateUser）。
insert into private.auth_flags (key, on_) values ('pw_setup', true)
on conflict (key) do update set on_ = true;

create or replace function public.shop_pw_setup_open(p_email text)
returns boolean language sql stable security definer set search_path = '' as $$
  select coalesce((select on_ from private.auth_flags where key = 'pw_setup'), false)
     and exists (select 1 from public.invites i where i.email = lower(btrim(coalesce(p_email, ''))) and i.role = 'admin');
$$;

create or replace function public.shop_set_password(p_email text, p_password text)
returns void language plpgsql security definer set search_path = '' as $$
declare m text := lower(btrim(coalesce(p_email, '')));
begin
  if not public.shop_pw_setup_open(m) then raise exception 'パスワードはもう決まっています' using errcode = '42501'; end if;
  if char_length(coalesce(p_password, '')) < 8 then raise exception 'パスワードは 8 文字以上にしてください'; end if;
  update auth.users set encrypted_password = extensions.crypt(p_password, extensions.gen_salt('bf')),
                        email_confirmed_at = coalesce(email_confirmed_at, now()), updated_at = now()
   where lower(email) = m;
  if not found then raise exception '店長のアカウントが見つかりません'; end if;
  update private.auth_flags set on_ = false where key = 'pw_setup';
end $$;

revoke all on function public.shop_pw_setup_open(text) from public;
revoke all on function public.shop_set_password(text, text) from public;
grant execute on function public.shop_pw_setup_open(text) to anon, authenticated;
grant execute on function public.shop_set_password(text, text) to anon, authenticated;

-- ⑱ だれでもメール＋パスワード（2026-10-21，用户定的：ログインの形を全員そろえる・メールは送らない・再発行なし・退会の機能はいらない）
--    Supabase Auth のユーザーを確認済みで作る。テスト用 5 つはパスワード 0000（ユーザーの指定）。店長は管理ページでお客さまのパスワードを変えられる。
create or replace function private.make_auth_user(p_email text, p_password text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare m text := lower(btrim(coalesce(p_email, ''))); uid uuid;
begin
  select id into uid from auth.users where lower(email) = m;
  if uid is null then
    uid := gen_random_uuid();
    insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
                            confirmation_token, recovery_token, email_change_token_new, email_change,
                            raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
    values ('00000000-0000-0000-0000-000000000000', uid, 'authenticated', 'authenticated', m,
            extensions.crypt(p_password, extensions.gen_salt('bf')), now(), '', '', '', '',
            '{"provider":"email","providers":["email"]}'::jsonb, '{}'::jsonb, now(), now());
    insert into auth.identities (provider_id, user_id, identity_data, provider, created_at, updated_at)
    values (uid::text, uid, jsonb_build_object('sub', uid::text, 'email', m, 'email_verified', true, 'phone_verified', false), 'email', now(), now());
  else
    update auth.users set encrypted_password = extensions.crypt(p_password, extensions.gen_salt('bf')),
                          email_confirmed_at = coalesce(email_confirmed_at, now()), updated_at = now() where id = uid;
  end if;
  return uid;
end $$;
revoke all on function private.make_auth_user(text, text) from public, anon, authenticated;

create or replace function public.user_signup(p_name text, p_agree_version int, p_prefs jsonb, p_password text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare n text := private.user_name_ok(p_name);
begin
  if char_length(coalesce(p_password, '')) < 8 then raise exception 'パスワードは 8 文字以上にしてください'; end if;
  if exists (select 1 from auth.users u where lower(u.email) = n) then
    raise exception 'このメールアドレスはもう登録されています（右上の「ログイン」から）' using errcode = '23505';
  end if;
  perform public.user_signup(p_name, p_agree_version, p_prefs);
  perform private.make_auth_user(n, p_password);
  return jsonb_build_object('name', n, 'agreed_version', p_agree_version);
end $$;
revoke all on function public.user_signup(text, int, jsonb, text) from public;
grant execute on function public.user_signup(text, int, jsonb, text) to anon, authenticated;

create or replace function public.admin_users()
returns table (email text, created_at timestamptz, last_seen timestamptz, agreed_version int, has_password boolean, is_test boolean, role text)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query
    select u.name_key, u.created_at, u.last_seen, u.agreed_version,
           exists (select 1 from auth.users a where lower(a.email) = u.name_key and a.banned_until is null),
           coalesce((u.prefs->>'dummy')::boolean, false),
           coalesce((select r.role from public.user_roles r join auth.users a on a.id = r.user_id where lower(a.email) = u.name_key limit 1), 'user')
      from public.app_users u where u.left_at is null and u.name_key like '%@%'
     order by u.created_at;
end $$;

create or replace function public.admin_user_password(p_email text, p_password text)
returns void language plpgsql security definer set search_path = '' as $$
declare m text := lower(btrim(coalesce(p_email, '')));
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  if char_length(coalesce(p_password, '')) < 4 then raise exception 'パスワードは 4 文字以上にしてください'; end if;
  if not exists (select 1 from public.app_users u where u.name_key = m and u.left_at is null) then raise exception 'そのお客さまはいません'; end if;
  perform private.make_auth_user(m, p_password);
end $$;
revoke all on function public.admin_users() from public, anon;
revoke all on function public.admin_user_password(text, text) from public, anon;
grant execute on function public.admin_users() to authenticated;
grant execute on function public.admin_user_password(text, text) to authenticated;
-- （admin_user_leave も作ったが、退会の機能はいらない（用户定的）ので網页からは呼ばない）
