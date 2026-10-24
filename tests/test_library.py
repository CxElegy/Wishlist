"""ライブラリ（db/library.sql・scripts/library.py）：同じものかどうかの印・共有の設定と人ごとの置き方の分け方。ネットには出ない。"""
import pathlib
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import library  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Key(unittest.TestCase):
    def test_same_name_in_other_writing_is_one_board(self):
        self.assertEqual(library.board_key({"name": "ＧＴＡ ６"}), library.board_key({"name": "gta6"}))
        self.assertEqual(library.board_key({"name": "あつ森"}), "n:あつ森")
        self.assertEqual(library.board_key({"name": "x", "wikidata": "Q123"}), "wd:Q123")

    def test_shop_items_split(self):
        items = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]
        boards, parents, follows = library.shop_rows(items)
        self.assertEqual(len({b["key"] for b in boards}), len(items))   # 店長の版面は 1 つずつ別の版面
        for b in boards:
            for k in library.PERSONAL:
                self.assertNotIn(k, b["config"])   # 置き方は人ごと（follows）
        self.assertEqual([f["pos"] for f in follows], list(range(len(items))))
        self.assertTrue(all(f["account"] == "test1" for f in follows))



class Wikidata(unittest.TestCase):
    """番号の決め方（ネットには出ない：get を差し替える）。"""
    def ent(self, labels):
        return {"labels": {k: {"value": v} for k, v in labels.items()}, "aliases": {}}

    def test_wiki_titles_pick_best_match(self):
        # 漫威电影：記事名の 1 つ目（映画 1 本）ではなく、名前・検索語が入るシリーズ全体を選ぶ
        def get(p):
            return {"entities": {"Q1": self.ent({"en": "Avengers: Doomsday"})}} if "Doomsday" in p.get("titles", "") \
                else {"entities": {"Q2": self.ent({"zh": "漫威电影宇宙", "en": "Marvel Cinematic Universe"})}}
        item = {"name": "漫威电影", "keywords": ["漫威 电影"], "wiki": ["en:Avengers: Doomsday", "en:Marvel Cinematic Universe"]}
        self.assertEqual(library.find_wikidata(item, get), "Q2")

    def test_topic_without_wiki_has_no_number(self):
        self.assertIsNone(library.find_wikidata({"name": "猫用品", "type": "category"}, lambda p: self.fail("引かない")))

    def test_find_wikidata_brand_category(self):
        def get(p):
            return {"search": [{"id": "Q37158", "label": "Starbucks", "aliases": ["スターバックス"]},
                               {"id": "Q5", "label": "gelato pique"}]}
        brand = {"type": "category", "subs": {"owner": "ブランド"}}
        self.assertEqual(library.find_wikidata({**brand, "name": "gelato pique", "keywords": ["ジェラピケ"]}, get), "Q5")
        # ブランドの品目（マグ）は検索語の「スターバックス」で本体に当たらない
        self.assertIsNone(library.find_wikidata({**brand, "name": "星巴克马克杯", "keywords": ["スターバックス"]}, get))
        # 項目がない（gelato pique は 2026-10-23 に ja/en/zh・全文検索とも 0 件）→ 名前のまま
        self.assertIsNone(library.find_wikidata({**brand, "name": "gelato pique"}, lambda p: {"search": []}))

    def test_search_needs_exact_name(self):
        def get(p):
            return {"search": [{"id": "Q9", "label": "あつまれ どうぶつの森", "aliases": ["あつ森"]}, {"id": "Q8", "label": "どうぶつの森"}]}
        self.assertEqual(library.find_wikidata({"name": "あつ森", "type": "game"}, get), "Q9")
        self.assertIsNone(library.find_wikidata({"name": "まったく別", "type": "game"}, get))

    def test_shop_items_with_number_use_it(self):
        items = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]
        keys = {i["name"]: library.board_key(i) for i in items}
        self.assertEqual(keys["あつ森"], "wd:Q64566657")
        self.assertEqual(keys["漫威电影"], "wd:Q642878")
        self.assertTrue(keys["猫用品"].startswith("n:"))


