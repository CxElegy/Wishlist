-- 设置页一提交（新增 / 修改关注项、改篇幅），数据库立刻叫 GitHub 跑「网页请求」工作流（.github/workflows/requests.yml），
-- 事件触发，没有定时轮询。在 Supabase → SQL Editor 里整段粘贴、运行一次即可（需要先运行过 db/settings.sql、db/item_requests.sql）。
--
-- 需要一个 GitHub 令牌（只给这个仓库的 Actions 读写权限）：
--   github.com/settings/personal-access-tokens/new → Repository access 选 Only select repositories → CxElegy/Wishlist
--   → Permissions → Repository permissions → Actions：Read and write → Generate token
-- 存进 Supabase Vault（Project Settings → Vault → Add new secret，名字 github_dispatch_token），或者运行：
--   select vault.create_secret('github_pat_……', 'github_dispatch_token');
-- 换令牌：select vault.update_secret((select id from vault.secrets where name = 'github_dispatch_token'), '新令牌');
-- 没设令牌时什么都不做，请求等每 2 小时一次的「关注清单通信」处理。叫的结果在 net._http_response（204 = 成功）。

create extension if not exists pg_net with schema extensions;

create table if not exists private.dispatch_log (
  id  int primary key default 1 check (id = 1),
  at  timestamptz not null
);

-- 20 秒内只叫一次：连点几下篇幅时，第一次叫起来的那次运行会一起处理
create or replace function private.kick_github()
returns void
language plpgsql security definer set search_path = ''
as $$
declare
  tok text;
  last timestamptz;
begin
  select s.decrypted_secret into tok from vault.decrypted_secrets s where s.name = 'github_dispatch_token' limit 1;
  if coalesce(tok, '') = '' then return; end if;
  select d.at into last from private.dispatch_log d where d.id = 1;
  if last is not null and now() - last < interval '20 seconds' then return; end if;
  insert into private.dispatch_log (id, at) values (1, now()) on conflict (id) do update set at = excluded.at;
  perform net.http_post(
    url := 'https://api.github.com/repos/CxElegy/Wishlist/actions/workflows/requests.yml/dispatches',
    body := '{"ref": "main"}'::jsonb,
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
                                  'X-GitHub-Api-Version', '2022-11-28', 'User-Agent', 'wishlist-supabase',
                                  'Content-Type', 'application/json'));
exception when others then
  raise warning '叫 GitHub 失败：%', sqlerrm;   -- 失败不影响提交本身，每 2 小时的更新会处理
end $$;
revoke all on function private.kick_github() from public, anon, authenticated;

-- 网页上显示「马上处理」还是「等下次更新」用：只告诉有没有设置令牌，不给令牌本身
create or replace function public.instant_enabled()
returns boolean
language sql stable security definer set search_path = ''
as $$ select exists (select 1 from vault.decrypted_secrets s where s.name = 'github_dispatch_token' and coalesce(s.decrypted_secret, '') <> '') $$;
revoke all on function public.instant_enabled() from public;
grant execute on function public.instant_enabled() to anon, authenticated;

-- submit_item()（db/item_requests.sql）和 set_size()（db/settings.sql）存好之后都会 perform private.kick_github()
