-- my_votes(p_account) の門（2026-11-17）：ログインして、その account を変えられる人にだけ票を返す。
--
-- 何：my_votes(text) の中身に「auth.uid() が空でなく、かつ can_edit(p_account)」を足す。それ以外（访客・他人・お客さま）は空の表を返す（エラーにしない）。
--     anon・public から execute を外し、authenticated にだけ残す。引数なしの my_votes()（凍結した test1 ページ用）も anon から外す
--     （中身は my_votes('test1') を呼ぶだけなので、門は自動で効く）。名前・引数・返す形（url text, vote smallint）は変えない。
-- なぜ：公開鍵（anon）で REST から my_votes を呼ぶと、店長（test1）の最後の票が誰にでも読めた（ページは #1042 で访客に塗らなくしたが、API は開いたままだった）。
--     can_edit は enforce が false だと誰でも true になるので、auth.uid() の有無も一緒に見る（開關の開け閉めに左右されない）。
-- 影響しないもの：digest.py recommend は REST の feedback 表を service key で直に読む（my_votes を呼ばない）。AI 編集・Actions も同じ。
--     お客さま本人の票は my_votes_own（本人の account・authenticated 限定）で、この関数を使わない。お客さま（u_…）の票は前から返さない（下に残す）。
-- 流し方（店長の PC・docs/rules/local-pc.md「DB を変える SQL は PC の会話で」）。まだどこにも流していない：
--   docker exec -i supabase-db psql -U postgres -d postgres < db/my_votes_guard.sql
--   何度流しても同じ（create or replace・grant/revoke）。
-- 確かめ（流したあと）：anon の鍵で POST /rest/v1/rpc/my_votes {"p_account":"test1"} → 401/403（権限なし）。
--     店長でログインしたページ → 👍👎 が今までどおり塗られる。
-- 戻し方（前の形。my_votes_own.sql の定義と my_votes.sql / accounts.sql の grant）：
--   create or replace function public.my_votes(p_account text)
--   returns table (url text, vote smallint) language sql stable security definer set search_path = public as $$
--     select l.url, l.vote from (
--       select distinct on (f.url) f.url, f.vote, f.created_at from public.feedback f
--       where f.account = private.acct(p_account) and p_account not like 'u\_%'
--       order by f.url, f.created_at desc, f.id desc
--     ) l where l.vote <> 0 order by l.created_at desc limit 5000;
--   $$;
--   grant execute on function public.my_votes(text) to anon;
--   grant execute on function public.my_votes() to anon;

create or replace function public.my_votes(p_account text)
returns table (url text, vote smallint)
language sql stable security definer set search_path = public as $$
  select l.url, l.vote from (
    select distinct on (f.url) f.url, f.vote, f.created_at from public.feedback f
    where (select auth.uid()) is not null
      and public.can_edit(p_account)
      and f.account = private.acct(p_account) and p_account not like 'u\_%'
    order by f.url, f.created_at desc, f.id desc
  ) l where l.vote <> 0 order by l.created_at desc limit 5000;
$$;

revoke all on function public.my_votes(text) from public, anon;
grant execute on function public.my_votes(text) to authenticated;
revoke all on function public.my_votes() from public, anon;
grant execute on function public.my_votes() to authenticated;