if __name__ == "__main__":
    unittest.main()


class Refresh(unittest.TestCase):
    """週 1 回の引き直し（library.refresh・write_wikidata）：断られたのと 0 件を分ける、items.yaml はコメントを残して書く。"""
    ITEMS = [{"name": "A", "wikidata": "Q1"}, {"name": "猫用品", "type": "category"},
             {"name": "gelato pique", "type": "category", "subs": {"owner": "ブランド"}}, {"name": "あつ森", "type": "game"}]

    def test_found_none_skip(self):
        def get(p):
            if p.get("search") == "あつ森":
                return {"search": [{"id": "Q9", "label": "あつ森"}]}
            return {"search": []}
        r = library.refresh(self.ITEMS, get, pause=0)
        self.assertEqual(r["found"], {"あつ森": "Q9"})
        self.assertEqual(r["none"], ["gelato pique"])   # 聞いて 0 件
        self.assertEqual(r["skip"], ["猫用品"])          # 題材は聞かない
        self.assertEqual(r["blocked"], [])

    def test_blocked_is_not_zero_and_stops(self):
        def get(p):
            raise library.WdBlocked("429")
        r = library.refresh(self.ITEMS, get, pause=0)
        self.assertEqual(r["blocked"], ["gelato pique", "あつ森"])   # 1 度断られたら残りは聞かない
        self.assertEqual(r["none"], [])
        self.assertEqual(r["found"], {})

    def test_wd_get_raises_when_refused(self):
        import urllib.error
        from unittest import mock

        def refuse(*a, **k):
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        with mock.patch("urllib.request.urlopen", refuse), mock.patch("time.sleep"):
            with self.assertRaises(library.WdBlocked):
                library._wd_get({"action": "wbsearchentities", "search": "x"})

    def test_write_keeps_comments(self):
        text = ('items:\n  - name: A\n    wikidata: Q1\n    motif: x\n\n  - name: gelato pique\n    # wikidata: なし（引いた）\n    motif: cloud\n\n'
                '  - name: "あつ森"\n    subs: {kind: ゲーム}   # 小分類\n')
        new, done = library.write_wikidata(text, {"gelato pique": "Q5", "あつ森": "Q9", "A": "Q2"})
        self.assertEqual(done, ["gelato pique", "あつ森"])   # 番号がある A は上書きしない
        data = yaml.safe_load(new)["items"]
        self.assertEqual([i.get("wikidata") for i in data], ["Q1", "Q5", "Q9"])
        self.assertNotIn("# wikidata: なし", new)
        self.assertIn("# 小分類", new)

    def test_write_shop_items_roundtrip(self):
        text = (ROOT / "items.yaml").read_text(encoding="utf-8")
        items = yaml.safe_load(text)["items"]
        missing = [i["name"] for i in items if not i.get("wikidata")]
        new, done = library.write_wikidata(text, {n: "Q42" for n in missing})
        self.assertEqual(sorted(done), sorted(missing))
        after = yaml.safe_load(new)["items"]
        self.assertEqual(len(after), len(items))
        self.assertTrue(all(i.get("wikidata") for i in after))
        self.assertEqual([{k: v for k, v in i.items() if k != "wikidata"} for i in after],
                         [{k: v for k, v in i.items() if k != "wikidata"} for i in items])   # ほかは 1 文字も変えない

    def test_refresh_main_writes_log(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "items.yaml"
            p.write_text('items:\n  - name: "あつ森"\n    type: game\n', encoding="utf-8")
            with mock.patch("runlog.LOG_DIR", pathlib.Path(d) / "log"):
                r, done = library.refresh_main(p, lambda q: {"search": [{"id": "Q9", "label": "あつ森"}]})
                rows = __import__("runlog").load("library")
            self.assertEqual(done, ["あつ森"])
            self.assertIn("wikidata: Q9", p.read_text(encoding="utf-8"))
            self.assertEqual((rows[-1]["found"], rows[-1]["blocked"]), (1, 0))


class Users(unittest.TestCase):
    """お客さまの選んだもの（prefs.picks）→ ライブラリの版面と follows（2026-10-24）。"""
    USERS = [{"email": "Test-A@example.com", "prefs": {"picks": [
                {"name": "あつ森", "sec": "游戏"}, {"name": "YOASOBI", "sec": "演出"}, {"name": "広島旅行", "sec": "生活"},
                {"name": " YOASOBI ", "sec": "演出"}]}},
             {"email": "test-b@example.com", "prefs": {"picks": [{"name": "広島旅行", "sec": "生活"}]}},
             {"email": "test-c@example.com", "prefs": {}}]
    BOARDS = [{"key": "wd:Q1", "name": "あつ森", "names": {"ja": "あつ森"}}]

    @staticmethod
    def wd(params):
        if params.get("action") == "wbgetentities":
            return {"entities": {}}
        if params["search"].strip() == "YOASOBI":
            return {"search": [{"id": "Q5", "label": "YOASOBI 一覧", "description": "Wikimedia list"},
                               {"id": "Q7", "label": "YOASOBI", "description": "Japanese duo"}]}
        return {"search": [{"id": "Q8", "label": "広島", "description": "city"}]}   # 名前が違う項目には当てない

    def test_plan(self):
        r = library.plan_users(self.USERS, self.BOARDS, self.wd, pause=0)
        a = __import__("userfeed").account_of("test-a@example.com")
        self.assertEqual(sorted(r["new"]), ["n:広島旅行", "wd:Q7"])         # あつ森はもとからある版面・広島旅行は 1 つだけ
        self.assertNotIn(a, str(r["new"]))                                   # boards にだれが足したかを書かない
        self.assertEqual(r["new"]["wd:Q7"]["created_by"], "user")
        fa = [f["key"] for f in r["follows"] if f["account"] == a]
        self.assertEqual(fa, ["wd:Q1", "wd:Q7", "n:広島旅行"])              # 同じ名前は 1 回
        self.assertEqual(len([f for f in r["follows"] if f["key"] == "n:広島旅行"]), 2)
        self.assertEqual(r["counts"]["users"], 2)
        f = next(f for f in r["follows"] if f["key"] == "n:広島旅行")
        self.assertEqual(f["section"], "生活")
        self.assertTrue(f["subs"])                                           # 小分類は必ず

    def test_blocked_waits_next_time(self):
        def no(params):
            raise library.WdBlocked("429")
        r = library.plan_users(self.USERS, self.BOARDS, no, pause=0)
        self.assertEqual(r["new"], {})
        self.assertEqual([f["key"] for f in r["follows"]], ["wd:Q1"])        # もとからある版面だけ
        self.assertEqual(r["counts"]["blocked"], 3)

    def test_limit(self):
        many = [{"email": "x@example.com", "prefs": {"picks": [{"name": f"題材{i}", "sec": "其他"} for i in range(105)]}}]
        r = library.plan_users(many, [], lambda p: {"search": []}, pause=0)
        self.assertEqual((len(r["follows"]), r["counts"]["over"]), (library.MAX_FOLLOWS, 5))


class PickLabelFirst(unittest.TestCase):
    def test_label_before_alias(self):
        hits = {"search": [{"id": "Q190012", "label": "adenosine", "aliases": ["ADO"], "match": {"type": "alias", "text": "ADO"}},
                           {"id": "Q77", "label": "Ado", "match": {"type": "label", "text": "Ado"}}]}
        self.assertEqual(library.find_pick_wikidata("Ado", lambda p: hits), "Q77")

    def test_short_ascii_alias_only_is_not_used(self):
        hits = {"search": [{"id": "Q190012", "label": "adenosine", "aliases": ["ADO"], "match": {"type": "alias", "text": "ADO"}}]}
        self.assertIsNone(library.find_pick_wikidata("Ado", lambda p: hits))

    def test_long_alias_still_ok(self):
        hits = {"search": [{"id": "Q1968", "label": "Formula One", "aliases": ["Formula 1"], "match": {"type": "alias", "text": "Formula 1"}}]}
        self.assertEqual(library.find_pick_wikidata("Formula 1", lambda p: hits), "Q1968")


def ent(desc, claims=None, labels=None):
    """wbgetentities の返事の作り物：1 回目 = 項目の説明と関係、2 回目 = 関係する項目の名前。"""
    def get(params):
        if params.get("props") == "labels":
            return {"entities": {q: {"labels": {"en": {"value": v}}} for q, v in (labels or {}).items()}}
        cl = {pid: [{"mainsnak": {"datavalue": {"value": {"id": q} if q.startswith("Q") else {"time": q}}}} for q in qs]
              for pid, qs in (claims or {}).items()}
        return {"entities": {params["ids"]: {"descriptions": {"en": {"value": desc}}, "claims": cl}}}
    return get


class SubsFromWikidata(unittest.TestCase):
    """小分類は名前だけでなく Wikidata の説明・関係から（2026-10-24 別の目の指摘：1 つ目の値に落ちていた）。"""
    def subs(self, sec, name, desc, claims=None, labels=None):
        f = library.wd_facts("Q1", ent(desc, claims, labels), today=__import__("datetime").date(2026, 10, 24))
        return library.subs_for(sec, name, f)

    def test_name_only_falls_to_first(self):
        self.assertEqual(library.subs_for("运动", "大谷翔平")["sport"], "サッカー")   # 前のやり方（名前だけ）

    def test_sports(self):
        self.assertEqual(self.subs("运动", "大谷翔平", "Japanese baseball player", {"P641": ["Q5369"]}, {"Q5369": "baseball"})["sport"], "野球")
        self.assertEqual(self.subs("运动", "NBA", "North American professional basketball league")["sport"], "バスケ")
        self.assertEqual(self.subs("运动", "F1", "auto racing championship", {"P641": ["Q1968"]}, {"Q1968": "Formula One"})["sport"], "モータースポーツ")
        self.assertEqual(self.subs("运动", "大相撲", "professional sumo wrestling")["sport"], "格闘技")

    def test_music_groups(self):
        s = self.subs("演出", "BTS", "South Korean boy band", {"P495": ["Q884"]}, {"Q884": "South Korea"})
        self.assertEqual((s["form"], s["scene"]), ("グループ", "K-POP"))
        self.assertEqual(self.subs("演出", "YOASOBI", "Japanese musical duo")["form"], "グループ")
        self.assertEqual(self.subs("演出", "Ado", "Japanese singer")["form"], "ソロ")

    def test_works(self):
        self.assertEqual(self.subs("影视", "鬼滅の刃", "Japanese manga series by Koyoharu Gotouge")["kind"], "マンガ")

    def test_games(self):
        s = self.subs("游戏", "スプラトゥーン3", "2022 video game", {"P400": ["Q19610114"], "P577": ["+2022-09-09T00:00:00Z"]},
                      {"Q19610114": "Nintendo Switch"})
        self.assertEqual((s["status"], s["platform"]), ("発売済み", "家庭用ゲーム機"))
        s = self.subs("游戏", "原神", "free-to-play action role-playing game", {"P400": ["Q91", "Q92", "Q93"], "P577": ["+2020-09-28T00:00:00Z"]},
                      {"Q91": "Android", "Q92": "PlayStation 5", "Q93": "Microsoft Windows"})
        self.assertEqual((s["status"], s["platform"]), ("運営中", "マルチ"))
        s = self.subs("游戏", "ポケットモンスター", "Japanese media franchise", {"P31": ["Q196600"]}, {"Q196600": "media franchise"})
        self.assertEqual((s["status"], s["platform"]), ("発売済み", "マルチ"))   # 日付も機種もないシリーズ全体（本番の Q864）
        s = self.subs("游戏", "新作", "upcoming video game", {"P577": ["+2027-03-01T00:00:00Z"]})
        self.assertEqual(s["status"], "新作・発売前")

    def test_life_and_outing(self):
        self.assertEqual(self.subs("生活", "キャンプ", "outdoor recreational activity")["kind"], "アウトドア・旅行")
        self.assertEqual(library.subs_for("生活", "広島旅行")["kind"], "アウトドア・旅行")
        self.assertEqual(library.subs_for("生活", "筋トレ")["kind"], "健康")
        self.assertEqual(self.subs("生活", "観葉植物", "plant grown indoors")["kind"], "インテリア")
        self.assertEqual(self.subs("生活", "コーヒー", "brewed drink")["kind"], "グルメ")   # 名前の英語名はなくても説明から
        self.assertEqual(self.subs("出行", "京都", "city in Japan")["kind"], "観光地")

    def test_shopping(self):
        self.assertEqual(self.subs("好物", "ユニクロ", "Japanese casual wear designer, manufacturer and retailer")["kind"], "ファッション・コスメ")
        self.assertEqual(self.subs("好物", "Nintendo Switch 2", "hybrid video game console")["kind"], "ガジェット・家電")
        self.assertEqual(self.subs("好物", "無印良品", "Japanese retail company")["kind"], "雑貨・食器")
        self.assertEqual(self.subs("好物", "ガンプラ", "Gundam plastic model kits")["kind"], "おもちゃ・フィギュア")

    def test_cache(self):
        calls = []
        def get(p):
            calls.append(p)
            return ent("Japanese baseball player")(p)
        cache = {}
        library.facts_for("Q9", get, cache)
        library.facts_for("Q9", get, cache)
        self.assertEqual(len(calls), 1)                                      # 30 日は聞き直さない


class Resubs(unittest.TestCase):
    """前に名前だけで決めた小分類を直す。本人が変えたらしい行は触らない。"""
    def test_fix_only_default_rows(self):
        by_id = {1: {"key": "wd:Q1", "name": "大谷翔平"}, 2: {"key": "n:広島旅行", "name": "広島旅行"}, 3: {"key": "wd:Q3", "name": "NBA"}}
        follows = [{"account": "u_a", "board_id": 1, "section": "运动", "subs": {"sport": "サッカー", "how": "観る"}},
                   {"account": "u_b", "board_id": 2, "section": "生活", "subs": {"kind": "ペット", "how": "買う"}},
                   {"account": "u_a", "board_id": 3, "section": "运动", "subs": {"sport": "テニス", "how": "観る"}}]   # 本人が選んだらしい値
        wrote = []
        n = library.resubs(follows, by_id, ent("Japanese baseball player"), {}, lambda path, body, *a, **k: wrote.append((path, body)))
        self.assertEqual(n, 2)
        self.assertEqual(wrote[0], ("follows?account=eq.u_a&board_id=eq.1", {"subs": {"sport": "野球", "how": "観る"}}))
        self.assertEqual(wrote[1][1]["subs"], {"kind": "アウトドア・旅行", "how": "作る・する"})

    def test_plan_skips_existing_follow(self):
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "大谷翔平", "sec": "运动"}]}}]
        boards = [{"key": "wd:Q1", "name": "大谷翔平"}]
        a = __import__("userfeed").account_of("a@example.com")
        def no(p):
            raise AssertionError("聞かない")
        r = library.plan_users(users, boards, no, pause=0, have={(a, "wd:Q1")})
        self.assertEqual(r["follows"], [])
