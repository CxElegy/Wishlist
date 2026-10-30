-- 管理ページ④AI 編集（2026-10-30）：ライブラリの全版面（お客さま・テスト用を含む）の AI 編集の状態を店長が読む。
-- 版面ごとに最新の日・載せた記事の本数・整理待ちの本数・更新時刻。店長（is_admin）だけ。足しただけ（表の形は変えない）。
-- 戻し方：drop function public.admin_board_edit_state();
create or replace function public.admin_board_edit_state()
returns table (board_id bigint, name text, followers int, day date, stories int, pending int, edited_at timestamptz)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  return query
    select b.id, b.name, b.followers, s.day,
           coalesce(jsonb_array_length(s.stories), 0), coalesce(jsonb_array_length(s.pending), 0), s.updated_at
      from public.boards b
      left join lateral (select * from public.board_stories x where x.board_id = b.id order by x.day desc limit 1) s on true
     order by b.followers desc, b.id;
end;
$$;
revoke all on function public.admin_board_edit_state() from public;
revoke all on function public.admin_board_edit_state() from anon;
grant execute on function public.admin_board_edit_state() to authenticated;
