-- 管理ページ「②版面」から、ライブラリの版面（お客さまの版面）の配色を店長が変える（2026-10-29，用户定った管理画面の段）。
-- 店長だけが呼べる。boards.config.theme（配色の手書き＝theme.resolve の manual。一部の字段だけでもよい）を書く。{} を渡すと手書きを外す（封面から取る色に戻る）。
-- 足しただけ（表の形は変えない）。戻し方：drop function public.board_theme_set(bigint, jsonb);
create or replace function public.board_theme_set(p_board bigint, p_theme jsonb)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
  k text;
begin
  if not public.is_admin() then raise exception '管理者だけが使えます' using errcode = '42501'; end if;
  if jsonb_typeof(p_theme) <> 'object' then raise exception '配色の形が正しくない'; end if;
  for k in select jsonb_object_keys(p_theme) loop
    if k not in ('bg', 'fg', 'accent', 'alt_bg', 'alt_fg', 'alt_accent') then raise exception '知らない字段: %', k; end if;
    if jsonb_typeof(p_theme -> k) <> 'string' or (p_theme ->> k) !~ '^#[0-9A-Fa-f]{6}$' then raise exception '色は #RRGGBB: %', k; end if;
  end loop;
  update public.boards
     set config = case when p_theme = '{}'::jsonb then config - 'theme' else jsonb_set(config, '{theme}', p_theme) end,
         updated_at = now()
   where id = p_board;
  if not found then raise exception '版面がありません'; end if;
end;
$$;
revoke all on function public.board_theme_set(bigint, jsonb) from public;
-- Supabase は anon にも既定で execute を付ける（from public だけでは外れない）。2026-10-29：anon からも外した
revoke all on function public.board_theme_set(bigint, jsonb) from anon;
grant execute on function public.board_theme_set(bigint, jsonb) to authenticated;
