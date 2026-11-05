"""古い db/*.sql を流し直して守りが戻らないように（2026-11-05 全体点検 本 3 ②③）。

①後のファイルが上書きした古いファイルは 1 行目に「流し直し禁止」②pw_setup を true に戻す行は生きていない
③search_path を固定した 3 関数は、最後の create のあとに alter … set search_path がある。"""
import pathlib
import re
import unittest

DB = pathlib.Path(__file__).resolve().parent.parent / "db"
OLD = ["accounts", "settings", "nav_schemes", "item_requests", "photo_inbox", "edit_control", "auth"]
PINNED = {"private.acct": "private, public, pg_temp", "private.user_name_ok": "private, public, pg_temp",
          "public.hook_invite_only": "public, pg_temp"}


def live(t):
    return "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("--"))


class DbRerun(unittest.TestCase):
    def test_old_files_say_do_not_rerun(self):
        bad = [f for f in OLD if not (DB / f"{f}.sql").read_text(encoding="utf-8").startswith("-- ⚠ 流し直し禁止")]
        self.assertEqual(bad, [])

    def test_no_live_line_opens_pw_setup(self):
        bad = [p.name for p in DB.glob("*.sql")
               if re.search(r"'pw_setup'\s*,\s*true|on_\s*=\s*true\s+where\s+key\s*=\s*'pw_setup'", live(p.read_text(encoding="utf-8")), re.I)]
        self.assertEqual(bad, [])

    def test_search_path_pinned_after_last_create(self):
        for fn, path in PINNED.items():
            hits = []
            for p in sorted(DB.glob("*.sql")):
                t = live(p.read_text(encoding="utf-8"))
                for m in re.finditer(rf"create or replace function {re.escape(fn)}\(|alter function {re.escape(fn)}\([^)]*\) set search_path = ([^;]+);", t):
                    hits.append(m.group(1))
            self.assertTrue(hits and hits[-1] == path, f"{fn}: {hits}")


if __name__ == "__main__":
    unittest.main()
