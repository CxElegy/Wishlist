-- アカウント（2026-10-19，用户定的）：test1 と test2 を「2 つのアカウント」として分ける。以後の一般ユーザーも同じ形で足す。
-- 自分ごとのデータ（投票・篇幅・目次の分け方・依頼・写真・AI 編集の開關・更新中の帯・集めた記事）の表に account を持たせ、
-- 網页は自分の account を渡す関数（p_account つき）だけを使う。前からある p_account なしの関数は test1 専用のまま残す
-- （凍結した test1 のページが前と同じに動く。関数を消さない＝破壊的な変更をしない）。
-- account の名前は英小文字・数字・_- の 1〜40 文字。いまの網页は test2。

-- 1. 列を足す（既存の行は test1）
alter table public.feedback      add column if not exists account text not null default 'test1';
alter table public.sizes         add column if not exists account text not null default 'test1';
alter table public.nav_schemes   add column if not exists account text not null default 'test1';
alter table public.item_requests add column if not exists account text not null default 'test1';
alter table public.photo_inbox   add column if not exists account text not null default 'test1';
alter table public.edit_control  add column if not exists account text not null default 'test1';
alter table public.live_status   add column if not exists account text not null default 'test1';
alter table public.news          add column if not exists account text not null default 'test1';
alter table public.stories       add column if not exists account text not null default 'test1';
alter table public.price_history add column if not exists account text not null default 'test1';

-- 2. test2 を始めた後（2026-10-19 12:36 UTC）にできた行は test2 のもの
update public.feedback      set account = 'test2' where created_at  >= '2026-10-19T12:36:00Z';
update public.item_requests set account = 'test2' where created_at  >= '2026-10-19T12:36:00Z';
update public.photo_inbox   set account = 'test2' where created_at  >= '2026-10-19T12:36:00Z';
update public.live_status   set account = 'test2' where updated_at  >= '2026-10-19T12:36:00Z';
update public.news          set account = 'test2' where first_seen  >= '2026-10-19T12:36:00Z';
update public.stories       set account = 'test2' where synced_at   >= '2026-10-19T12:36:00Z';
update public.price_history set account = 'test2' where observed_at >= '2026-10-19T12:36:00Z';

-- 3. 一意の鍵に account を入れる（同じ名前の関注項が別のアカウントにあってよい）
alter table public.sizes       drop constraint if exists sizes_pkey,       add primary key (account, item);
alter table public.nav_schemes drop constraint if exists nav_schemes_pkey, add primary key (account, section);
alter table public.live_status drop constraint if exists live_status_pkey, add primary key (account, board, proc);
alter table public.news        drop constraint if exists news_pkey,        add primary key (account, item, url);
alter table public.stories     drop constraint if exists stories_pkey,     add primary key (account, issue_date, item, pos);
alter table public.edit_control drop constraint if exists edit_control_id_check;
alter table public.edit_control drop constraint if exists edit_control_pkey, add primary key (account);
alter table public.edit_control alter column id drop default;
alter table public.edit_control alter column id drop not null;

-- test2 の最初の行：AI 編集の開關（14:29 UTC に test2 で押された「やり直す」を引き継ぐ）・篇幅
insert into public.edit_control (account, mode, redo, updated_at)
  select 'test2', c.mode, c.redo, c.updated_at from public.edit_control c where c.account = 'test1'
  on conflict (account) do nothing;
update public.edit_control set redo = '{}' where account = 'test1';
insert into public.sizes (account, item, size) values ('test2', 'ちいかわ', 'M') on conflict do nothing;

-- 4. アカウント名の検査
create or replace function private.acct(p text) returns text language plpgsql immutable as $$
begin
  if coalesce(p, '') !~ '^[a-z0-9_-]{1,40}$' then raise exception 'account が不正'; end if;
  return p;
end $$;

-- 5. 網页が使う関数（p_account つき）
create or replace function public.my_votes(p_account text)
returns table (url text, vote smallint)
language sql stable security definer set search_path = public as $$
  select l.url, l.vote from (
    select distinct on (f.url) f.url, f.vote, f.created_at from public.feedback f
    where f.account = private.acct(p_account)
    order by f.url, f.created_at desc, f.id desc
  ) l where l.vote <> 0 order by l.created_at desc limit 5000;
