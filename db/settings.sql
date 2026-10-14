-- 网页「设置」页（docs/settings.html）用：在网页上改每个关注项的篇幅 S / M / L。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（需要先运行过 db/sizes.sql）。
--
-- 网页用公开的 publishable key，所以不直接开放 sizes 表：
--   get_sizes()                    谁都能读篇幅（只有关注项名字和 S / M / L）
--   set_size(item, size, 口令)     口令对了才能改；口令只存加盐哈希，放在网页接口碰不到的 private schema
-- 设置 / 更换口令（把 你的口令 换掉，只在 SQL Editor 里运行，不要写进任何文件）：
--   insert into private.settings_pass (id, hash) values (1, extensions.crypt('你的口令', extensions.gen_salt('bf')))
--   on conflict (id) do update set hash = excluded.hash;

create extension if not exists pgcrypto with schema extensions;
create schema if not exists private;
revoke all on schema private from anon, authenticated;

create table if not exists private.settings_pass (
  id    int primary key default 1 check (id = 1),   -- 只有一行
  hash  text not null
);

create or replace function public.get_sizes()
returns table (item text, size text)
language sql stable security definer set search_path = ''
as $$ select s.item, s.size from public.sizes s order by s.item $$;

create or replace function public.set_size(p_item text, p_size text, p_pass text)
returns text
language plpgsql security definer set search_path = ''
as $$
begin
  if not exists (select 1 from private.settings_pass p where p.hash = extensions.crypt(p_pass, p.hash)) then
    perform pg_sleep(1);   -- 拖慢乱猜
    raise exception '口令不对' using errcode = '28P01';
  end if;
  if p_size not in ('S', 'M', 'L') then
    raise exception '篇幅只能是 S / M / L';
  end if;
  if length(coalesce(p_item, '')) not between 1 and 200 then
    raise exception '关注项名字不对';
  end if;
  insert into public.sizes (item, size, updated_at) values (p_item, p_size, now())
  on conflict (item) do update set size = excluded.size, updated_at = now();
  return p_size;
end
$$;

revoke all on function public.get_sizes() from public;
revoke all on function public.set_size(text, text, text) from public;
grant execute on function public.get_sizes() to anon, authenticated;
grant execute on function public.set_size(text, text, text) to anon, authenticated;
