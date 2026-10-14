-- 网页「设置」页（docs/settings.html）用：在网页上改每个关注项的篇幅 S / M / L。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（需要先运行过 db/sizes.sql）。
--
-- 网页用公开的 publishable key，所以不直接开放 sizes 表：
--   get_sizes()                  谁都能读篇幅（只有关注项名字和 S / M / L）
--   set_size(item, size, 不用)   改篇幅。不要口令（第三个参数留着只是为了兼容旧网页，传什么都行）
-- 网页是公开的，知道网址的人也能改；真被乱改，在 Supabase 的 Table Editor 里改回来即可。

create or replace function public.get_sizes()
returns table (item text, size text)
language sql stable security definer set search_path = ''
as $$ select s.item, s.size from public.sizes s order by s.item $$;

create or replace function public.set_size(p_item text, p_size text, p_pass text)
returns text
language plpgsql security definer set search_path = ''
as $$
begin
  if p_size not in ('S', 'M', 'L') then
    raise exception '篇幅只能是 S / M / L';
  end if;
  if length(coalesce(p_item, '')) not between 1 and 200 then
    raise exception '关注项名字不对';
  end if;
  insert into public.sizes (item, size, updated_at) values (p_item, p_size, now())
  on conflict (item) do update set size = excluded.size, updated_at = now();
  perform private.kick_github();   -- 立刻叫 GitHub 重新生成网页（db/instant.sql）
  return p_size;
end
$$;

revoke all on function public.get_sizes() from public;
revoke all on function public.set_size(text, text, text) from public;
grant execute on function public.get_sizes() to anon, authenticated;
grant execute on function public.set_size(text, text, text) to anon, authenticated;
