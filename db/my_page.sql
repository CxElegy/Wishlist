-- お客さま自分のページ（2026-10-22，用户定的：アカウントは 1 つずつ独立。ログインしたら店長の中身ではなく自分の（最初は空の）ページ）。
-- ログインした本人（Supabase Auth のメール）の app_users の行だけを読む・書く。ほかの人の行は触れない。
-- キーワード = prefs.picks（[{name, sec}]、入口の「新しく始める」で選んだものと同じ形）。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（Claude 可以用 Supabase 连接器代为执行）。

create or replace function public.my_page()
returns jsonb language sql stable security definer set search_path = '' as $$
  select case when (select auth.uid()) is null then null else (
    select jsonb_build_object('name', u.name, 'email', u.email, 'since', u.created_at, 'prefs', u.prefs)
    from public.app_users u
    where lower(u.email) = lower((select auth.jwt()) ->> 'email') and u.left_at is null
    limit 1) end $$;

-- キーワードを丸ごと置き換える（追加・削除は網页で並べ直して送る）。200 個まで・名前 1〜80 文字・板块 1〜10 文字。返り値：個数
create or replace function public.my_keywords_set(p_picks jsonb)
returns int language plpgsql security definer set search_path = '' as $$
declare n int; mail text := lower((select auth.jwt()) ->> 'email');
begin
  if (select auth.uid()) is null or coalesce(mail, '') = '' then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  if jsonb_typeof(p_picks) is distinct from 'array' then raise exception 'キーワードの形が違います'; end if;
  n := jsonb_array_length(p_picks);
  if n > 200 then raise exception 'キーワードは 200 個までです'; end if;
  if exists (select 1 from jsonb_array_elements(p_picks) x
             where jsonb_typeof(x) <> 'object' or length(btrim(coalesce(x ->> 'name', ''))) not between 1 and 80
                or length(coalesce(x ->> 'sec', '')) not between 1 and 10) then
    raise exception 'キーワードは 1〜80 文字、大類つきで';
  end if;
  update public.app_users set prefs = prefs || jsonb_build_object('picks', p_picks), last_seen = now()
  where lower(email) = mail and left_at is null;
  if not found then raise exception 'お客さまの登録が見つかりません'; end if;
  return n;
end $$;

revoke all on function public.my_page() from public;
revoke all on function public.my_keywords_set(jsonb) from public;
grant execute on function public.my_page() to authenticated;
grant execute on function public.my_keywords_set(jsonb) to authenticated;
