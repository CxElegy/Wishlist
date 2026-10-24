-- ライブラリ（2026-10-23，用户定的）：みんなの版面の置き場。店長もお客さまも、ここから自分の版面を選ぶ（なければ 1 つ足す）。
-- 記事集め・AI 編集・デザインは版面ごとに 1 回で、追いかけている全員が同じものを受け取る。
-- 人ごとのもの（置く板块・小分類・篇幅・見たい種類・並び）は follows、👍👎・欲しい物は今までどおり account 列の表。
-- 書くのは Actions（secret key）と、ログインした本人の関数だけ。版面と記事は公開のニュースなので読むのはだれでも。だれが何を追いかけているか（follows）は本人と店長だけ。
-- 戻し方（足しただけ。消すときは運営者が SQL Editor で）：
--   drop table if exists public.follows, public.board_stories, public.boards;
--   alter table public.app_users drop column if exists ui_lang, drop column if exists model, drop column if exists board_limit;

create table if not exists public.boards (
  id          bigint generated always as identity primary key,
  key         text not null unique check (length(key) between 1 and 200),   -- 同じものかどうかの印：'wd:Q…'（Wikidata）か 'n:' + そろえた名前
  name        text not null check (length(name) between 1 and 80),          -- 代表の名前（店長の items.yaml の name）
  names       jsonb not null default '{}'::jsonb,                           -- 各言語の名前 {"ja": …, "en": …, "zh": …}
  wd          text check (wd ~ '^Q[0-9]+$'),                                -- Wikidata の番号
  parent_id   bigint references public.boards(id) on delete set null,       -- 下級のときの上級
  config      jsonb not null default '{}'::jsonb,                           -- items.yaml の 1 項目のうち、みんなで共有するもの（拾う語・除く語・記事の言語・主題・配色・小元素・アイコン…）
  followers   int not null default 0,                                       -- 追いかけている人数（0 人なら更新を止める）
  created_by  text,                                                         -- 最初に足した account
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.board_stories (
  board_id    bigint not null references public.boards(id) on delete cascade,
  day         date not null,
  stories     jsonb not null default '[]'::jsonb,                           -- その日の記事（AI 編集のあとの形。重大・頭・まとめ文も）
  pending     jsonb not null default '[]'::jsonb,                           -- 整理待ち
  updated_at  timestamptz not null default now(),
  primary key (board_id, day)
);

create table if not exists public.follows (
  account     text not null,                                                -- 'test1'（店長）か 'u_' + md5(メール) 16 字
  board_id    bigint not null references public.boards(id) on delete cascade,
  section     text,                                                         -- 置く板块（人ごと：あつ森をゲームに置く人もグッズに置く人も）
  subs        jsonb not null default '{}'::jsonb,                           -- 小分類（分け方ごと）
  also        jsonb not null default '{}'::jsonb,                           -- ほかの板块の乗換駅
  size        text check (size in ('S', 'M', 'L')),
  media       jsonb not null default '[]'::jsonb,                           -- 見たい種類（ゲーム・グッズ…）。空 = 全部
  pos         int not null default 0,                                       -- 並び（items.yaml の順）
  created_at  timestamptz not null default now(),
  primary key (account, board_id)
);
create index if not exists follows_board on public.follows (board_id);

alter table public.app_users add column if not exists ui_lang text not null default 'ja';
alter table public.app_users add column if not exists model text not null default 'sonnet' check (model in ('none', 'haiku', 'sonnet'));
alter table public.app_users add column if not exists board_limit int not null default 100 check (board_limit between 0 and 1000);

alter table public.boards enable row level security;
alter table public.board_stories enable row level security;
alter table public.follows enable row level security;
drop policy if exists boards_read on public.boards;
create policy boards_read on public.boards for select to anon, authenticated using (true);
drop policy if exists board_stories_read on public.board_stories;
create policy board_stories_read on public.board_stories for select to anon, authenticated using (true);
drop policy if exists follows_own on public.follows;
create policy follows_own on public.follows for select to authenticated
  using (account = private.user_account((select auth.jwt()) ->> 'email') or public.is_admin());
revoke insert, update, delete on public.boards, public.board_stories, public.follows from anon, authenticated;

-- 追いかけている人数をそろえる（follows が変わったら）
create or replace function private.boards_count() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  update public.boards b set followers = (select count(*) from public.follows f where f.board_id = b.id)
   where b.id in (coalesce(new.board_id, old.board_id), coalesce(old.board_id, new.board_id));
  return null;
end $$;
drop trigger if exists follows_count on public.follows;
create trigger follows_count after insert or delete or update of board_id on public.follows
  for each row execute function private.boards_count();

-- 読める版面をしぼる（2026-10-24，用户定的：案 B）：
--   ログインなし = 店長（test1）が追いかけている版面だけ（店長のページと同じ線）。お客さま = それ＋自分が追いかけている版面。店長（is_admin）= 全部。
--   だれも追いかけていない版面・お客さまだけが足した版面（n:広島旅行 など）の名前と記事は、ほかの人には見えない（HARNESS §2・§3）。
--   今の permissive の boards_read / board_stories_read（using true）は残し、restrictive のポリシーを「足す」（restrictive は AND で効く）。Actions は secret key なので RLS を通らない。
--   戻し方：drop policy boards_visible on public.boards; drop policy board_stories_visible on public.board_stories; drop function public.board_visible(bigint);
create or replace function public.board_visible(p_board bigint)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.follows f where f.board_id = p_board and f.account = 'test1')
      or ((select auth.uid()) is not null
          and (public.is_admin()
               or exists (select 1 from public.follows f
                           where f.board_id = p_board
                             and f.account = private.user_account((select auth.jwt()) ->> 'email'))));
$$;
revoke all on function public.board_visible(bigint) from public;
grant execute on function public.board_visible(bigint) to anon, authenticated;
drop policy if exists boards_visible on public.boards;
create policy boards_visible on public.boards as restrictive for select to anon, authenticated
  using (public.board_visible(id));
drop policy if exists board_stories_visible on public.board_stories;
create policy board_stories_visible on public.board_stories as restrictive for select to anon, authenticated
  using (public.board_visible(board_id));
