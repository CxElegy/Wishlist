-- 小元素の管理（2026-10-26，用户定的）：管理ページ「小元素」欄から、ライブラリの版面（お客さまの版面）の小元素を 替える・固定・外す。
-- 店長だけが呼べる。依頼は boards.config.emblem_requests に足すだけ（実際に直すのは Actions の library_emblem.py の次の回：同じ人の別の写真を探す）。
-- 2026-10-26：候補から選ぶ（_emblem_cands・_emblem_pick）も受ける。
-- 足しただけ（表の形は変えない）。戻し方：drop function public.board_emblem_request(bigint, jsonb);
create or replace function public.board_emblem_request(p_board bigint, p_edit jsonb)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
  k text;
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  if jsonb_typeof(p_edit) <> 'object' or p_edit = '{}'::jsonb then raise exception '依頼が空です'; end if;
  for k in select jsonb_object_keys(p_edit) loop
    if k not in ('_emblem_swap', '_emblem_lock', '_emblem_reject', '_emblem_cands', '_emblem_pick') then raise exception '知らない依頼: %', k; end if;
    if jsonb_typeof(p_edit -> k) <> 'array' or jsonb_array_length(p_edit -> k) not between 1 and 50 then raise exception '依頼の数が正しくない'; end if;
  end loop;
  update public.boards
     set config = jsonb_set(config, '{emblem_requests}', coalesce(config -> 'emblem_requests', '[]'::jsonb) || jsonb_build_array(p_edit)),
         updated_at = now()
   where id = p_board;
  if not found then raise exception '版面がありません'; end if;
end;
$$;
revoke all on function public.board_emblem_request(bigint, jsonb) from public;
grant execute on function public.board_emblem_request(bigint, jsonb) to authenticated;
