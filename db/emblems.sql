-- ライブラリの版面の小元素の置き場（2026-10-24，用户定的：Supabase Storage の公開の箱。ファイル名は番号だけ・版面の名前を出さない・同じ版面は全員で 1 枚）
-- scripts/library_emblem.py（Actions の secret key）が emblems/<Wikidata の番号か b+版面の id>-<中身の指紋>.webp を書き、
-- 網页は https://<project>.supabase.co/storage/v1/object/public/emblems/<file> を直接読む（公開の箱は読むのに policy が要らない）。
-- 書くのは secret key だけ（storage.objects に insert の policy を作らない = RLS で拒否）。
-- 戻し方（足しただけ）：Storage の画面で emblems の箱を空にしてから delete from storage.buckets where id = 'emblems';
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('emblems', 'emblems', true, 2097152, array['image/webp'])
on conflict (id) do nothing;