$$;

create or replace function public.get_sizes(p_account text)
returns table (item text, size text) language sql stable security definer set search_path = ''
as $$ select s.item, s.size from public.sizes s where s.account = private.acct(p_account) order by s.item $$;

create or replace function public.set_size(p_account text, p_item text, p_size text, p_pass text)
returns text language plpgsql security definer set search_path = '' as $$
begin
  if p_size not in ('S', 'M', 'L') then raise exception '篇幅只能是 S / M / L'; end if;
  if length(coalesce(p_item, '')) not between 1 and 200 then raise exception '关注项名字不对'; end if;
  insert into public.sizes (account, item, size, updated_at) values (private.acct(p_account), p_item, p_size, now())
  on conflict (account, item) do update set size = excluded.size, updated_at = now();
  perform private.kick_github();
  return p_size;
end $$;

create or replace function public.get_nav_schemes(p_account text)
returns table (section text, scheme text) language sql stable security definer set search_path = ''
as $$ select n.section, n.scheme from public.nav_schemes n where n.account = private.acct(p_account) order by n.section $$;

create or replace function public.set_nav_scheme(p_account text, p_section text, p_scheme text)
returns text language plpgsql security definer set search_path = '' as $$
begin
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

create or replace function public.list_item_requests(p_account text)
returns table (name text, action text, status text, note text, created_at timestamptz)
language sql stable security definer set search_path = ''
as $$ select r.name, r.action, r.status, r.note, r.created_at from public.item_requests r
      where r.account = private.acct(p_account) and (r.status = 'pending' or r.created_at > now() - interval '3 days')
      order by r.id desc limit 20 $$;

create or replace function public.add_photo(p_account text, p_pass text, p_image text, p_thumb text, p_status text, p_note text)
returns bigint language plpgsql security definer set search_path = '' as $$
declare new_id bigint; a text := private.acct(p_account);
begin
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

create or replace function public.get_photo_inbox(p_account text)
returns table (id bigint, created_at timestamptz, status text, note text, state text, wish_name text, thumb text)
language sql stable security definer set search_path = ''
as $$ select i.id, i.created_at, i.status, i.note, i.state, i.wish_name, i.thumb from public.photo_inbox i
      where i.account = private.acct(p_account) and (i.state <> 'done' or i.created_at > now() - interval '3 days')
      order by i.id desc limit 20 $$;

create or replace function public.edit_control_get(p_account text)
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce((select jsonb_build_object('mode', c.mode, 'redo', c.redo, 'updated_at', c.updated_at)
                   from public.edit_control c where c.account = private.acct(p_account)),
                  jsonb_build_object('mode', 'run', 'redo', '[]'::jsonb, 'updated_at', null));
$$;

