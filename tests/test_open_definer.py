"""anon/authenticated が実行できる SECURITY DEFINER 関数のうち、名前・メールを引数に取るのに
auth.uid()・can_edit・is_admin の守りがないものを db/*.sql から数える（BACKLOG「呼び出した人の名前に限る」）。
今ある穴は KNOWN_OPEN に固定。新しく増えたら落ちる。減らしたら KNOWN_OPEN から外す。"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARD = re.compile(r"is_admin\(\)|can_edit\(|auth\.uid\(\)|auth\.jwt\(\)|shop_pw_setup_open\(")
# user_register・user_signup は登録そのもの（開いていて当然）。submit_item は本番では can_edit で守り済み（古い定義が db/ に残る分）
KNOWN_OPEN = {"user_agree", "user_leave", "user_set_prefs", "user_login", "remember_user", "user_register", "user_signup", "submit_item"}


def open_definers():
    out = set()
    for f in sorted((ROOT / "db").glob("*.sql")):
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r"create\s+(?:or\s+replace\s+)?function\s+public\.(\w+)\s*\(([^)]*)\)(.*?)\$\$\s*;", t, re.S | re.I):
            fn, args, body = m.groups()
            if not re.search(r"\bp_(name|email)\b", args) or "security definer" not in body.lower() or fn.startswith("admin_"):
                continue
            if not re.search(rf"grant\s+execute\s+on\s+function\s+public\.{fn}\([^)]*\)\s+to\s+[^;]*\banon\b", t, re.I):
                continue
            if not GUARD.search(body) and re.search(r"\b(update|insert|delete)\b", body, re.I):   # 書き換えるものだけ
                out.add(fn)
    return out


class OpenDefiner(unittest.TestCase):
    def test_no_new_unguarded_name_functions(self):
        got = open_definers()
        self.assertEqual(got - KNOWN_OPEN, set(), "新しく守りのない関数（名前・メールを取る）が anon に開いている")
        self.assertEqual(KNOWN_OPEN - got, set(), "直ったなら KNOWN_OPEN から外す")


if __name__ == "__main__":
    unittest.main()
