-- 写真の一時保管の置き場（2026-10-31，用户定的：記事の写真をサーバーに先に置いて読み込みを速くする。溜めない）
-- scripts/photo_store.py（Actions の secret key）が photos/<網址の指紋>-400.webp ・ -800.webp を書き、
-- 網页は https://<project>.supabase.co/storage/v1/object/public/photos/<file> を直接読む（公開の箱は読むのに policy が要らない）。
-- 書く・消すのは secret key だけ。保つのは「いまのページに載っている＋最後に使ってから 14 日」・全体 300MB まで（超えたら古い順に消す）。
-- 戻し方（足しただけ）：Storage の画面で photos の箱を空にしてから delete from storage.buckets where id = 'photos';
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('photos', 'photos', true, 2097152, array['image/webp'])
on conflict (id) do nothing;