create or replace function public.edit_control_set(p_account text, p_mode text default null, p_redo_add text default null, p_redo_clear text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r text[]; a text := private.acct(p_account);
begin
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

create or replace function public.live_boards(p_account text)
returns table (board text, proc text, state text, found int, note text, started_at timestamptz, eta_at timestamptz)
language sql stable security definer set search_path = public as $$
  select board, proc, state, found, note, started_at, eta_at from public.live_status
  where account = private.acct(p_account) and updated_at > now() - interval '45 minutes' order by started_at;
$$;

create or replace function public.live_report(p_account text, p_board text, p_proc text, p_state text, p_note text default null, p_eta_min int default null)
returns void language plpgsql security definer set search_path = public as $$
declare a text := private.acct(p_account);
begin
  if p_proc not in ('edit', 'emblem') then raise exception 'proc'; end if;
  if p_state = 'clear' then
    delete from public.live_status where account = a and proc = p_proc and (p_board = '*' or board = p_board);
    return;
  end if;
  if p_state not in ('work', 'wait') then raise exception 'state'; end if;
  if not exists (select 1 from public.sizes where account = a and item = p_board) then raise exception 'board'; end if;
  insert into public.live_status (account, board, proc, state, note, started_at, eta_at, updated_at)
  values (a, p_board, p_proc, p_state, left(p_note, 40), now(),
          case when p_eta_min is null then null else now() + make_interval(mins => least(greatest(p_eta_min, 1), 90)) end, now())
  on conflict (account, board, proc) do update set state = excluded.state, note = excluded.note, eta_at = excluded.eta_at,
    updated_at = now(),
    started_at = case when public.live_status.updated_at > now() - interval '45 minutes' then public.live_status.started_at else now() end;
end $$;

-- 6. 前からの関数（p_account なし）は test1 専用（凍結した test1 のページ用）。名前も引数も同じまま中身だけ test1 に絞る
create or replace function public.my_votes() returns table (url text, vote smallint)
language sql stable security definer set search_path = public as $$ select * from public.my_votes('test1') $$;
create or replace function public.get_sizes() returns table (item text, size text)
language sql stable security definer set search_path = '' as $$ select * from public.get_sizes('test1') $$;
create or replace function public.set_size(p_item text, p_size text, p_pass text) returns text
language sql security definer set search_path = '' as $$ select public.set_size('test1', p_item, p_size, p_pass) $$;
create or replace function public.get_nav_schemes() returns table (section text, scheme text)
language sql stable security definer set search_path = '' as $$ select * from public.get_nav_schemes('test1') $$;
create or replace function public.set_nav_scheme(p_section text, p_scheme text) returns text
language sql security definer set search_path = '' as $$ select public.set_nav_scheme('test1', p_section, p_scheme) $$;
create or replace function public.submit_item(p_action text, p_name text, p_config jsonb) returns bigint
language sql security definer set search_path = '' as $$ select public.submit_item('test1', p_action, p_name, p_config) $$;
create or replace function public.list_item_requests() returns table (name text, action text, status text, note text, created_at timestamptz)
language sql stable security definer set search_path = '' as $$ select * from public.list_item_requests('test1') $$;
create or replace function public.add_photo(p_pass text, p_image text, p_thumb text, p_status text, p_note text) returns bigint
language sql security definer set search_path = '' as $$ select public.add_photo('test1', p_pass, p_image, p_thumb, p_status, p_note) $$;
create or replace function public.get_photo_inbox() returns table (id bigint, created_at timestamptz, status text, note text, state text, wish_name text, thumb text)
language sql stable security definer set search_path = '' as $$ select * from public.get_photo_inbox('test1') $$;
create or replace function public.edit_control_get() returns jsonb
language sql stable security definer set search_path = '' as $$ select public.edit_control_get('test1') $$;
create or replace function public.edit_control_set(p_mode text default null, p_redo_add text default null, p_redo_clear text default null) returns jsonb
language sql security definer set search_path = '' as $$ select public.edit_control_set('test1', p_mode, p_redo_add, p_redo_clear) $$;
create or replace function public.live_boards() returns table (board text, proc text, state text, found int, note text, started_at timestamptz, eta_at timestamptz)
language sql stable security definer set search_path = public as $$ select * from public.live_boards('test1') $$;
create or replace function public.live_status() returns table (board text, proc text, state text, found int, started_at timestamptz, eta_at timestamptz)
language sql stable security definer set search_path = public as $$ select board, proc, state, found, started_at, eta_at from public.live_boards('test1') $$;
create or replace function public.live_report(p_board text, p_proc text, p_state text, p_note text default null, p_eta_min int default null) returns void
language sql security definer set search_path = public as $$ select public.live_report('test1', p_board, p_proc, p_state, p_note, p_eta_min) $$;

-- 7. 権限（網页の publishable key = anon）
revoke all on function public.my_votes(text), public.get_sizes(text), public.set_size(text, text, text, text),
  public.get_nav_schemes(text), public.set_nav_scheme(text, text, text), public.submit_item(text, text, text, jsonb),
  public.list_item_requests(text), public.add_photo(text, text, text, text, text, text), public.get_photo_inbox(text),
  public.edit_control_get(text), public.edit_control_set(text, text, text, text), public.live_boards(text),
  public.live_report(text, text, text, text, text, int) from public;
grant execute on function public.my_votes(text), public.get_sizes(text), public.set_size(text, text, text, text),
  public.get_nav_schemes(text), public.set_nav_scheme(text, text, text), public.submit_item(text, text, text, jsonb),
  public.list_item_requests(text), public.add_photo(text, text, text, text, text, text), public.get_photo_inbox(text),
  public.edit_control_get(text), public.edit_control_set(text, text, text, text), public.live_boards(text),
  public.live_report(text, text, text, text, text, int) to anon, authenticated;
