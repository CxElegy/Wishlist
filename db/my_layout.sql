-- お客さまが自分の篇幅（S / M / L）と小分類の分け方を設定ページで変える（2026-10-24）。
-- 店長は set_size / set_nav_scheme（p_account = test1）。お客さまは public.accounts に行がないので can_edit が通らない →
-- ログインした本人の account（public.my_account() = 'u_' + md5(メール) 16 字）にだけ書く関数を足す。p_account は取らない（ほかの人の分は書けない）。
--   篇幅：ライブラリの follows.size（本人の行、db/library.sql）。follows にまだない（足したばかり）ものは app_users.prefs.sizes に覚える。
--         sizes 表には書かない（get_sizes(p_account) はだれでも読めるので、お客さまの追いかけているものの名前が漏れる）。
--   分け方：nav_schemes 表（account = 本人）。板块と分け方の id だけなので漏れて困るものはない。
-- 変えたら render.yml を起こす（scripts/user_pages.py が本人のページを作り直す）。押すたびに起こす：render.yml は
-- concurrency の cancel-in-progress なので、続けて押しても最後に押したあとの回が DB を読んで勝つ（2026-10-24、前は 60 秒に 1 回に
-- 間引いていて、続けて押した 2 回目以降が次の収集まで出なかった）。押しすぎの歯止めは 1 人 10 分に 30 回（private.render_kicks）。
-- create / create or replace だけ。消す文・表の形を変える文はない。

create table if not exists private.render_kick (
  id  int primary key default 1 check (id = 1),
  at  timestamptz not null
);
create table if not exists private.render_kicks (
  at       timestamptz not null default now(),
  account  text not null
);
create index if not exists render_kicks_account_at on private.render_kicks (account, at);

create or replace function private.kick_render()
returns void language plpgsql security definer set search_path = '' as $$
declare tok text; a text := coalesce(public.my_account(), '');
begin
  select s.decrypted_secret into tok from vault.decrypted_secrets s where s.name = 'github_dispatch_token' limit 1;
  if coalesce(tok, '') = '' then return; end if;
  if (select count(*) from private.render_kicks k where k.account = a and k.at > now() - interval '10 minutes') >= 30 then return; end if;
  insert into private.render_kicks (account) values (a);
  insert into private.render_kick (id, at) values (1, now()) on conflict (id) do update set at = excluded.at;
  perform net.http_post(
    url := 'https://api.github.com/repos/CxElegy/Wishlist/actions/workflows/render.yml/dispatches',
    body := '{"ref": "main"}'::jsonb,
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
                                  'X-GitHub-Api-Version', '2022-11-28', 'User-Agent', 'wishlist-supabase',
                                  'Content-Type', 'application/json'));
exception when others then
  raise warning 'render.yml を起こせなかった：%', sqlerrm;   -- 保存は残る。次の収集のあとの作り直しで反映
end $$;
revoke all on function private.kick_render() from public, anon, authenticated;

create or replace function public.my_size_set(p_name text, p_size text)
returns text language plpgsql security definer set search_path = '' as $$
declare a text := public.my_account(); mail text := lower((select auth.jwt()) ->> 'email');
begin
  if (select auth.uid()) is null or coalesce(mail, '') = '' then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  if p_size not in ('S', 'M', 'L') then raise exception '篇幅は S / M / L'; end if;
  p_name := btrim(coalesce(p_name, ''));
  if length(p_name) not between 1 and 80 then raise exception '名前が違います'; end if;
  update public.follows f set size = p_size
    from public.boards b where b.id = f.board_id and f.account = a and lower(b.name) = lower(p_name);
  update public.app_users set prefs = jsonb_set(prefs, '{sizes}', coalesce(prefs -> 'sizes', '{}'::jsonb) || jsonb_build_object(p_name, p_size))
   where lower(email) = mail and left_at is null;
  if not found then raise exception 'お客さまの登録が見つかりません'; end if;
  perform private.kick_render();
  return p_size;
end $$;

create or replace function public.my_nav_scheme_set(p_section text, p_scheme text)
returns text language plpgsql security definer set search_path = '' as $$
declare a text := public.my_account();
begin
  if (select auth.uid()) is null or coalesce((select auth.jwt()) ->> 'email', '') = '' then
    raise exception 'ログインが必要です' using errcode = '42501';
  end if;
  if length(coalesce(p_section, '')) not between 1 and 40 or p_scheme !~ '^[a-z][a-z0-9_]{0,30}$' then
    raise exception '板块か分け方の名前が不正';
  end if;
  insert into public.nav_schemes (account, section, scheme, updated_at) values (private.acct(a), p_section, p_scheme, now())
  on conflict (account, section) do update set scheme = excluded.scheme, updated_at = now();
  perform private.kick_render();
  return p_scheme;
end $$;

revoke all on function public.my_size_set(text, text) from public, anon;
revoke all on function public.my_nav_scheme_set(text, text) from public, anon;
grant execute on function public.my_size_set(text, text) to authenticated;
grant execute on function public.my_nav_scheme_set(text, text) to authenticated;
revoke all on table private.render_kicks from public, anon, authenticated;
