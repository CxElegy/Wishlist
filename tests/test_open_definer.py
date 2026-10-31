"""anon が実行できる SECURITY DEFINER の書き換え関数（insert/update/delete）のうち、
auth.uid()・can_edit・is_admin の守りがないものを db/*.sql から全部数える（引数名では絞らない）。
今ある穴は KNOWN_OPEN に理由つきで固定。新しく増えたら落ちる。減らしたら KNOWN_OPEN から外す。
署名ごとに数える：どれかの定義に守りがあれば守り済み、anon から revoke された署名は数えない。"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARD = re.compile(r"is_admin\(\)|can_edit\(|auth\.uid\(\)|auth\.jwt\(\)|shop_pw_setup_open\(")
# 本番で確かめた穴（2026-10-31）。直すには DB の変更が要る＝BACKLOG の [?]
KNOWN_OPEN = {
    # 名前を取って書き換えるのに本人確認がない（BACKLOG [?]）
    "user_agree", "user_leave", "user_set_prefs", "user_login", "remember_user",
    # 秘密鍵を持たない定時タスク（AI 編集・小元素）が anon で呼ぶ設計。proc・版面・文字数は関数の中で絞っている
    "live_report",
}


def _types(args):
    out = []
    for a in re.split(r",", re.sub(r"\([^)]*\)", "", args)):
        a = re.sub(r"\s+default\s+.*$", "", a.strip(), flags=re.I)
        if a:
            out.append(a.split()[-1].lower() if len(a.split()) > 1 else a.lower())
    return tuple(out)


def open_definers():
    sig = {}      # (fn, types) -> [guarded, writes, definer]
    granted, revoked = set(), set()
    for f in sorted((ROOT / "db").glob("*.sql")):
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r"create\s+(?:or\s+replace\s+)?function\s+public\.(\w+)\s*\(([^)]*)\)(.*?)\$\$\s*;", t, re.S | re.I):
            fn, args, body = m.groups()
            s = sig.setdefault((fn, _types(args)), [False, False, False])
            s[0] |= bool(GUARD.search(body))
            s[1] |= bool(re.search(r"\b(update|insert|delete)\b", body, re.I))
            s[2] |= "security definer" in body.lower()
        for m in re.finditer(r"\b(grant|revoke)\s+(?:execute|all)(?:\s+privileges)?\s+on\s+function\s+(.*?)\s+(to|from)\s+([^;]*);", t, re.S | re.I):
            verb, funcs, _, who = m.groups()
            if not re.search(r"\banon\b", who, re.I):
                continue
            for fm in re.finditer(r"public\.(\w+)\s*\(([^)]*)\)", funcs):
                (granted if verb.lower() == "grant" else revoked).add((fm.group(1), _types(fm.group(2))))
    return {fn for (fn, ty), (g, w, d) in sig.items()
            if d and w and not g and (fn, ty) in granted and (fn, ty) not in revoked}


class OpenDefiner(unittest.TestCase):
    def test_no_new_unguarded_write_functions(self):
        got = open_definers()
        self.assertEqual(got - KNOWN_OPEN, set(), "新しく守りのない書き換え関数が anon に開いている")
        self.assertEqual(KNOWN_OPEN - got, set(), "直ったなら KNOWN_OPEN から外す")


if __name__ == "__main__":
    unittest.main()
