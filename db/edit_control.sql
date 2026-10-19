-- AI 編集のコントロール（2026-10-19、ユーザーが決めた：AI 編集を一時停止・1 版面ずつ・やり直しできるように）。
-- 管理ページのボタン（口令なし）と AI 編集の定時タスク（publishable key）が読み書きする。1 行だけの表。
--   mode  run   = 整理待ちの版面を 1 つずつ全部
--         step  = 次の 1 版面だけやって、終わったら自動で pause に
--         pause = 次の版面に入る前に止まる（いま編集中の版面は最後までやる）。定時（9:00 / 18:00）も起こさない
--   redo  やり直す版面の名前（編集済みでももう一度、いちばん先に）。AI 編集がやり終えたら外す
-- 悪用されても「AI 編集が止まる / 余計に 1 版面編集する」だけ（データは消えない）。版面名は sizes にあるものだけ、redo は 30 個まで。
-- 消す語（DELETE / DROP）を使わない：Supabase 連接器の確認待ちで止まらないように。

create table if not exists public.edit_control (
  id int primary key default 1 check (id = 1),
  mode text not null default 'run',
  redo text[] not null default '{}',
  updated_at timestamptz not null default now()
);
alter table public.edit_control enable row level security;   -- ポリシーなし = 網页からは関数だけ
insert into public.edit_control (id) values (1) on conflict (id) do nothing;

create or replace function public.edit_control_get()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object('mode', c.mode, 'redo', c.redo, 'updated_at', c.updated_at) from public.edit_control c where c.id = 1;
$$;

create or replace function public.edit_control_set(p_mode text default null, p_redo_add text default null, p_redo_clear text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r text[];
begin
  if p_mode is not null and p_mode not in ('run', 'step', 'pause') then
    return jsonb_build_object('ok', false, 'msg', 'mode は run / step / pause');
  end if;
  if p_redo_add is not null and not exists (select 1 from public.sizes s where s.item = p_redo_add) then
    return jsonb_build_object('ok', false, 'msg', 'その版面はありません');
  end if;
  select c.redo into r from public.edit_control c where c.id = 1;
  if p_redo_add is not null and not (p_redo_add = any(r)) and coalesce(array_length(r, 1), 0) < 30 then
    r := array_append(r, p_redo_add);
  end if;
  if p_redo_clear = '*' then
    r := '{}';
  elsif p_redo_clear is not null then
    r := array_remove(r, p_redo_clear);
  end if;
  update public.edit_control c set mode = coalesce(p_mode, c.mode), redo = r, updated_at = now() where c.id = 1;
  return public.edit_control_get() || jsonb_build_object('ok', true);
end $$;

revoke all on function public.edit_control_get() from public;
revoke all on function public.edit_control_set(text, text, text) from public;
grant execute on function public.edit_control_get() to anon, authenticated;
grant execute on function public.edit_control_set(text, text, text) to anon, authenticated;
