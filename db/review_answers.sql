-- 審査ページ（docs/testground/）の答えの置き場（2026-11-02，ユーザー：触って決める審査。HARNESS「審査は触って決める」）。
-- 足しただけ（既存の表・関数は触らない）。書けるのは店長（is_admin()）だけ、読むのは secret key / Supabase MCP（policy なし）。
-- 戻し方：drop function public.review_save(text, text, jsonb); drop table public.review_answers;
create table if not exists public.review_answers (
  id bigint generated always as identity primary key,
  page text not null, step text not null, answer jsonb not null,
  created_at timestamptz not null default now());
alter table public.review_answers enable row level security;
create or replace function public.review_save(p_page text, p_step text, p_answer jsonb)
returns bigint language plpgsql security definer set search_path = '' as $$
declare new_id bigint;
begin
  if not public.is_admin() then raise exception '店長でログインしてください' using errcode = '42501'; end if;
  if length(coalesce(p_page, '')) not between 1 and 40 or length(coalesce(p_step, '')) not between 1 and 20
     or jsonb_typeof(p_answer) is distinct from 'object' or length(p_answer::text) > 200000 then raise exception '答えの形が不正'; end if;
  insert into public.review_answers (page, step, answer) values (p_page, p_step, p_answer) returning id into new_id;
  return new_id;
end $$;
revoke all on function public.review_save(text, text, jsonb) from public, anon;
grant execute on function public.review_save(text, text, jsonb) to authenticated;
