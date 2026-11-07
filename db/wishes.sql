-- お客さま本人の欲しい物（2026-11-07，用户定的：店長にあるものは管理以外すべてお客さまにも）。流すのは 1 回だけ、PC の Supabase（docs/rules/local-pc.md）。
-- 店長の欲しい物は今までどおり wishlist.yaml。ここはお客さまの分だけ。公開のリポジトリ・Pages に置かない（docs/rules/library.md）。
-- 表は直接開けない。読み書きは本人の関数だけ（account はログインの鍵から決まるので、ほかの人の行には届かない）。
create table if not exists public.wishes (
  id         bigint generated always as identity primary key,
  account    text not null,
  name       text not null check (length(name) between 1 and 200),
  status     text not null default '想要' check (status in ('想要', '纠结', '已入手', '没买到', '已过期')),
  price      numeric check (price >= 0),
  currency   text check (length(currency) <= 8),
  url        text check (length(url) <= 2000 and url ~ '^https?://'),
  shop       text check (length(shop) <= 100),
  note       text check (length(note) <= 500),
  specs      jsonb,
  image      text check (length(image) <= 400000 and image ~ '^data:image/jpeg;base64,'),   -- 長辺 800 まで。本人だけが読むページに埋める
  photo      bigint unique,   -- photo_inbox の編号（写真から足したとき。同じ写真で 2 行にしない）
  added      date not null default current_date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists wishes_account on public.wishes (account, id desc);
alter table public.wishes enable row level security;   -- 規則を置かない：service key だけが直接読み書きできる

create or replace function public.my_wishes()
returns setof public.wishes language sql stable security definer set search_path = ''
as $$ select w.* from public.wishes w where w.account = public.my_account() order by w.id desc limit 300 $$;

create or replace function public.my_wish_add(p_name text, p_status text, p_price numeric, p_currency text, p_url text, p_note text)
returns bigint language plpgsql security definer set search_path = '' as $$
declare a text := public.my_account(); new_id bigint;
begin
  if a is null or (select auth.uid()) is null then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  if (select count(*) from public.wishes where account = a) >= 300 then raise exception '欲しい物は 300 件までです'; end if;
  insert into public.wishes (account, name, status, price, currency, url, note)
  values (a, btrim(p_name), coalesce(p_status, '想要'), p_price, nullif(btrim(coalesce(p_currency, '')), ''), nullif(btrim(coalesce(p_url, '')), ''), nullif(btrim(coalesce(p_note, '')), ''))
  returning id into new_id;
  return new_id;
end $$;

create or replace function public.my_wish_status(p_id bigint, p_status text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if (select auth.uid()) is null then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  update public.wishes set status = p_status, updated_at = now() where id = p_id and account = public.my_account();
  if not found then raise exception '見つかりません'; end if;
end $$;

create or replace function public.my_wish_del(p_id bigint)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if (select auth.uid()) is null then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  delete from public.wishes where id = p_id and account = public.my_account();
  if not found then raise exception '見つかりません'; end if;
end $$;

revoke all on function public.my_wishes() from public, anon;
revoke all on function public.my_wish_add(text, text, numeric, text, text, text) from public, anon;
revoke all on function public.my_wish_status(bigint, text) from public, anon;
revoke all on function public.my_wish_del(bigint) from public, anon;
grant execute on function public.my_wishes() to authenticated;
grant execute on function public.my_wish_add(text, text, numeric, text, text, text) to authenticated;
grant execute on function public.my_wish_status(bigint, text) to authenticated;
grant execute on function public.my_wish_del(bigint) to authenticated;

-- 表そのものは service key だけ（既定の権限を外す）
revoke all on public.wishes from anon, authenticated;

-- 写真から足す：受付は店長と同じ photo_inbox。account は鍵から決まる（p_account を渡さない）。
-- お客さまの写真は公開のリポジトリに書き出さない：digest.export_photos は店長の行だけ（scope_account）、お客さまの行はクラウドの AI 編集が短い合言葉で受け取る
create or replace function public.my_photo_add(p_image text, p_thumb text, p_status text, p_note text)
returns bigint language plpgsql security definer set search_path = '' as $$
declare a text := public.my_account(); new_id bigint;
begin
  if a is null or (select auth.uid()) is null then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  if (select count(*) from public.photo_inbox where account = a and state <> 'done') >= 20 then
    raise exception '待ちの写真が 20 枚あります。処理が済んでから足してください';
  end if;
  if p_status not in ('想要', '纠结') then raise exception '状態が不正です'; end if;
  if p_image !~ '^data:image/jpeg;base64,' or coalesce(p_thumb, '') !~ '^(data:image/jpeg;base64,.*)?$' then
    raise exception '写真の形式が不正です';
  end if;
  insert into public.photo_inbox (account, status, note, image, thumb)
  values (a, p_status, nullif(left(coalesce(p_note, ''), 500), ''), p_image, nullif(p_thumb, '')) returning id into new_id;
  return new_id;
end $$;

create or replace function public.my_photo_inbox()
returns table (id bigint, created_at timestamptz, status text, note text, state text, wish_name text, thumb text)
language sql stable security definer set search_path = ''
as $$ select i.id, i.created_at, i.status, i.note, i.state, i.wish_name, i.thumb from public.photo_inbox i
      where i.account = public.my_account() and (i.state <> 'done' or i.created_at > now() - interval '3 days')
      order by i.id desc limit 20 $$;

revoke all on function public.my_photo_add(text, text, text, text) from public, anon;
revoke all on function public.my_photo_inbox() from public, anon;
grant execute on function public.my_photo_add(text, text, text, text) to authenticated;
grant execute on function public.my_photo_inbox() to authenticated;
