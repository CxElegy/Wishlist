-- 愿望清单页「📷 拍照加愿望」的照片收件箱。在 Supabase → SQL Editor 里整段粘贴、运行一次即可。
--
-- 流程：网页上传（口令对了才收）→ GitHub Actions 每 2 小时导出到 inbox/photos/（state: new → exported）
--      → Claude 定时任务按 PHOTOS.md 认出物品、加进 wishlist.yaml（带 photo: 编号）
--      → 下一次 Actions 看到 wishlist.yaml 里有这个编号，标成 done 并记下名字。
-- 网页用公开的 publishable key，所以不直接开放这张表：
--   add_photo(不用, 图片, 缩略图, 想要/纠结, 备注)   收一张照片。不要口令（第一个参数留着只是为了兼容，传什么都行）；
--                                                   待处理（还没加进愿望清单）的最多 20 张，免得被乱传
--   get_photo_inbox()                               网页看排队情况（只给缩略图）
-- 网页是公开的，知道网址的人也能传；真被乱传，在 Supabase 的 Table Editor 里删掉那几行即可。

create table if not exists public.photo_inbox (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  status      text not null check (status in ('想要', '纠结')),
  note        text check (length(note) <= 500),
  image       text not null check (length(image) <= 3000000),   -- data:image/jpeg;base64,…（网页先缩到长边 1600）
  thumb       text check (length(thumb) <= 200000),             -- 缩略图，网页排队列表用
  state       text not null default 'new' check (state in ('new', 'exported', 'done')),
  wish_name   text
);
alter table public.photo_inbox enable row level security;   -- 不设任何规则：只有 secret key 能直接读写

create or replace function public.add_photo(p_pass text, p_image text, p_thumb text, p_status text, p_note text)
returns bigint language plpgsql security definer set search_path = ''
as $$
declare new_id bigint;
begin
  if (select count(*) from public.photo_inbox where state <> 'done') >= 20 then
    raise exception '待处理的照片已经有 20 张了，等 Claude 处理完再传';
  end if;
  if p_status not in ('想要', '纠结') then raise exception '只能选 想要 / 纠结'; end if;
  if p_image !~ '^data:image/jpeg;base64,' or coalesce(p_thumb, '') !~ '^(data:image/jpeg;base64,.*)?$' then
    raise exception '图片格式不对';
  end if;
  insert into public.photo_inbox (status, note, image, thumb)
  values (p_status, nullif(left(coalesce(p_note, ''), 500), ''), p_image, nullif(p_thumb, ''))
  returning id into new_id;
  return new_id;
end $$;

create or replace function public.get_photo_inbox()
returns table (id bigint, created_at timestamptz, status text, note text, state text, wish_name text, thumb text)
language sql stable security definer set search_path = ''
as $$ select i.id, i.created_at, i.status, i.note, i.state, i.wish_name, i.thumb from public.photo_inbox i
      where i.state <> 'done' or i.created_at > now() - interval '3 days' order by i.id desc limit 20 $$;

revoke all on function public.add_photo(text, text, text, text, text) from public;
revoke all on function public.get_photo_inbox() from public;
grant execute on function public.add_photo(text, text, text, text, text) to anon, authenticated;
grant execute on function public.get_photo_inbox() to anon, authenticated;

-- 以前新闻卡片上的「♥ 加入心愿单」已经去掉：不再让网页往 wish_requests 里写
drop policy if exists "网页只能新增加入心愿单的请求" on public.wish_requests;
revoke insert on public.wish_requests from anon;
