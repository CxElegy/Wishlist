"""古い db/*.sql を流し直して守りが戻らないように（2026-11-05 全体点検 本 3 ②③）。

①後のファイルが上書きした古いファイルは 1 行目に「流し直し禁止」②pw_setup を true に戻す行は生きていない
③search_path を固定した 3 関数は、最後の create のあとに alter … set search_path がある。"""
import pathlib
import re
import unittest

DB = pathlib.Path(__file__).resolve().parent.parent / "db"
MARK = "-- ⚠ 流し直し禁止"
DRAFT = "-- 【未適用"   # 承認待ちの案（流していない）は数えない
PINNED = {"private.acct": "private, public, pg_temp", "private.user_name_ok": "private, public, pg_temp",
          "public.hook_invite_only": "public, pg_temp"}


def live(t):
    return "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("--"))


def defs():
    """{関数の名前(引数の型): 定義しているファイル名の集まり}。同じ名前でも引数が違えば別の関数。"""
    out = {}
    for p in sorted(DB.glob("*.sql")):
        if p.read_text(encoding="utf-8").startswith(DRAFT):
            continue
        for m in re.finditer(r"create\s+(?:or\s+replace\s+)?function\s+([\w.]+)\s*\(([^)]*)\)", live(p.read_text(encoding="utf-8")), re.I):
            n = m.group(1).lower()
            n = n if "." in n else "public." + n
            ty = [a.split()[-1].lower() for a in re.sub(r"\s+default\s+[^,]*", "", m.group(2), flags=re.I).split(",") if a.strip()]
            out.setdefault(f"{n}({','.join(ty)})", set()).add(p.name)
    return out


class DbRerun(unittest.TestCase):
    def test_old_files_say_do_not_rerun(self):
        """同じ関数を 2 つ以上のファイルが作るなら、今の形のファイルは 1 つだけで、ほかは全部
        頭書き「流し直し禁止」でそのファイルの名前を挙げる（一覧を手で持たず、重なりを自分で探す）。"""
        bad = []
        for fn, files in defs().items():
            if len(files) < 2:
                continue
            head = {f: (DB / f).read_text(encoding="utf-8").split("\n", 2)[:2] for f in files}
            cur = [c for c in files if all(head[o][0].startswith(MARK) and c in "".join(head[o]) for o in files - {c})]
            if len(cur) != 1:
                bad.append(f"{fn}: {sorted(files)}")
        self.assertEqual(bad, [])

    def test_counts_known_stale_files(self):
        """本番の DB と中身を比べて古いと分かったファイル（2026-11-05）を、上の数え方が拾えること。"""
        d = defs()
        self.assertEqual(d["public.run_now(text)"], {"auth_guard.sql", "run_now.sql"})
        self.assertEqual(d["public.my_votes()"], {"accounts.sql", "my_votes.sql"})
        self.assertEqual(d["public.live_status()"], {"accounts.sql", "live_status.sql"})

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
