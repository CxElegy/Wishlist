-- 网页「设置」页（docs/settings.html）上「新增 / 修改关注项」的请求。在 Supabase → SQL Editor 里整段粘贴、运行一次即可。
--
-- 网页用公开的 publishable key，所以不直接开放这张表，只能走两个函数（不用口令）：
--   submit_item(action, 名字, config)   action = add 新增 / edit 修改；config 是 items.yaml 里这一项的字段（JSON）
--   list_item_requests()                最近的请求（名字、新增还是修改、状态、没处理的原因）
-- 同时最多 20 个待处理的请求，防止乱提交。
-- GitHub Actions 每次运行（每 2 小时）用 secret key 读出待处理的：新增的追加到 items.yaml 末尾，
-- 修改的只改提交了的字段（别的字段和注释不动），再标成 done；名字重复、找不到、内容不对的标成 skipped 并写明原因。

create table if not exists public.item_requests (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  action      text not null default 'add' check (action in ('add', 'edit')),
  name        text not null check (length(name) between 1 and 80),
  config      jsonb not null default '{}' check (jsonb_typeof(config) = 'object' and length(config::text) <= 20000),
  status      text not null default 'pending' check (status in ('pending', 'done', 'skipped')),
  note        text,                                                 -- skipped 的原因
  handled_at  timestamptz
);

alter table public.item_requests enable row level security;   -- 不设任何规则：网页只能走下面两个函数

create or replace function public.submit_item(p_action text, p_name text, p_config jsonb)
returns bigint
language plpgsql security definer set search_path = ''
as $$
declare new_id bigint;
begin
  p_name := btrim(coalesce(p_name, ''));
  if length(p_name) not between 1 and 80 then raise exception '名字要 1–80 个字'; end if;
  if coalesce(p_action, '') not in ('add', 'edit') then raise exception 'action 只能是 add / edit'; end if;
  if jsonb_typeof(p_config) is distinct from 'object' then raise exception '内容不对'; end if;
  if (select count(*) from public.item_requests r where r.status = 'pending') >= 20 then
    raise exception '待处理的请求太多了，等下次更新处理完再提交';
  end if;
  if p_action = 'add' and exists (select 1 from public.item_requests r
                                  where r.name = p_name and r.action = 'add' and r.status = 'pending') then
    raise exception '「%」已经在等待加入了', p_name;
  end if;
  insert into public.item_requests (action, name, config) values (p_action, p_name, p_config)
  returning id into new_id;
  perform private.kick_github();   -- 立刻叫 GitHub 处理（db/instant.sql）
  return new_id;
end $$;

create or replace function public.list_item_requests()
returns table (name text, action text, status text, note text, created_at timestamptz)
language sql stable security definer set search_path = ''
as $$ select r.name, r.action, r.status, r.note, r.created_at from public.item_requests r
      where r.status = 'pending' or r.created_at > now() - interval '3 days' order by r.id desc limit 20 $$;

revoke all on function public.submit_item(text, text, jsonb) from public;
revoke all on function public.list_item_requests() from public;
grant execute on function public.submit_item(text, text, jsonb) to anon, authenticated;
grant execute on function public.list_item_requests() to anon, authenticated;
