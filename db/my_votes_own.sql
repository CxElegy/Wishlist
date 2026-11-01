-- お客さまの 👍👎 は本人の account（public.my_account() = 'u_' + md5(メール) 16 字）の feedback 行に入る（2026-11-02，ユーザー：
-- 「ユーザーの機能は管理できない以外、店長と同じ。個人保持の Like / dislike」）。店長の票（account = test1）とは混ざらない。
-- p_account を取らない（ほかの人の票は書けない・読めない）。add だけ：消す文・表の形を変える文はない。
create or replace function public.my_vote_add(p_url text, p_vote smallint, p_kind text default null, p_title text default null,
                                              p_work text default null, p_because text default null,
                                              p_hits text[] default null, p_words text[] default null)
returns void language plpgsql security definer set search_path = '' as $$
declare a text := public.my_account();
begin
  if (select auth.uid()) is null or coalesce(a, '') = '' then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  if p_vote not in (-1, 0, 1) or length(coalesce(p_url, '')) not between 1 and 2000 then raise exception '票が不正'; end if;
  if (select count(*) from public.feedback f where f.account = a and f.created_at > now() - interval '1 minute') >= 120 then
    raise exception '押しすぎです。少し待ってください';
  end if;
  insert into public.feedback (account, url, vote, kind, title, work, because, hits, words)
  values (a, p_url, p_vote, left(p_kind, 30), left(p_title, 500), left(p_work, 200), left(p_because, 200),
          p_hits[1:20], p_words[1:20]);
end $$;
revoke all on function public.my_vote_add(text, smallint, text, text, text, text, text[], text[]) from public, anon;
grant execute on function public.my_vote_add(text, smallint, text, text, text, text, text[], text[]) to authenticated;

create or replace function public.my_votes_own()
returns table (url text, vote smallint) language sql stable security definer set search_path = public as $$
  select l.url, l.vote from (
    select distinct on (f.url) f.url, f.vote, f.created_at from public.feedback f
    where f.account = public.my_account() order by f.url, f.created_at desc, f.id desc
  ) l where l.vote <> 0 order by l.created_at desc limit 5000;
$$;
revoke all on function public.my_votes_own() from public, anon;
grant execute on function public.my_votes_own() to authenticated;

-- 公開の my_votes(p_account) は、お客さま（u_…）の票は返さない（本人は my_votes_own、店長は管理ページ）
create or replace function public.my_votes(p_account text)
returns table (url text, vote smallint) language sql stable security definer set search_path = public as $$
  select l.url, l.vote from (
    select distinct on (f.url) f.url, f.vote, f.created_at from public.feedback f
    where f.account = private.acct(p_account) and p_account not like 'u\_%'
    order by f.url, f.created_at desc, f.id desc
  ) l where l.vote <> 0 order by l.created_at desc limit 5000;
$$;
