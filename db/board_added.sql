-- 版面を足したら、その場で後ろの仕組みを起こす（2026-11-11 店長：新規ユーザーが盤面を追加したとき、どのくらいで使えるかを KPI 化して改善）。
--
-- 前：my_keywords_set は prefs.picks を書くだけで、何も起こさなかった。ライブラリの follows・記事集め・小元素・本人のページは
--     全部 cron 待ち（library.yml 毎時・digest.yml 2 時間・library_emblem.yml 実測 4〜6 時間）。足した時刻もどこにも残らなかった。
-- 今：1. 新しく足した名前には added_at（いつ足したか）を付けて残す（KPI：harness/board_kpi.py）。前からある名前は前の added_at のまま。
--     2. 新しい名前があれば GitHub の board_added.yml を起こす（library --users → 記事集め → 本人のページ → 小元素）。
--        押しすぎの歯止め：1 人 1 時間に 6 回・全体で 30 秒に 1 回（private.board_kicks）。起こせなくても足すことは失敗しない（cron が拾う）。
-- 流し方：店長の PC の会話から（docs/rules/local-pc.md「DB を変える SQL は PC の会話で」）。
--   docker exec -i supabase-db psql -U postgres -d postgres < db/board_added.sql

create table if not exists private.board_kicks (
  account text not null,
  at timestamptz not null default now()
);
create index if not exists board_kicks_at on private.board_kicks (at);
create index if not exists board_kicks_account_at on private.board_kicks (account, at);

create or replace function private.kick_board_added(a text) returns void
language plpgsql security definer set search_path = '' as $$
declare tok text;
begin
  select s.decrypted_secret into tok from vault.decrypted_secrets s where s.name = 'github_dispatch_token' limit 1;
  if coalesce(tok, '') = '' then return; end if;
  if (select count(*) from private.board_kicks k where k.account = a and k.at > now() - interval '1 hour') >= 6 then return; end if;
  if exists (select 1 from private.board_kicks k where k.at > now() - interval '30 seconds') then return; end if;
  insert into private.board_kicks (account) values (a);
  perform net.http_post(
    url := 'https://api.github.com/repos/CxElegy/Wishlist/actions/workflows/board_added.yml/dispatches',
    body := '{"ref": "main"}'::jsonb,
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
                                  'X-GitHub-Api-Version', '2022-11-28', 'User-Agent', 'wishlist-supabase',
                                  'Content-Type', 'application/json'));
exception when others then
  raise warning 'board_added.yml を起こせなかった：%', sqlerrm;
end $$;
revoke all on function private.kick_board_added(text) from public, anon, authenticated;

create or replace function public.my_keywords_set(p_picks jsonb) returns integer
language plpgsql security definer set search_path = '' as $$
declare n int; mail text := lower((select auth.jwt()) ->> 'email'); old jsonb; fresh int; stamped jsonb; me text;
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
  select coalesce(u.prefs -> 'picks', '[]'::jsonb), u.name_key into old, me from public.app_users u where lower(u.email) = mail and u.left_at is null;
  if not found then raise exception 'お客さまの登録が見つかりません'; end if;
  -- 足した時刻：前からある名前は前の added_at（無ければ付けない）、新しい名前は今
  select coalesce(jsonb_agg(case
           when o.v is null then x.v || jsonb_build_object('added_at', now())
           when o.v ? 'added_at' then x.v || jsonb_build_object('added_at', o.v -> 'added_at')
           else x.v - 'added_at' end order by x.i), '[]'::jsonb),
         count(*) filter (where o.v is null)
    into stamped, fresh
    from jsonb_array_elements(p_picks) with ordinality x(v, i)
    left join lateral (select y from jsonb_array_elements(old) y where y ->> 'name' = x.v ->> 'name' limit 1) o(v) on true;
  update public.app_users set prefs = prefs || jsonb_build_object('picks', stamped), last_seen = now()
  where lower(email) = mail and left_at is null;
  if fresh > 0 then perform private.kick_board_added('u_' || left(md5(mail), 16)); end if;
  return n;
end $$;
