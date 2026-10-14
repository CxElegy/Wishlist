-- 网页「设置」页（docs/settings.html）上「新增关注项」的请求。在 Supabase → SQL Editor 里整段粘贴、运行一次即可
-- （需要先运行过 db/settings.sql，用同一个口令）。
--
-- 网页用公开的 publishable key，所以不直接开放这张表：
--   add_item(名字, 类型, 关键词, 最关心什么, 板块, 篇幅, 语言区, 口令)   口令对了才能提交
--   get_item_requests()                                                  谁都能看最近的请求（只有名字、类型、状态、时间）
-- GitHub Actions 每次运行（每 2 小时）用 secret key 读出待处理的，追加进 items.yaml 后标成 done
-- （items.yaml 里已经有同名的标成 skipped），同一次运行就开始收集这一项的新闻。

create table if not exists public.item_requests (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  name        text not null check (length(name) between 1 and 80),
  type        text not null default 'product' check (type in ('game', 'anime', 'show', 'product', 'category', 'event')),
  keywords    text[] not null check (cardinality(keywords) between 1 and 12),
  priority    text check (length(priority) <= 300),             -- 最关心它的什么
  section     text check (length(section) <= 20),              -- 头版上归到哪个板块，空 = 按类型
  size        text not null default 'M' check (size in ('S', 'M', 'L')),
  news_langs  text[] check (news_langs <@ array['zh-CN', 'zh-TW', 'en-US', 'ja-JP', 'ko-KR']),
  status      text not null default 'pending' check (status in ('pending', 'done', 'skipped')),
  handled_at  timestamptz
);

alter table public.item_requests enable row level security;   -- 不设任何规则：网页只能走下面两个函数

create or replace function public.add_item(p_name text, p_type text, p_keywords text[], p_priority text,
                                           p_section text, p_size text, p_langs text[], p_pass text)
returns bigint
language plpgsql security definer set search_path = ''
as $$
declare
  kws text[];
  new_id bigint;
begin
  if not exists (select 1 from private.settings_pass p where p.hash = extensions.crypt(p_pass, p.hash)) then
    perform pg_sleep(1);   -- 拖慢乱猜
    raise exception '口令不对' using errcode = '28P01';
  end if;
  p_name := btrim(coalesce(p_name, ''));
  if length(p_name) not between 1 and 80 then
    raise exception '名字要 1–80 个字';
  end if;
  if exists (select 1 from public.item_requests r where r.name = p_name and r.status = 'pending') then
    raise exception '「%」已经在等待加入了', p_name;
  end if;
  -- 名字排第一个，去重、去空，保持填写顺序
  select array_agg(k order by o) into kws from (
    select btrim(t.k) k, min(t.o) o from unnest(array[p_name] || coalesce(p_keywords, '{}')) with ordinality t(k, o)
    where btrim(t.k) <> '' and length(btrim(t.k)) <= 100 group by btrim(t.k) order by min(t.o) limit 12) s;
  insert into public.item_requests (name, type, keywords, priority, section, size, news_langs)
  values (p_name, coalesce(nullif(p_type, ''), 'product'), kws, nullif(btrim(coalesce(p_priority, '')), ''),
          nullif(btrim(coalesce(p_section, '')), ''), coalesce(nullif(p_size, ''), 'M'),
          nullif(coalesce(p_langs, '{}'), '{}'))
  returning id into new_id;
  return new_id;
end
$$;

create or replace function public.get_item_requests()
returns table (name text, type text, status text, created_at timestamptz)
language sql stable security definer set search_path = ''
as $$ select r.name, r.type, r.status, r.created_at from public.item_requests r
      where r.status = 'pending' or r.created_at > now() - interval '3 days' order by r.id desc limit 20 $$;

revoke all on function public.add_item(text, text, text[], text, text, text, text[], text) from public;
revoke all on function public.get_item_requests() from public;
grant execute on function public.add_item(text, text, text[], text, text, text, text[], text) to anon, authenticated;
grant execute on function public.get_item_requests() to anon, authenticated;
