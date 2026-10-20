-- 打开登录的开关（切换那天运行一次；先要运行过 db/auth.sql・db/auth_guard.sql，Google 登录也要先设好）。
-- 打开以后：没登录 = 只能看；管理者 = 都能改；一般用户 = 只能改自己的 account。
-- 出问题时把 true 改成 false 再运行一次，就回到以前（谁都能改）。
update private.auth_flags set on_ = true where key = 'enforce';

-- 旧的不带 p_account 的写函数只给冻结的 test1 用（网页本来就拦着），开关打开后连数据库也关上
revoke execute on function public.set_size(text, text, text) from anon, authenticated;
revoke execute on function public.set_nav_scheme(text, text) from anon, authenticated;
revoke execute on function public.submit_item(text, text, jsonb) from anon, authenticated;
revoke execute on function public.add_photo(text, text, text, text, text) from anon, authenticated;
revoke execute on function public.edit_control_set(text, text, text) from anon, authenticated;
