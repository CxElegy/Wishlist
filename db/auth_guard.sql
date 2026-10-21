-- 写操作的身份检查（2026-10-20，登录第 1 步）。先运行 db/auth.sql。
-- 每个写函数开头都问 public.can_edit(p_account)：开关（private.auth_flags 的 enforce）关着时永远 true = 跟以前一样；
-- 开了以后：没登录 = 不行，管理者 = 都行，一般用户 = 只有自己的 account（public.accounts.owner）。
-- 所以这个文件现在运行也不改变网站的行为；真正生效是 db/auth_enforce.sql 打开开关的那一刻。
-- 函数内容和 db/accounts.sql 一样，只在开头加了一行检查。全是 create or replace / alter policy，不删东西。

-- 投票：没登录的（anon）只在开关关着时能投；登录的人只能投进自己能改的 account
alter policy "网页只能新增投票" on public.feedback with check (not public.auth_enforced());
do $$ begin
  create policy "登录的人投进自己的 account" on public.feedback for insert to authenticated
    with check (public.can_edit(account));
exception when duplicate_object then null; end $$;
grant insert on public.feedback to authenticated;

-- 愿望清单的「加进去」：同上（这张表还没分 account，开关开了以后只有管理者）
alter policy "网页只能新增加入心愿单的请求" on public.wish_requests
  with check (status = 'pending' and handled_at is null and not public.auth_enforced());
do $$ begin
  create policy "管理者加进心愿单" on public.wish_requests for insert to authenticated
    with check (status = 'pending' and handled_at is null and (public.is_admin() or not public.auth_enforced()));
exception when duplicate_object then null; end $$;
grant insert (url, title, work, image, source) on public.wish_requests to authenticated;

create or replace function public.set_size(p_account text, p_item text, p_size text, p_pass text)
returns text language plpgsql security definer set search_path = '' as $$
begin
  if not public.can_edit(p_account) then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  if p_size not in ('S', 'M', 'L') then raise exception '篇幅只能是 S / M / L'; end if;
  if length(coalesce(p_item, '')) not between 1 and 200 then raise exception '关注项名字不对'; end if;
  insert into public.sizes (account, item, size, updated_at) values (private.acct(p_account), p_item, p_size, now())
  on conflict (account, item) do update set size = excluded.size, updated_at = now();
  perform private.kick_github();
  return p_size;
end $$;

create or replace function public.set_nav_scheme(p_account text, p_section text, p_scheme text)
returns text language plpgsql security definer set search_path = '' as $$
begin
  if not public.can_edit(p_account) then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  if length(coalesce(p_section, '')) not between 1 and 40 or p_scheme !~ '^[a-z][a-z0-9_]{0,30}$' then
    raise exception '板块か分け方の名前が不正';
  end if;
  insert into public.nav_schemes (account, section, scheme, updated_at) values (private.acct(p_account), p_section, p_scheme, now())
  on conflict (account, section) do update set scheme = excluded.scheme, updated_at = now();
  perform private.kick_github();
  return p_scheme;
end $$;

create or replace function public.submit_item(p_account text, p_action text, p_name text, p_config jsonb)
returns bigint language plpgsql security definer set search_path = '' as $$
declare new_id bigint; a text := private.acct(p_account);
begin
  if not public.can_edit(p_account) then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  p_name := btrim(coalesce(p_name, ''));
  if length(p_name) not between 1 and 80 then raise exception '名字要 1–80 个字'; end if;
  if coalesce(p_action, '') not in ('add', 'edit') then raise exception 'action 只能是 add / edit'; end if;
  if jsonb_typeof(p_config) is distinct from 'object' then raise exception '内容不对'; end if;
  if (select count(*) from public.item_requests r where r.account = a and r.status = 'pending') >= 20 then
    raise exception '待处理的请求太多了，等下次更新处理完再提交';
  end if;
  if p_action = 'add' and exists (select 1 from public.item_requests r
      where r.account = a and r.name = p_name and r.action = 'add' and r.status = 'pending') then
    raise exception '「%」已经在等待加入了', p_name;
  end if;
  insert into public.item_requests (account, action, name, config) values (a, p_action, p_name, p_config) returning id into new_id;
  perform private.kick_github();
  return new_id;
end $$;

