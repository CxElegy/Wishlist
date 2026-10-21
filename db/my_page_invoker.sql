-- 【未適用・ユーザーの承認待ち（2026-10-22）】db/my_page.sql（今動いている SECURITY DEFINER の版）を置き換える案。
-- Supabase 公式スキルのセキュリティチェックリストに合わせたもの。承認されたら実行し、db/my_page.sql をこの中身にして、このファイルは消す。

-- お客さま自分のページ（2026-10-22，用户定的：アカウントは 1 つずつ独立。ログインしたら店長の中身ではなく自分の（最初は空の）ページ）。
-- ログインした本人（Supabase Auth のメール）の app_users の行だけを読む・書く。ほかの人の行は触れない。
-- キーワード = prefs.picks（[{name, sec}]、入口の「新しく始める」で選んだものと同じ形）。
--
-- 守り方は Supabase の公式スキル（supabase/agent-skills@supabase のセキュリティチェックリスト）に合わせた：
--   ・SECURITY DEFINER で RLS を飛ばさない → SECURITY INVOKER ＋「自分の行だけ」の RLS ポリシー（TO authenticated ＋ 持ち主の条件）
--   ・UPDATE は SELECT のポリシーも要る・USING と WITH CHECK の両方（メールを他人のものに書き換えられない）
--   ・書けるのは prefs と last_seen の列だけ（同意の記録・メール・退会の印は本人も変えられない）
--   ・anon（ログインなし）は関数を呼べない
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（Claude 可以用 Supabase 连接器代为执行）。

drop policy if exists app_users_select_own on public.app_users;
create policy app_users_select_own on public.app_users for select to authenticated
  using (lower(email) = lower((select auth.jwt()) ->> 'email') and left_at is null);
drop policy if exists app_users_update_own on public.app_users;
create policy app_users_update_own on public.app_users for update to authenticated
  using (lower(email) = lower((select auth.jwt()) ->> 'email') and left_at is null)
  with check (lower(email) = lower((select auth.jwt()) ->> 'email') and left_at is null);
revoke update on public.app_users from authenticated;
grant update (prefs, last_seen) on public.app_users to authenticated;

create or replace function public.my_page()
returns jsonb language sql stable security invoker set search_path = '' as $$
  select jsonb_build_object('name', u.name, 'email', u.email, 'since', u.created_at, 'prefs', u.prefs)
  from public.app_users u limit 1 $$;   -- 見えるのは RLS で自分の行だけ

-- キーワードを丸ごと置き換える（追加・削除は網页で並べ直して送る）。200 個まで・名前 1〜80 文字・板块 1〜10 文字。返り値：個数
create or replace function public.my_keywords_set(p_picks jsonb)
returns int language plpgsql security invoker set search_path = '' as $$
declare n int;
begin
  if (select auth.uid()) is null then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  if jsonb_typeof(p_picks) is distinct from 'array' then raise exception 'キーワードの形が違います'; end if;
  n := jsonb_array_length(p_picks);
  if n > 200 then raise exception 'キーワードは 200 個までです'; end if;
  if exists (select 1 from jsonb_array_elements(p_picks) x
             where jsonb_typeof(x) <> 'object' or length(btrim(coalesce(x ->> 'name', ''))) not between 1 and 80
                or length(coalesce(x ->> 'sec', '')) not between 1 and 10) then
    raise exception 'キーワードは 1〜80 文字、大類つきで';
  end if;
  update public.app_users set prefs = prefs || jsonb_build_object('picks', p_picks), last_seen = now();   -- RLS で自分の行だけ
  if not found then raise exception 'お客さまの登録が見つかりません'; end if;
  return n;
end $$;

revoke all on function public.my_page() from public, anon;
revoke all on function public.my_keywords_set(jsonb) from public, anon;
grant execute on function public.my_page() to authenticated;
grant execute on function public.my_keywords_set(jsonb) to authenticated;
