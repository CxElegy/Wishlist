-- 版面の「更新中」の帯（render.BUSY_JS）が読む：いま裏でどの版面を作り直しているか。
-- 書く人：収集（GitHub Actions・secret key で直接）／AI 編集・小元素の自動補完（Claude の定時タスク・live_report() 経由）。
-- 網页は live_status() で読むだけ（publishable key）。表そのものは網页から読めない・書けない。
-- 在 Supabase → SQL Editor 里整段粘贴、运行一次即可（Claude 可以用 Supabase 连接器代为执行）。

create table if not exists public.live_status (
  board text not null,              -- 関注項の名前（items.yaml の name）
  proc text not null,               -- collect / edit / emblem
  state text not null,              -- fetch / found / work / wait（表示は note）
  found int not null default 0,     -- 新着の件数（収集）
  note text,                        -- 帯に出す言葉（「AI が編集しています」など）
  started_at timestamptz not null default now(),
  eta_at timestamptz,               -- 網页に出るまでの予想時刻
  updated_at timestamptz not null default now(),
  primary key (board, proc)
);
alter table public.live_status add column if not exists note text;
alter table public.live_status enable row level security;   -- ポリシーなし = 網页からは直接触れない

-- 古い読み口（note なし）。網页は live_boards() を読む。消すのは破壊的変更なので残しておく
create or replace function public.live_status()
returns table (board text, proc text, state text, found int, started_at timestamptz, eta_at timestamptz)
language sql stable security definer set search_path = public as $$
  select board, proc, state, found, started_at, eta_at from public.live_status
  where updated_at > now() - interval '45 minutes'
  order by started_at;
$$;
revoke all on function public.live_status() from public;
grant execute on function public.live_status() to anon;

create or replace function public.live_boards()
returns table (board text, proc text, state text, found int, note text, started_at timestamptz, eta_at timestamptz)
language sql stable security definer set search_path = public as $$
  select board, proc, state, found, note, started_at, eta_at from public.live_status
  where updated_at > now() - interval '45 minutes'
  order by started_at;
$$;
revoke all on function public.live_boards() from public;
grant execute on function public.live_boards() to anon;

-- Claude の定時タスク（secret key を持たない）が書くための入口。できることを絞る：
--   proc は edit / emblem だけ、版面は sizes にある名前だけ、言葉は 40 文字・予想は 90 分まで、
--   p_state = 'clear' で消す（p_board = '*' ならその proc を全部）。悪用されても「偽の帯が最長 45 分出る」だけ。
create or replace function public.live_report(p_board text, p_proc text, p_state text, p_note text default null, p_eta_min int default null)
returns void language plpgsql security definer set search_path = public as $$
begin
  if p_proc not in ('edit', 'emblem') then raise exception 'proc'; end if;
  if p_state = 'clear' then
    delete from public.live_status where proc = p_proc and (p_board = '*' or board = p_board);
    return;
  end if;
  if p_state not in ('work', 'wait') then raise exception 'state'; end if;
  if not exists (select 1 from public.sizes where item = p_board) then raise exception 'board'; end if;
  insert into public.live_status (board, proc, state, note, started_at, eta_at, updated_at)
  values (p_board, p_proc, p_state, left(p_note, 40), now(),
          case when p_eta_min is null then null else now() + make_interval(mins => least(greatest(p_eta_min, 1), 90)) end, now())
  on conflict (board, proc) do update set state = excluded.state, note = excluded.note, eta_at = excluded.eta_at,
    updated_at = now(),
    started_at = case when public.live_status.updated_at > now() - interval '45 minutes' then public.live_status.started_at else now() end;
end;
$$;
revoke all on function public.live_report(text, text, text, text, int) from public;
grant execute on function public.live_report(text, text, text, text, int) to anon;
