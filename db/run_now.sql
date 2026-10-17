-- 管理ページの「今すぐ実行」ボタン：定時を待たずに GitHub Actions のワークフローを起こす。
-- 網页（管理ページ）は公開で口令なしなので、GitHub の令牌は網页に置かない。db/instant.sql と同じく
-- Supabase Vault の github_dispatch_token を使い、データベースから GitHub に頼む（pg_net）。
-- 起こせるのは下の 3 つだけ。連打されても困らないように、仕事ごとに間隔（cooldown）をあける。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（先要运行过 db/instant.sql）。

create table if not exists private.run_log (
  job text primary key,
  at  timestamptz not null
);

-- job → (ワークフロー, 間隔, 渡す inputs)
--   background  后台作業（ゲート → 小元素の補完）。ボタンからは失敗した版面の待ち時間（6 時間）も待たない
--   collect     ニュース収集（関注清单通信）
--   render      ページ生成（网页立即更新）
create or replace function public.run_now(job text)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
  tok text;
  last timestamptz;
  wf text;
  gap interval;
  inputs jsonb;
begin
  case job
    when 'background' then wf := 'background.yml'; gap := interval '3 minutes'; inputs := '{"retry_now": "true", "minutes": "40"}';
    when 'collect'    then wf := 'digest.yml';     gap := interval '10 minutes'; inputs := '{}';
    when 'render'     then wf := 'render.yml';     gap := interval '1 minute';   inputs := '{}';
    else return jsonb_build_object('ok', false, 'msg', 'この仕事はボタンから起こせません');
  end case;
  select s.decrypted_secret into tok from vault.decrypted_secrets s where s.name = 'github_dispatch_token' limit 1;
  if coalesce(tok, '') = '' then
    return jsonb_build_object('ok', false, 'msg', 'GitHub の令牌が未設定（db/instant.sql の説明）');
  end if;
  select r.at into last from private.run_log r where r.job = run_now.job;
  if last is not null and now() - last < gap then
    return jsonb_build_object('ok', false, 'msg', 'さっき起こしたばかり', 'next_at', last + gap);
  end if;
  insert into private.run_log as r (job, at) values (run_now.job, now()) on conflict on constraint run_log_pkey do update set at = excluded.at;
  perform net.http_post(
    url := 'https://api.github.com/repos/CxElegy/Wishlist/actions/workflows/' || wf || '/dispatches',
    body := jsonb_build_object('ref', 'main', 'inputs', inputs),
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
                                  'X-GitHub-Api-Version', '2022-11-28', 'User-Agent', 'wishlist-supabase',
                                  'Content-Type', 'application/json'));
  return jsonb_build_object('ok', true, 'msg', '起こしました', 'next_at', now() + gap);
exception when others then
  return jsonb_build_object('ok', false, 'msg', '起こせませんでした：' || sqlerrm);
end $$;
revoke all on function public.run_now(text) from public;
grant execute on function public.run_now(text) to anon, authenticated;
