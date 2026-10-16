-- 网页读回「我点过的 👍 / 👎」：换浏览器、换手机、清了缓存，按钮也显示成按过的样子。
-- feedback 表本身网页仍然读不到；这个函数只返回每条消息的最后一票（网址 + 1 / -1），撤销（0）的不返回。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（Claude 可以用 Supabase 连接器代为执行）。

create or replace function public.my_votes()
returns table (url text, vote smallint)
language sql stable security definer set search_path = public as $$
  select l.url, l.vote from (
    select distinct on (f.url) f.url, f.vote, f.created_at
    from public.feedback f
    order by f.url, f.created_at desc, f.id desc
  ) l
  where l.vote <> 0
  order by l.created_at desc
  limit 5000;
$$;

revoke all on function public.my_votes() from public;
grant execute on function public.my_votes() to anon;
