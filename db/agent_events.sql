-- 会話（セッション）の記録（2026-10-29，BACKLOG「全部の会話が何をしているかを記録して見る」）。足すだけ。
-- 書く：service_role だけが agent_event_add を呼べる（anon・お客さまは呼べない＝荒らされない）。読む：is_admin() だけ。
create table if not exists public.agent_events (
  id bigint generated always as identity primary key,
  ts timestamptz not null default now(),
  event text not null,        -- SessionStart / PostToolUse / Stop / SubagentStop
  session text not null,      -- 会話の id の先頭 8 字（ハッシュ）
  label text,                 -- どの係（worktree 名・Workflow のラベル）
  tool text,
  summary text,               -- 短い要約（道具の入力はそのまま書かない）
  dur_ms integer,
  ok boolean
);
alter table public.agent_events enable row level security;
drop policy if exists agent_events_read on public.agent_events;
create policy agent_events_read on public.agent_events for select using (public.is_admin());
create index if not exists agent_events_ts on public.agent_events (ts desc);

create or replace function public.agent_event_add(p_rows jsonb) returns integer
language sql security definer set search_path = public as $$
  with ins as (
    insert into public.agent_events (ts, event, session, label, tool, summary, dur_ms, ok)
    select coalesce((r->>'ts')::timestamptz, now()), r->>'event', r->>'session', r->>'label', r->>'tool',
           left(r->>'summary', 300), (r->>'dur_ms')::int, (r->>'ok')::boolean
    from jsonb_array_elements(p_rows) r returning 1)
  select count(*)::int from ins;
$$;
revoke all on function public.agent_event_add(jsonb) from public, anon, authenticated;
grant execute on function public.agent_event_add(jsonb) to service_role;
