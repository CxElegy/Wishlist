-- お客さまのページの置き場（2026-10-24，用户定的：本人と店長だけが見る。公開のリポジトリ・Pages には置かない）
-- scripts/user_pages.py（Actions の secret key）が pages/<account>/index.html を書き、
-- 網页（render.AUTH_JS）がログインした本人の鍵で読む。account = 'u_' + md5(メール) 16 字（private.user_account と同じ式）
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('pages', 'pages', false, 8388608, array['text/html'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

-- 読むのは本人（自分の account のフォルダ）と店長だけ。書くのは secret key だけ（ポリシーなし = RLS で拒否）
drop policy if exists "pages: owner or admin reads" on storage.objects;
create policy "pages: owner or admin reads" on storage.objects for select to authenticated
using (
  bucket_id = 'pages'
  and (
    (storage.foldername(name))[1] = 'u_' || left(md5(lower(btrim(coalesce(auth.jwt() ->> 'email', '')))), 16)
    or public.is_admin()
  )
);

-- ログインした本人の置き場の名前（網页が pages/<これ>/index.html を読む）。ログインしていなければ null
create or replace function public.my_page_path()
returns text language sql stable security invoker set search_path = '' as $$
  select case when (select auth.uid()) is null then null
              else 'u_' || left(md5(lower(btrim(coalesce((select auth.jwt()) ->> 'email', '')))), 16) end $$;
revoke all on function public.my_page_path() from public;
grant execute on function public.my_page_path() to authenticated;