create or replace function public.add_photo(p_account text, p_pass text, p_image text, p_thumb text, p_status text, p_note text)
returns bigint language plpgsql security definer set search_path = '' as $$
declare new_id bigint; a text := private.acct(p_account);
begin
  if not public.can_edit(p_account) then raise exception 'ログインが必要です' using errcode = '42501'; end if;
  if (select count(*) from public.photo_inbox where account = a and state <> 'done') >= 20 then
    raise exception '待处理的照片已经有 20 张了，等 Claude 处理完再传';
  end if;
  if p_status not in ('想要', '纠结') then raise exception '只能选 想要 / 纠结'; end if;
  if p_image !~ '^data:image/jpeg;base64,' or coalesce(p_thumb, '') !~ '^(data:image/jpeg;base64,.*)?$' then
    raise exception '图片格式不对';
  end if;
  insert into public.photo_inbox (account, status, note, image, thumb)
  values (a, p_status, nullif(left(coalesce(p_note, ''), 500), ''), p_image, nullif(p_thumb, '')) returning id into new_id;
  return new_id;
end $$;

create or replace function public.edit_control_set(p_account text, p_mode text default null, p_redo_add text default null, p_redo_clear text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r text[]; a text := private.acct(p_account);
begin
  if not public.can_edit(p_account) then
    return jsonb_build_object('ok', false, 'msg', 'ログインが必要です');
  end if;
  if p_mode is not null and p_mode not in ('run', 'step', 'pause') then
    return jsonb_build_object('ok', false, 'msg', 'mode は run / step / pause');
  end if;
  if p_redo_add is not null and not exists (select 1 from public.sizes s where s.account = a and s.item = p_redo_add) then
    return jsonb_build_object('ok', false, 'msg', 'その版面はありません');
  end if;
  insert into public.edit_control (account) values (a) on conflict (account) do nothing;
  select c.redo into r from public.edit_control c where c.account = a;
  if p_redo_add is not null and not (p_redo_add = any(r)) and coalesce(array_length(r, 1), 0) < 30 then r := array_append(r, p_redo_add); end if;
  if p_redo_clear = '*' then r := '{}'; elsif p_redo_clear is not null then r := array_remove(r, p_redo_clear); end if;
  update public.edit_control c set mode = coalesce(p_mode, c.mode), redo = r, updated_at = now() where c.account = a;
  return public.edit_control_get(a) || jsonb_build_object('ok', true);
end $$;

-- 「今すぐ実行」：管理者だけ。pg_cron の 'tick'（毎時 17 分）はデータベース自身が呼ぶので誰でも可（間隔 3 分で守られている）
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
  if job <> 'tick' and public.auth_enforced() and not public.is_admin() then
    return jsonb_build_object('ok', false, 'msg', '管理者だけが使えます');
  end if;
  case job
    when 'background' then wf := 'background.yml'; gap := interval '3 minutes'; inputs := '{"retry_now": "true", "minutes": "40"}';
    when 'tick'       then wf := 'background.yml'; gap := interval '3 minutes'; inputs := '{"minutes": "40"}';
    when 'edit_now'   then wf := 'background.yml'; gap := interval '10 minutes'; inputs := '{"force_edit": "true", "minutes": "5"}';
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

-- 2026-10-21：開關を開くと、ログインしない AI 編集（定時の会話）の edit_control_set が止まる。許すのは 2 つだけ：
-- 「次の 1 版面」が済んだ後の step → pause と、編み直した版面を 1 つやり直し一覧から外すこと（* で全部消すのはだめ）。
create or replace function public.edit_control_set(p_account text, p_mode text default null, p_redo_add text default null, p_redo_clear text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r text[]; a text := private.acct(p_account); cur text;
begin
  select c.mode into cur from public.edit_control c where c.account = a;
  if not public.can_edit(p_account) and not (
       p_redo_add is null
       and (p_mode is null or (p_mode = 'pause' and cur = 'step'))
       and (p_redo_clear is null or p_redo_clear <> '*')
       and (p_mode is not null or p_redo_clear is not null)) then
    return jsonb_build_object('ok', false, 'msg', 'ログインが必要です');
  end if;
  if p_mode is not null and p_mode not in ('run', 'step', 'pause') then
    return jsonb_build_object('ok', false, 'msg', 'mode は run / step / pause');
  end if;
  if p_redo_add is not null and not exists (select 1 from public.sizes s where s.account = a and s.item = p_redo_add) then
    return jsonb_build_object('ok', false, 'msg', 'その版面はありません');
  end if;
  insert into public.edit_control (account) values (a) on conflict (account) do nothing;
  select c.redo into r from public.edit_control c where c.account = a;
  if p_redo_add is not null and not (p_redo_add = any(r)) and coalesce(array_length(r, 1), 0) < 30 then r := array_append(r, p_redo_add); end if;
  if p_redo_clear = '*' then r := '{}'; elsif p_redo_clear is not null then r := array_remove(r, p_redo_clear); end if;
  update public.edit_control c set mode = coalesce(p_mode, c.mode), redo = r, updated_at = now() where c.account = a;
  return public.edit_control_get(a) || jsonb_build_object('ok', true);
end $$;
