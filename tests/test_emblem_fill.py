"""小元素の自動補完（scripts/emblem_fill.py）・本人確認（face_id.py）・プロセス一覧（processes.py）。ネットワークには出ない。

    python -m unittest discover tests
"""

import datetime as dt
import zoneinfo
import json
import os
import pathlib
import sys
import unittest
import tempfile
import urllib.parse
from unittest import mock

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import emblem_fill as ef  # noqa: E402
import face_id  # noqa: E402
import processes  # noqa: E402
import render  # noqa: E402
import sitedir  # noqa: E402
import runlog  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Rules(unittest.TestCase):
    def test_work_names_strip_accents(self):
        """Pokémon の é で英数字の呼び名が空になり、own_wiki が外れてポケモンの分類が見つからなかった。"""
        item = {"name": "ポケットモンスター", "wiki": ["en:Pokémon", "ja:ポケットモンスター"], "keywords": ["ポケットモンスター"]}
        self.assertEqual(ef.work_names(item), ["Pokemon"])
        self.assertTrue(ef.own_wiki("https://pokemon.fandom.com/api.php", "Pokémon Wiki", item))

    def test_kind_inferred_from_type(self):
        self.assertEqual(ef.kind_of({"type": "anime"}), "character")
        self.assertEqual(ef.kind_of({"type": "event"}), "person")
        self.assertEqual(ef.kind_of({"type": "product"}), "brand")
        self.assertEqual(ef.kind_of({"type": "category"}), "topic")
        self.assertEqual(ef.kind_of({"type": "category", "emblem_kind": "brand"}), "brand")
        self.assertEqual(ef.kind_of({"type": "game", "emblem_kind": "???"}), "character")   # 知らない種類は type で推定

    def test_targets(self):
        self.assertEqual(ef.rule({"type": "event", "emblem_kind": "person"})[1:], (3, 6, 10))
        self.assertEqual(ef.rule({"type": "category", "emblem_kind": "brand"})[1:], (1, 1, 1))
        self.assertEqual(ef.rule({"type": "category"})[1:], (2, 3, 5))
        # グループはメンバー全員（天井 50）
        nine = {"type": "event", "emblem_kind": "group", "emblem_who": [f"m{i}" for i in range(9)]}
        self.assertEqual(ef.rule(nine)[2:], (9, 9))
        many = {**nine, "emblem_who": [f"m{i}" for i in range(24)]}
        self.assertEqual(ef.rule(many)[2:], (24, 24))
        # 名前を挙げたキャラはその全員が目標（2 人の作品は 2 枚で足りる、上限も 2）
        two = {"type": "game", "emblem_who": ["a", "b"]}
        self.assertEqual(ef.rule(two)[1:], (2, 2, 2))

    def test_cap_follows_main_elements(self):
        # 上限は内容の主要な要素の数：キャラ 60 人のゲームは 60 枚（用户定的）、目標は名前を挙げた人数まで
        game = {"type": "game", "emblem_pool": 60, "emblem_who": [f"c{i}" for i in range(14)]}
        self.assertEqual(ef.rule(game)[2:], (14, 60))
        self.assertEqual(ef.rule({**game, "emblem_who": [f"c{i}" for i in range(60)]})[2:], (60, 60))

    def test_subjects_step_by_step(self):
        # 主要な要素が多いときは、まだいない人から STEP 人ずつ（いる人は集め直さない）
        who = [f"c{i}" for i in range(60)]
        item = {"type": "game", "emblem_pool": 60, "emblem_who": who, "emblem": [{"subject": f"c{i}"} for i in range(20)]}
        got = ef.subjects(item, "character", 60)
        self.assertEqual(len(got), ef.STEP)
        self.assertTrue(all(int(x[1:]) >= 20 for x in got))
        # 主役が 4 人の作品は 4 枚、要素の数がわからない作品は既定（6、最大 10）
        self.assertEqual(ef.rule({"type": "anime", "emblem_pool": 4})[2:], (4, 4))
        self.assertEqual(ef.rule({"type": "anime"})[1:], (3, 6, 10))
        # 主題は代表作の数、本人は別の写真（要素を数えない）、emblem_max は手で決めた上限（ぐでたま 3）
        self.assertEqual(ef.rule({"type": "category", "emblem_examples": ["a", "b", "c", "d", "e"]})[2:], (5, 5))
        self.assertEqual(ef.rule({"type": "event", "emblem_kind": "person", "emblem_pool": 40})[1:], (3, 6, 10))
        self.assertEqual(ef.rule({"type": "anime", "emblem_max": 3})[1:], (3, 3, 3))

    def test_subjects_rotation_reaches_everyone(self):
        # 回ごとのずらしで名簿の全員に届く（STEP ずつずらすと 65 人のうち 30 人に一度も届かなかった）・実写の「役（出演者）」はもういる人
        from unittest import mock
        who = [f"a{i}" for i in range(65)]
        item = {"type": "drama", "emblem_who": who, "emblem": [{"subject": "Harry Potter（a0）"}, {"subject": "作品（作品）"}]}
        seen = set()
        for h in range(100):
            with mock.patch.object(ef.time, "time", return_value=h * 3600):
                seen |= set(ef.subjects(item, "character", 65))
        self.assertEqual(seen, set(who[1:]))
        self.assertEqual(ef._who_of("Harry Potter（Dominic McLaughlin） 2"), {"Harry Potter（Dominic McLaughlin）", "Dominic McLaughlin"})

    def test_broken_cuts_forehead(self):
        # 額まで切れた前からの切り抜きも外す（取るときの check_whole と同じ規則、emblem.forehead_cut）
        import tempfile
        from unittest import mock
        from PIL import Image
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "emblems").mkdir()
        Image.new("RGBA", (200, 200)).save(tmp / "emblems" / "a.webp")
        Image.new("RGBA", (200, 200)).save(tmp / "emblems" / "b.webp")
        item = {"emblem": [{"subject": "A", "image": "emblems/a.webp"}, {"subject": "B", "image": "emblems/b.webp"}]}
        with mock.patch.object(ef.emblem.sitedir, "SITE_DIR", tmp), mock.patch.object(ef.emblem, "top_share", return_value=0.05), \
                mock.patch.object(ef.emblem, "forehead_cut", side_effect=lambda im: im.filename.endswith("a.webp")):
            self.assertEqual([x["subject"] for x in ef.broken_cuts(item)], ["A"])
        # 上の端に TOP_TOUCH 未満しか当たっていない（頭が全部入っている：The Mandalorian Gideon 1.0%）は額を見ない（check_whole と同じ）
        with mock.patch.object(ef.emblem.sitedir, "SITE_DIR", tmp), mock.patch.object(ef.emblem, "top_share", return_value=0.01), \
                mock.patch.object(ef.emblem, "forehead_cut", return_value=True):
            self.assertEqual(ef.broken_cuts(item), [])

    def test_broken_image_top_max(self):
        # 上の端の半分以上が人物（コマの切り抜き：BLEACH Muramasa）は前からの切り抜きも外す。check_whole の TOP_MAX と同じ
        from unittest import mock
        from PIL import Image
        im = Image.new("RGBA", (200, 200))
        with mock.patch.object(ef.emblem, "head_cut", return_value=False), mock.patch.object(ef.emblem, "flat_flaw", return_value=False):
            with mock.patch.object(ef.emblem, "top_share", return_value=0.6):
                self.assertTrue(ef.broken_image(im, False))
            with mock.patch.object(ef.emblem, "top_share", return_value=0.4), mock.patch.object(ef.emblem, "forehead_cut", return_value=False):
                self.assertFalse(ef.broken_image(im, False))

    def test_bad_source_and_same_pics(self):
        # 別の作品・持ち物の絵（あつ森の SSBB_Trophy・原神の Item_）は元のファイル名で外す。同じ image・同じ見た目は 1 枚（Vaundy 3 本・Stella Fortuna 3 人）
        # 透明な背の高い立ち絵どうし（呪術廻戦）は別の絵
        from PIL import Image, ImageDraw
        for u in ("https://dodo.ac/np/images/thumb/b/b3/Crazy_Redd_SSBB_Trophy.png/400px-Crazy_Redd_SSBB_Trophy.png",
                  "https://static.wikia.nocookie.net/g/images/a/a9/Item_Stella_Fortuna_%285_Star%29.png/revision/latest?cb=1"):
            self.assertTrue(ef.emblem.bad_source({"source": u}), u)
        self.assertFalse(ef.emblem.bad_source({"source": "https://static.wikia.nocookie.net/g/images/c/c3/Character_Itto_Full_Wish.png/revision/latest?cb=1"}))

        def man(color):
            im = Image.new("RGBA", (170, 520), (0, 0, 0, 0))
            ImageDraw.Draw(im).rectangle((40, 20, 130, 500), fill=color)
            return im
        a, b = man((150, 100, 50, 255)), man((20, 20, 30, 255))
        xs = [{"image": "emblems/v.webp", "source": "u1", "subject": "A"}, {"image": "emblems/v.webp", "source": "u2", "subject": "A2"},
              {"image": "emblems/x.webp", "source": "u3", "subject": "B"}, {"image": "emblems/y.webp", "source": "u4", "subject": "C"},
              {"image": "emblems/z.webp", "source": "u5", "subject": "D", "lock": True}]
        imgs = {"emblems/v.webp": a, "emblems/x.webp": b, "emblems/y.webp": b, "emblems/z.webp": b}
        files, looks = ef.same_pics(xs, lambda x: imgs[x["image"]])
        self.assertEqual([x["subject"] for x in files], ["A2"])
        self.assertEqual([x["subject"] for x in looks], ["C"])   # 固定の D は残す
        self.assertGreater(bin(ef._hash(a) ^ ef._hash(b)).count("1"), ef.SAME_BITS)

    def test_broken_image_whole_figure(self):
        """公式の全身の絵（body の足の裏が画像の中）の上の端は絵そのもの：ポチタの平らな持ち手は「頭が切れた」ではない。"""
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((10, 0, 90, 119), fill=(40, 40, 40, 255))   # 上の端の近くが丸く広い（持ち手）
        self.assertTrue(ef.broken_image(im, False))
        self.assertFalse(ef.broken_image(im, False, whole=True))
        self.assertTrue(ef.broken_image(Image.new("RGBA", (60, 10), (1, 1, 1, 255)), False, whole=True))   # 切れ端は全身でも外す

    def test_real_body_no_model_no_face(self):
        """姿勢モデルがなく（Actions）顔も見つからない絵（ポチタ）は、上半身に切らず全身（前は多数決で切って顔の切れ端になった）。"""
        from PIL import Image, ImageDraw
        import emblem
        im = Image.new("RGBA", (100, 160), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((10, 20, 90, 150), fill=(220, 120, 60, 255))
        with mock.patch.object(emblem, "_pose_model", return_value=None), mock.patch.object(emblem, "face_box", return_value=None):
            self.assertIs(emblem.real_body(im, (0.3, 0.95, 0.5, 0.6, 0.7))[0], False)
        with mock.patch.object(emblem, "_pose_model", return_value=None), mock.patch.object(emblem, "face_box", return_value=(1, 2, 3, 4)):
            self.assertIsNone(emblem.real_body(im, (0.3, 0.95, 0.5, 0.6, 0.7))[0])

    def test_broken_image_two_people(self):
        # 2 番目の顔がいちばん大きい顔と同じくらい（CROWD_H）= 2 人が並んだ切り抜きは前からのものも外す（点検 E11）
        from unittest import mock
        from PIL import Image
        im = Image.new("RGBA", (200, 200))
        with mock.patch.object(ef.emblem, "head_cut", return_value=False), mock.patch.object(ef.emblem, "flat_flaw", return_value=False), \
                mock.patch.object(ef.emblem, "top_share", return_value=0.0):
            with mock.patch.object(ef.emblem, "other_faces", return_value=1) as m:
                self.assertTrue(ef.broken_image(im, False))
                self.assertEqual(m.call_args.kwargs["ratio"], ef.emblem.CROWD_H)
            with mock.patch.object(ef.emblem, "other_faces", return_value=0):
                self.assertFalse(ef.broken_image(im, False))

    def test_unbreak_restores_by_current_rule(self):
        # 前の版の broken_cuts で外した小元素を、今の規則で外れなければ戻し、emblem_reject からも抜く
        import tempfile
        from unittest import mock
        from PIL import Image
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "emblems").mkdir()
        (tmp / "state").mkdir()
        Image.new("RGBA", (200, 200)).save(tmp / "emblems" / "g.webp")
        Image.new("RGBA", (200, 200)).save(tmp / "emblems" / "k.webp")
        g = {"subject": "G（a）", "image": "emblems/g.webp", "source": "http://s/g"}
        k = {"subject": "K（b）", "image": "emblems/k.webp", "source": "http://s/k"}
        (tmp / "state" / "emblem_broken.json").write_text(json.dumps({"M": [{"v": 1, "emblem": g}, {"v": 1, "emblem": k}]}), encoding="utf-8")
        (tmp / "items.yaml").write_text('items:\n  - name: M\n    emblem_kind: character\n    emblem_reject: ["http://s/g", "http://s/k", "http://s/z"]\n'
                                        '    emblem:\n      - {subject: "D（c）", image: "emblems/d.webp"}\n', encoding="utf-8")
        item = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef.emblem, "ROOT", tmp), mock.patch.object(ef.emblem.sitedir, "SITE_DIR", tmp), \
                mock.patch.object(ef, "broken_cuts", side_effect=lambda it: [x for x in it["emblem"] if x["subject"].startswith("K")]):
            self.assertEqual([i["name"] for i in ef.due({"items": {}}, [{**item, "emblem_target": 1}], "2026-10-25T00:00:00")], ["M"])
            self.assertEqual(ef.unbreak(item, log=lambda *_: None), 1)
            got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
            self.assertEqual(ef.unbreak(got, log=lambda *_: None), 0)   # 見直しは版ごとに 1 回
        self.assertEqual([x["subject"] for x in got["emblem"]], ["D（c）", "G（a）"])
        self.assertEqual(got["emblem_reject"], ["http://s/k", "http://s/z"])
        self.assertEqual(json.loads((tmp / "state" / "emblem_broken.json").read_text(encoding="utf-8")), {"M": [{"v": ef.BROKEN_V, "emblem": k}]})

    def test_role_image_needs_tie_without_anchor_face(self):
        # 作り直しの剧：役の記事の代表画像は前の映画の役者（PadmaPatil.png）。出演者の顔の基準がなければ、作品・出演者の名前がある画像だけ
        self.assertFalse(ef.tied("https://x/harrypotter/images/4/45/PadmaPatil.png/revision/latest?cb=20220930", "Anjula Murali", "Harry Potter"))
        self.assertTrue(ef.tied("https://x/images/6/6e/Ravenclaw_students_HPTV.jpg", "Anjula Murali", "Harry Potter"))
        self.assertTrue(ef.tied("File:Nick Frost as Rubeus Hagrid.jpg", "Nick Frost", "Harry Potter"))
        # 作品の始まり（剧 2026-12）の 2 年前より後に上がった画像はこの作品のもの（FROM の Sarah_Myers_Season_3.png?cb=20241106）
        self.assertFalse(ef.tied("https://x/PadmaPatil.png/revision/latest?cb=20220930", "Anjula Murali", "Harry Potter", "20241225"))
        self.assertTrue(ef.tied("https://x/Sarah_Myers_Season_3.png/revision/latest?cb=20241106", "Avery Konrad", "From", "20200220"))
        from unittest import mock
        from PIL import Image
        img = Image.linear_gradient("L").convert("RGB")   # 白紙でない画像
        cands = [{"subject": "P（A）", "image": "http://a", "source": "基準（出演者の写真）", "anchor": True, "anchor_only": True},
                 {"subject": "P（A）", "image": "http://lead", "source": "役の記事", "untied": True},
                 {"subject": "P（A）", "image": "http://still", "source": "役の記事", "untied": True},
                 {"subject": "P（A）", "image": "http://hptv", "source": "役の記事", "untied": False}]
        info = lambda im: (None, {"faces": 4, "ratio": 0.3, "second": 0.9}) if im.info.get("u") == "http://a" else ("f", {"faces": 1, "ratio": 0.3, "second": 0})

        def insp(data):
            im = img.copy()
            im.info["u"] = data
            return "photo", None, im
        with mock.patch.object(ef, "_get", side_effect=lambda u, *a: u), mock.patch.object(ef, "inspect", side_effect=insp), \
                mock.patch.object(ef.face_id, "face_info", side_effect=info), \
                mock.patch.object(ef.face_id, "same_person", side_effect=lambda f, a, strict: {k for k, x in enumerate(f) if x is not None}), \
                mock.patch.object(ef, "_hash", side_effect=lambda im: hash(im.info["u"])):
            got = ef.check(cands, log=lambda *_: None, need_face=True, strict=True)
        self.assertEqual([c["image"] for c in got], ["http://hptv"])

    def test_is_remake(self):
        # 原作が同じ別の映像作品がある剧だけ作り直し（哈利波特剧集）。FROM は前の映画がないので外さない
        from unittest import mock
        ent = lambda **c: {"entities": {k: {"claims": v} for k, v in c.items()}}
        cl = lambda p, q: {p: [{"mainsnak": {"datavalue": {"value": {"id": q}}}}]}
        tbl = {"QHP": ent(QHP=cl("P144", "QBOOK")), "QBOOK": ent(QBOOK=cl("P4969", "QFILM")),
               "QFROM": ent(QFROM={}), "QF2": ent(QF2=cl("P144", "QB2")), "QB2": ent(QB2=cl("P4969", "QF2"))}
        ef._REMAKE.clear()
        with mock.patch.object(ef, "_wd_get", side_effect=lambda p: tbl[p["ids"]]):
            self.assertTrue(ef.is_remake({"wikidata": "QHP"}))
            self.assertFalse(ef.is_remake({"wikidata": "QFROM"}))
            self.assertFalse(ef.is_remake({"wikidata": "QF2"}))   # 原作の派生が自分だけ
            self.assertFalse(ef.is_remake({}))
        ef._REMAKE.clear()

    def test_faceless_scrap(self):
        # 写真の切り抜きに顔がなく横長 = 髪・額だけの切れ端（哈利波特剧集 Hermione 194×92）は外す。顔のない縦長の兜は残す
        from unittest import mock
        from PIL import Image
        wide, tall = Image.new("RGBA", (194, 92), (20, 20, 20, 255)), Image.new("RGBA", (396, 492), (20, 20, 20, 255))
        with mock.patch.object(ef.emblem, "face_sharp", return_value=None), mock.patch("face_id.engine", return_value=object()):
            self.assertTrue(ef.emblem.faceless_scrap(wide))
            self.assertFalse(ef.emblem.faceless_scrap(tall))
            self.assertTrue(ef.broken_image(wide, True))
        with mock.patch.object(ef.emblem, "face_sharp", return_value=(100, 2.0, 0.5)), mock.patch("face_id.engine", return_value=object()):
            self.assertFalse(ef.emblem.faceless_scrap(wide))
        with mock.patch("face_id.engine", return_value=None):
            self.assertFalse(ef.emblem.faceless_scrap(wide))

    def test_head_cut_and_blur(self):
        # 頭のてっぺんが上の端で切れた（上 3px に 20% 以上）切り抜きは取るときも前からのものも外す。写真はぼやけたもの（SHARP_MIN 未満）も
        import tempfile
        from unittest import mock
        from PIL import Image, ImageDraw
        cut = Image.new("RGBA", (200, 200))
        ImageDraw.Draw(cut).ellipse((50, -60, 150, 199), fill=(90, 60, 40, 255))
        self.assertTrue(ef.emblem.head_cut(cut))
        with self.assertRaisesRegex(ValueError, "頭のてっぺん"):
            ef.emblem.check_whole(cut)
        ok = Image.new("RGBA", (200, 200))
        ImageDraw.Draw(ok).ellipse((50, 10, 150, 199), fill=(90, 60, 40, 255))
        self.assertFalse(ef.emblem.head_cut(ok))
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "emblems").mkdir()
        cut.save(tmp / "emblems" / "a.webp")
        ok.save(tmp / "emblems" / "b.webp")
        ok.save(tmp / "emblems" / "c.webp")
        item = {"emblem_kind": "person", "emblem": [{"subject": s, "image": f"emblems/{s.lower()}.webp"} for s in "ABC"]}
        sharp = lambda im: (100, 0.5 if im.filename.endswith("c.webp") else 1.5)
        with mock.patch.object(ef.emblem.sitedir, "SITE_DIR", tmp), mock.patch.object(ef.emblem, "forehead_cut", return_value=False), \
                mock.patch.object(ef.emblem, "face_sharp", side_effect=sharp):
            self.assertEqual([x["subject"] for x in ef.broken_cuts(item)], ["A", "C"])
            self.assertEqual([x["subject"] for x in ef.broken_cuts({**item, "emblem_kind": "character"})], ["A"])   # 絵はぼやけを見ない

    def test_subjects_skip_not_character_already_in_who(self):
        # もうある名簿の Player・Parents（あつ森）も集めない：先頭の HEAD 人に入らない
        who = ["A", "B", "Player", "C", "Special character", "D", "Parents"] + [f"c{i}" for i in range(20)]
        got = ef.subjects({"type": "game", "emblem_who": who}, "character", 30)
        self.assertFalse({"Player", "Parents", "Special character"} & set(got))
        self.assertEqual(got[:ef.HEAD], ["A", "B", "C", "D", "c0"][:ef.HEAD])

    def test_roster_writes_pool_and_names(self):
        import tempfile, shutil
        from unittest import mock
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            (tmp / "items.yaml").write_text(
                'items:\n  - name: G\n    type: game\n    emblem_kind: character\n    emblem_who: ["A", "Player"]\n'
                '    emblem_fandom: g\n    emblem_category: "Playable"\n  - name: H\n    type: game\n', encoding="utf-8")
            with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef.emblem, "category_top", return_value=["B", "A", "C"]):
                item = yaml.safe_load((tmp / "items.yaml").read_text())["items"][0]
                self.assertEqual(ef.roster(item, log=lambda *_: None), 3)
            got = yaml.safe_load((tmp / "items.yaml").read_text())["items"]
            self.assertEqual(got[0]["emblem_pool"], 3)
            self.assertEqual(got[0]["emblem_who"], ["A", "B", "C"])   # 前からいる Player は外し、今の名前の後ろに、中心にいる順で足す
            self.assertNotIn("emblem_pool", got[1])
        finally:
            shutil.rmtree(tmp)

    def test_category_top_continues(self):
        """分類が 200 人を超えたら続き（cmcontinue）、参照が 500 を超えたら続き（lhcontinue）で数える。分類の説明の記事・下位のページは除く。"""
        import json as js
        from unittest import mock
        from urllib.parse import parse_qs, urlparse

        def fake_get(url, limit=0):
            q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
            if q.get("list") == "categorymembers":
                first = "cmcontinue" not in q
                names = ["Character", "Aino", "Aino/Storyline", "Band"] if first else ["Zhongli"]
                return js.dumps({"query": {"categorymembers": [{"title": n} for n in names]},
                                 **({"continue": {"cmcontinue": "z", "continue": "-||"}} if first else {})}).encode()
            if q.get("prop") == "categories":   # 集まりのページ（Music bands）は人ではない
                return js.dumps({"query": {"pages": {str(i): {"title": x, "categories": [{"title": "Category:Music bands" if x == "Band" else "Category:Characters"}]}
                                                     for i, x in enumerate(q["titles"].split("|"))}}}).encode()
            t, more = q["titles"], "lhcontinue" not in q
            n = {"Aino": 10, "Zhongli": 500}[t]
            return js.dumps({"query": {"pages": {"1": {"linkshere": [{}] * n, "length": 5}}},
                             **({"continue": {"lhcontinue": "x", "continue": "||"}} if t == "Zhongli" and more else {})}).encode()
        with mock.patch.object(ef.emblem, "_get", fake_get):
            gone = set()
            self.assertEqual(ef.emblem.category_top("https://g.fandom.com/api.php", "Characters", 5, gone), ["Zhongli", "Aino"])
            self.assertEqual(gone, {"Band"})

    def test_fringe_drops_short_low_link_pages_only(self):
        """60 人以上の分類で、参照が中央値の 1 割未満かつ記事が短いページだけ外す。参照が少ないだけの新キャラ（Ringmaster 33/5521）は残す。小さい分類は何も外さない。"""
        counts = {f"H{i}": 400 + i for i in range(60)}
        length = {t: 30000 for t in counts}
        counts.update({"Yasuo": 23, "Irelia": 21, "John Raider": 1, "Ringmaster": 33, "Bloodchemist": 37})
        length.update({"Yasuo": 1559, "Irelia": 978, "John Raider": 1636, "Ringmaster": 5521, "Bloodchemist": 30963})
        self.assertEqual(ef.emblem.fringe(counts, length), {"Yasuo", "Irelia", "John Raider"})
        small = {f"G{i}": 5 for i in range(20)}
        small["X"] = 0
        self.assertEqual(ef.emblem.fringe(small, {}), set())

    def test_brand_without_logo_uses_p18(self):
        """ロゴ（P154）のない製品は Wikidata の代表画像（P18）。iPhone が 0 枚にならない。"""
        from unittest import mock
        calls = []

        def fake_wd(q, props=("P154", "P18"), limit=3):
            calls.append(props)
            return [] if props == ("P154",) else [{"title": "IPhone.svg", "image": "https://c/i.png"}]
        with mock.patch.object(ef, "wikidata_images", fake_wd), mock.patch.object(ef, "commons_photos", lambda *a, **k: []), \
                mock.patch.object(ef, "wiki_titles", lambda item: {}):
            cands = ef.gather({"name": "iPhone", "type": "product", "emblem_kind": "brand", "wikidata": "Q2766"}, log=lambda *a: None)
        self.assertIn(("P18",), calls)
        self.assertEqual([c["image"] for c in cands], ["https://c/i.png"])

    def test_own_logo(self):
        self.assertFalse(ef.own_logo("File:Logo of the Linksys iPhone.svg", "iPhone"))   # 別の会社の iPhone
        self.assertTrue(ef.own_logo("File:IPhone logo 2016.svg", "iPhone"))
        self.assertTrue(ef.own_logo("File:Gelato pique logo.svg", "gelato pique"))
        self.assertFalse(ef.own_logo("File:京都 決済.jpg", "京都"))   # ロゴのファイルでない

    def test_not_emblem(self):
        for bad in ("Kyoto (Chinese characters).svg", "Oversimplification on how AI Model Text 2 Image works.png",
                    "Wrestling at Tokyo 1890s.jpg", "Kunisada Sumo Triptychon c1860s.jpg"):
            self.assertTrue(ef.not_emblem(bad), bad)
        for ok in ("Asashoryu fight Jan08.JPG", "Shogi.jpg", "IPhone 17 Pro Vector.svg", "Emblem of Kyoto, Kyoto.svg", "Tokyo Tower 2023.jpg"):
            self.assertFalse(ef.not_emblem(ok), ok)

    def test_status(self):
        base = {"name": "x", "type": "game"}
        self.assertEqual(ef.status(base)["state"], "none")
        self.assertEqual(ef.status({**base, "emblem": [{}] * 2})["state"], "low")
        self.assertEqual(ef.status({**base, "emblem": [{}] * 6})["state"], "ok")
        # emblem_skip は「足りている」の理由にならない
        self.assertEqual(ef.status({**base, "emblem_skip": "なし"})["state"], "none")

    def test_audit_sorts_gaps_first(self):
        rows = ef.audit([{"name": "a", "type": "game", "emblem": [{}] * 6}, {"name": "b", "type": "game"},
                         {"name": "c", "type": "game", "emblem": [{}]}])
        self.assertEqual([r["name"] for r in rows], ["b", "c", "a"])

    def test_every_item_resolves(self):
        items = (yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]
                 )
        for i in items:
            st = ef.status(i)
            self.assertIn(st["kind"], ef.RULES, i["name"])
            self.assertLessEqual(st["target"], ef.CEIL[st["kind"]], i["name"])   # 上限は要素の数（天井 CEIL）
            self.assertGreaterEqual(st["target"], st["lo"], i["name"])
            if i.get("emblem_kind"):
                self.assertIn(i["emblem_kind"], ef.RULES, i["name"])


class Sources(unittest.TestCase):
    def test_wide_logo_is_not_too_small(self):
        import emblem
        import io as _io
        from PIL import Image

        def png(w, h):
            b = _io.BytesIO()
            Image.new("RGB", (w, h), "white").save(b, "PNG")
            return b.getvalue()
        emblem.inspect(png(500, 133))   # 横長のロゴは長い辺 300 以上なら使える
        for w, h in ((120, 120), (280, 60), (500, 50)):
            with self.assertRaises(ValueError):
                emblem.inspect(png(w, h))

    def test_parse_bing(self):
        html = ('x murl&quot;:&quot;https://a.example/p/1.jpg&quot; y murl&quot;:&quot;https://a.example/p/1.jpg&quot; '
                'murl&quot;:&quot;https://b.example/bad name.png&quot; murl&quot;:&quot;https://c.example/2.webp?x=1&quot;')
        urls = [x["image"] for x in ef.parse_bing(html)]
        self.assertEqual(urls, ["https://a.example/p/1.jpg", "https://c.example/2.webp?x=1"])   # 重複と空白入りの網址は除く

    def test_relevant(self):
        self.assertTrue(ef.relevant("File:Starbucks Corporation Logo 2011.svg.png", "Starbucks"))
        self.assertFalse(ef.relevant("File:Chopin portrait.jpg", "Jay Chou"))
        self.assertTrue(ef.relevant("File:周杰倫 2014.jpg", "周杰倫"))

    def test_twemoji(self):
        self.assertTrue(ef.twemoji("🎾")["image"].endswith("/1f3be.svg"))
        self.assertTrue(ef.twemoji("⛷️")["image"].endswith("/26f7.svg"))   # 異体字セレクタは落とす

    def test_site_images_skip_logos(self):
        import types
        ef_get = ef._get
        ef._get = lambda url, limit=0: (b'<meta property="og:image" content="/og.png"><img src="/img/logo.png">'
                                        b'<img src="/img/member1.jpg">')
        try:
            urls = [x["image"] for x in ef.site_images("https://x.example/a/")]
        finally:
            ef._get = ef_get
        self.assertEqual(urls, ["https://x.example/og.png", "https://x.example/img/member1.jpg"])

    def test_auto_pick_prefers_reliable_sources(self):
        good = [{"subject": "A", "source": "Web 画像検索"}, {"subject": "A", "source": "Wikipedia"},
                {"subject": "B", "source": "Fandom"}, {"subject": "B", "source": "Web 画像検索"}]
        item = {"type": "game", "emblem_who": ["A", "B"]}
        self.assertEqual(sorted(ef.auto_pick(item, good)), [2, 3])   # 1 人 1 枚、Web 検索より Wiki 系を先に


    def test_auto_pick_background_skips_web_and_existing(self):
        item = {"type": "event", "emblem_kind": "group", "emblem_who": ["A", "B", "C"],
                "emblem": [{"subject": "A", "image": "emblems/a.webp", "source": "https://x.example/a.jpg"}]}
        good = [{"subject": "A", "source": "Wikipedia", "image": "https://x.example/a2.jpg"},   # A はもうある
                {"subject": "B", "source": "Web 画像検索", "image": "https://x.example/b.jpg"},
                {"subject": "C", "source": "Wikipedia", "image": "https://x.example/a.jpg"},   # 同じ画像はもうある
                {"subject": "C", "source": "新聞の配図", "image": "https://x.example/c.jpg"}]
        self.assertEqual(ef.auto_pick(item, good, web=False), [4])
        self.assertEqual(sorted(ef.auto_pick(item, good)), [2, 4])

    def test_auto_pick_skips_rejected(self):
        item = {"type": "event", "emblem_kind": "person", "emblem_reject": ["https://x.example/bad.jpg"]}
        good = [{"subject": "A", "source": "Wikipedia", "image": "https://x.example/bad.jpg"},
                {"subject": "A", "source": "Wikipedia", "image": "https://x.example/ok.jpg"}]
        self.assertEqual(ef.auto_pick(item, good, web=False, strict=True), [2])

    def test_auto_pick_brand_prefers_wikidata_logo(self):
        item = {"type": "product", "emblem_kind": "brand"}
        good = [{"subject": "X", "source": "Wikimedia Commons", "image": "c"}, {"subject": "X", "source": "公式サイト", "image": "s"},
                {"subject": "X", "source": "Wikidata", "image": "w"}]
        self.assertEqual(ef.auto_pick(item, good, web=False), [3])

    def test_topic_examples(self):
        # ジャンルの版面は「下の一段」（代表作）を 1 作 1 枚、Twemoji の記号より先に
        item = {"type": "category", "emblem_examples": ["en:Blade & Soul", "en:Aion 2", "en:ArcheAge", "en:Throne and Liberty"]}
        self.assertEqual(ef.rule(item)[2], 4)
        good = [{"subject": "🛡 アイコン", "source": "Twemoji", "image": "t"},
                {"subject": "Blade & Soul", "source": "代表作(Wikipedia)", "image": "b1"},
                {"subject": "Blade & Soul", "source": "代表作(Wikidata)", "image": "b2"},
                {"subject": "Aion 2", "source": "代表作(Wikipedia)", "image": "a"}]
        self.assertEqual(ef.auto_pick(item, good, web=False, strict=True), [2, 4, 1])

    def test_same_name(self):
        self.assertTrue(ef.same_name("Aion 2 (video game)", "Aion 2"))
        self.assertTrue(ef.same_name("Blade & Soul", "blade&soul"))
        self.assertFalse(ef.same_name("Lightning Returns: Final Fantasy XIII", "Odin: Valhalla Rising"))

    def test_auto_pick_strict_drawn_characters(self):
        # 絵のキャラは、後台ではキャラ専用の取り方だけ（Commons の「Juggernaut」はバンドの写真だった）
        item = {"type": "game", "emblem_who": ["Juggernaut", "Axe"]}
        good = [{"subject": "Juggernaut", "source": "Wikimedia Commons", "image": "c"},
                {"subject": "Axe", "source": "直接指定", "image": "d"}]
        self.assertEqual(ef.auto_pick(item, good, web=False, strict=True), [2])
        people = {"type": "show", "emblem_people": True, "emblem_who": ["A"]}
        self.assertEqual(ef.auto_pick(people, [{"subject": "A", "source": "Wikimedia Commons", "image": "c"}], web=False, strict=True), [1])

    def test_needs_face(self):
        self.assertTrue(ef.needs_face({"type": "event"}))
        self.assertTrue(ef.needs_face({"type": "show", "emblem_people": True}))
        self.assertFalse(ef.needs_face({"type": "show"}))
        self.assertFalse(ef.needs_face({"type": "product"}))


class Background(unittest.TestCase):
    """定時の後台（--background）と進捗ファイル。ネットには出ず、fill を差し替える。"""

    ITEMS = [{"name": "full", "type": "game", "emblem_who": ["a"], "emblem": [{"subject": "a", "image": "x"}]},
             {"name": "one", "type": "game", "emblem": [{}]},
             {"name": "zero", "type": "game"},
             {"name": "brand", "type": "product"}]

    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.dir.name) / "emblem_progress.json"
        self.items = [dict(i) for i in self.ITEMS]
        self._load = ef.load_items
        ef.load_items = lambda: self.items
        self._logdir = runlog.LOG_DIR
        runlog.LOG_DIR = pathlib.Path(self.dir.name) / "log"   # 本物の state/log に書かない

    def tearDown(self):
        ef.load_items = self._load
        runlog.LOG_DIR = self._logdir
        self.dir.cleanup()

    def test_sync_progress(self):
        prog = ef.sync_progress({"items": {"gone": {"state": "ok"}}}, self.items)
        self.assertNotIn("gone", prog["items"])
        self.assertEqual(prog["items"]["full"]["state"], "ok")
        self.assertEqual(prog["items"]["zero"]["state"], "running")
        self.assertEqual(prog["summary"], {"ok": 1, "total": 4})

    def test_due_order_and_failed_skip(self):
        now = "2026-10-17T00:00:00+00:00"
        prog = ef.sync_progress({"items": {}}, self.items)
        self.assertEqual([i["name"] for i in ef.due(prog, self.items, now)], ["zero", "one", "brand"])   # 足りない枚数の多い順
        zero = next(i for i in self.items if i["name"] == "zero")
        prog["items"]["zero"].update(state="failed", failed_at="2026-10-16T23:30:00+00:00", material=ef.material(zero))
        self.assertEqual(ef.RETRY_HOURS, 1)   # AI なし：6 時間は待たせすぎ（2026-10-22）→ 毎時の後台で毎回
        self.assertEqual([i["name"] for i in ef.due(prog, self.items, now)], ["one", "brand"])   # 1 時間以内・材料が同じ失敗は飛ばす
        self.assertEqual(ef.waiting(prog, self.items, now), [("zero", "2026-10-17T00:30:00+00:00")])   # 再挑戦待ちとして見える
        from unittest import mock
        with mock.patch.object(ef, "broken_cuts", side_effect=lambda i: [1] if i["name"] == "zero" else []):
            self.assertIn("zero", [i["name"] for i in ef.due(prog, self.items, now)])   # 頭が切れた・ぼやけた小元素のある版面は待たない
        with mock.patch.object(ef, "closeup_state", return_value={"zero": {"Ichigo": {"n": 1}}}):
            self.assertIn("zero", [i["name"] for i in ef.due(prog, self.items, now)])   # 胸像待ちの版面は失敗の待ちに入らない（BLEACH が 1 度も回らなかった）
        for v in ef.RULE_VERSION_NAMES:   # 規則の版が上がった：材料が同じでも待たずにやり直す（版ごと）
            with mock.patch.object(ef, v, getattr(ef, v) + 1):
                self.assertIn("zero", [i["name"] for i in ef.due(prog, self.items, now)], v)
        prog["items"]["zero"].pop("material")   # 指紋の記録がない古い失敗は待たない
        self.assertIn("zero", [i["name"] for i in ef.due(prog, self.items, now)])
        self.assertEqual(ef.waiting(prog, self.items, now), [])
        prog["items"]["zero"]["material"] = "old"   # 新しい記事・手がかりが来た
        self.assertIn("zero", [i["name"] for i in ef.due(prog, self.items, now)])
        prog["items"]["zero"].update(material=ef.material(zero), failed_at="2026-10-16T22:59:00+00:00")
        self.assertIn("zero", [i["name"] for i in ef.due(prog, self.items, now)])   # 1 時間たった
        prog["items"]["zero"]["exhausted"] = True   # 残りが全員「画像のない人」：1 日おき（1 時間では飛ばす）
        self.assertNotIn("zero", [i["name"] for i in ef.due(prog, self.items, now)])
        prog["items"]["zero"]["failed_at"] = "2026-10-15T23:00:00+00:00"
        self.assertIn("zero", [i["name"] for i in ef.due(prog, self.items, now)])

    def test_rule_versions_all_listed(self):
        """*_V（規則の版）を足して RULE_VERSION_NAMES に入れ忘れると、失敗の待ちが解けない（#526 のあとの BLEACH）。"""
        import re
        found = {k for k, v in vars(ef).items() if re.fullmatch(r"[A-Z]+_V", k) and isinstance(v, int)}
        self.assertEqual(found, set(ef.RULE_VERSION_NAMES))

    def test_background_streams_lines(self):
        """管理ページのライブログ：開始・版面ごとの作業の 1 行 1 行・結果・終了が live_log に流れる（「今すぐ再挑戦」から起きたらそう書く）。"""
        import livestatus
        sent = []
        lines = livestatus.Lines("emblem", send=sent.extend)

        def fill(item, log):
            log("  [別人] X（役の記事）cos 0.1")
            return {"state": "failed", "note": "0 枚足した", "tried": {"役の記事": 3}}
        with mock.patch.dict(os.environ, {"EMBLEM_RETRY_NOW": "1"}):
            ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=1, lines=lines)
        texts = [(r["board"], r["text"], r["level"]) for r in sent]
        self.assertTrue(texts[0][1].startswith("管理ページの「今すぐ再挑戦」から起動"))
        self.assertTrue(texts[1][1].startswith("開始：予算 40 分"))
        self.assertIn(("zero", "[別人] X（役の記事）cos 0.1", "info"), texts)
        self.assertIn(("zero", "→ 失敗：0 枚足した", "error"), texts)
        self.assertTrue(texts[-1][1].startswith("終了：3 版面を処理") and texts[-1][2] == "ok")
        self.assertTrue(all(r["proc"] == "emblem" and r["at"] for r in sent))

    def test_lines_without_key_send_nothing(self):
        import livestatus
        with mock.patch.dict(os.environ, {"SUPABASE_SERVICE_KEY": ""}):
            lines = livestatus.Lines("emblem")
        lines.add("x")
        lines.close()
        self.assertIsNone(lines.send)
        self.assertEqual(lines.buf, [])

    def test_background_tells_the_page(self):
        """版面の「更新中」の帯：処理を始めた版面に work、増えた版面は wait、増えなかった・失敗した版面は clear。"""
        calls, filled = [], set()

        def fill(item, log):
            if item["name"] == "zero":
                raise RuntimeError("boom")
            if item["name"] == "one":
                filled.add("one")   # items.yaml に 6 枚書いた
                return {"state": "ok", "note": "", "tried": {}}
            return {"state": "review", "note": "", "tried": {}}
        with mock.patch.object(ef, "load_items", side_effect=lambda: [dict(i, emblem=[{}] * 6) if i["name"] in filled else i for i in self.items]):
            ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=1,
                          live=lambda board, proc, state, note=None, eta=None: calls.append((board, state)))
        self.assertEqual(calls, [("zero", "work"), ("zero", "clear"), ("one", "work"), ("one", "wait"), ("brand", "work"), ("brand", "clear")])

    def test_background_records_each_item(self):
        seen = []

        def fill(item, log):
            seen.append(item["name"])
            if item["name"] == "zero":
                raise RuntimeError("boom")
            if item["name"] == "one":
                item["emblem"] = [{}] * 6   # 目標に届いた
                return {"state": "ok", "note": "5 枚足した", "tried": {"Fandom": 5}}
            return {"state": "review", "note": "一覧で確かめる", "tried": {"Wikidata": 0}, "sheet": "/tmp/x.jpg"}
        prog = ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=1)
        self.assertEqual(seen, ["zero", "one", "brand"])
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["items"]["zero"]["state"], "failed")   # 1 つの失敗で止まらない
        self.assertIn("failed_at", saved["items"]["zero"])
        self.assertEqual(saved["items"]["one"]["state"], "ok")
        self.assertEqual(saved["items"]["brand"]["state"], "review")
        self.assertEqual(saved["items"]["brand"]["tried"], {"Wikidata": 0})
        self.assertEqual(saved["last_run"]["done"], ["zero", "one", "brand"])
        self.assertTrue(saved["started"] and saved["last_run"]["end"])
        self.assertEqual(prog["summary"], {"ok": 2, "total": 4})
        # 2 回目：失敗したものは飛ばし、開始時刻は最初のまま
        seen.clear()
        again = ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=1)
        self.assertEqual(seen, ["brand"])
        self.assertEqual(again["started"], saved["started"])
        log = runlog.recent(50)
        self.assertTrue(all(r["proc"] == "emblem" for r in log))
        texts = [r["text"] for r in log]
        self.assertTrue(any(t.startswith("開始：予算 40 分・1 本並列・待ち 3 版面") for t in texts))
        self.assertTrue(any(t.startswith("zero：失敗") for t in texts))
        self.assertEqual(next(r for r in log if r["text"].startswith("one：")).get("level"), "ok")

    def test_background_stops_when_out_of_time(self):
        seen = []

        def fill(item, log):
            seen.append(item["name"])
            raise ef.OutOfTime("x")
        prog = ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=1)
        self.assertEqual(seen, ["zero"])   # 途中で止めたら次に入らない
        self.assertEqual(prog["items"]["zero"]["state"], "running")
        self.assertNotIn("failed_at", prog["items"]["zero"])   # 失敗ではないので次の回にすぐやり直す

    def test_background_parallel(self):
        import threading
        import time as _t
        live, peak, lock = [0], [0], threading.Lock()

        def fill(item, log):
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            _t.sleep(0.2)
            with lock:
                live[0] -= 1
            return {"state": "review", "note": item["name"]}
        prog = ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=3)
        self.assertEqual(peak[0], 3)   # 3 つ同時に動いた
        self.assertEqual(sorted(prog["last_run"]["done"]), ["brand", "one", "zero"])
        self.assertEqual(prog["last_run"]["workers"], 3)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual({n: x["note"] for n, x in saved["items"].items() if n != "full"}, {"zero": "zero", "one": "one", "brand": "brand"})
        self.assertTrue(any("3 本並列" in r["text"] for r in runlog.recent(10)))

    def test_background_respects_budget(self):
        t = [0.0]

        def clock():
            return t[0]

        def fill(item, log):
            t[0] += 30 * 60   # 1 つに 30 分かかる
            return {"state": "review", "note": ""}
        prog = ef.background(40, log=lambda m: None, fill=fill, clock=clock, path=self.path, workers=1)
        self.assertEqual(prog["last_run"]["done"], ["zero", "one"])   # 30 分後（残り 10 分）は 2 つ目に入り、60 分後は入らない


class Identity(unittest.TestCase):
    """face_id.same_person の論理だけ確かめる（モデルなしで、特徴量の代わりに数を使う）。"""

    def setUp(self):
        self._eng, self._sim = face_id.engine, face_id.similarity
        face_id.engine = lambda: ("det", "rec")
        face_id.similarity = lambda a, b: 1.0 if a == b else 0.0

    def tearDown(self):
        face_id.engine, face_id.similarity = self._eng, self._sim

    def test_anchor_keeps_matching_only(self):
        # 0 が代表画像。顔なし（None）と別人（2）は落とす
        self.assertEqual(face_id.same_person([1, 1, None, 2, 1], anchor=0), {0, 1, 4})

    def test_majority_when_anchor_is_wrong(self):
        # 代表画像（0）だけ別の顔：同じ顔が多い方を本人とする
        self.assertEqual(face_id.same_person([9, 1, 1, 1], anchor=0), {1, 2, 3})

    def test_no_faces(self):
        self.assertEqual(face_id.same_person([None, None]), set())

    def test_unavailable_engine(self):
        face_id.engine = lambda: None
        self.assertIsNone(face_id.same_person([1, 1]))


class FaceEnginePerThread(unittest.TestCase):
    def test_engine_not_shared_between_threads(self):
        # 検出器を共有すると 6 本並列の後台が Segmentation fault で落ちた（#433 のあと）
        import threading
        saved = dict(face_id._engine)
        face_id._engine.clear()
        try:
            got = []
            t = threading.Thread(target=lambda: got.append(face_id.engine()))
            main = face_id.engine()
            t.start(); t.join()
            if main is not None:
                self.assertIsNot(got[0][0], main[0])
        finally:
            face_id._engine.clear(); face_id._engine.update(saved)


class Processes(unittest.TestCase):
    def test_flows_are_well_formed(self):
        ids = [p["id"] for p in processes.PROCESSES]
        self.assertEqual(len(ids), len(set(ids)))
        for p in processes.PROCESSES:
            self.assertIn(p["lane"], processes.LANES)
            self.assertTrue(p["flow"], p["id"])
            for n in p["flow"]:
                self.assertIn(n["kind"], ("step", "decision", "fan", "store", "table"), p["id"])
                self.assertIn(n.get("lane"), processes.LANES, (p["id"], n["id"]))
                if n["kind"] == "decision":
                    self.assertTrue(n.get("no"), (p["id"], n["id"]))   # はい = 下へ続く、いいえ = 右の箱
                if n["kind"] == "fan":
                    self.assertTrue(all(len(x) in (3, 4) for x in n["items"]))
                    for x in n["items"][3:4] and [it[3] for it in n["items"] if len(it) == 4]:
                        self.assertIn(x, processes.COMPONENTS, (p["id"], n["id"]))
                for c in n.get("uses", []):
                    self.assertIn(c, processes.COMPONENTS, (p["id"], n["id"]))
            for c in p.get("uses", []):
                self.assertIn(c, processes.COMPONENTS, p["id"])
                if n["kind"] == "table":
                    self.assertTrue(all(len(x) == 2 for x in n["rows"]))

    def test_architecture(self):
        out = processes.render()
        ids = set()
        for z in processes.ARCH:
            for n in z["nodes"]:
                ids.add(n["id"])
                ids |= {f"p-{x}" for x in n.get("subs", [])}
                if n.get("proc"):
                    self.assertIn(n["proc"], {p["id"] for p in processes.PROCESSES})
                for c in n.get("uses", []):
                    self.assertIn(c, processes.COMPONENTS, n["id"])
        for n, a, b, t, c in processes.EDGES:   # 矢印の両端は図の部品・色は凡例にあるもの
            self.assertIn(a, ids)
            self.assertIn(b, ids)
            self.assertIn(c, processes.EDGE_JA)
        self.assertEqual([x[0] for x in processes.EDGES], list(range(1, len(processes.EDGES) + 1)))
        shown = {p["id"] for p in processes.PROCESSES if f'data-open="proc-{p["id"]}"' in out}
        self.assertEqual(shown, {p["id"] for p in processes.PROCESSES})   # 全部のプロセスが図から開ける
        self.assertIn('id="arch-edges"', out)
        for c in processes.COMPONENTS.values():   # モデル・アルゴリズムは名前と数字つき
            self.assertTrue(c["name"] and c["kind"] in processes.KIND_LABEL)
        for name in ("rembg birefnet-general-lite", "YuNet", "SFace", "FASTOCTREE", "話題度 6 次元"):
            self.assertIn(name, out)
        d = processes.flow_diagram(next(p for p in processes.PROCESSES if p["id"] == "emblem-cron"))
        edges = json.loads(d.split('id="dge-emblem-cron">')[1].split("</script>")[0])
        self.assertTrue(any(x[3] == "いいえ" and x[5] for x in edges))   # 判断のいいえは破線の枝
        self.assertIn("dn-dec", d)
        self.assertIn("dn-fan", d)
        try:   # ARCH に置いていない新しい仕組みも「そのほか」から開ける
            processes.PROCESSES.append({"id": "zz", "name": "新しい仕組み", "en": "ZZ", "lane": "web", "trigger": "t", "summary": "s",
                                        "flow": [{"id": "a", "kind": "step", "lane": "web", "title": "x"}]})
            out2 = processes.render()
        finally:
            processes.PROCESSES.pop()
        self.assertIn('data-open="proc-zz"', out2)
        self.assertIn("そのほかの仕組み", out2)

    def test_render_and_escape(self):
        evil = [{"id": "x", "name": "<b>x</b>", "en": "X", "lane": "ai", "trigger": "t", "summary": "s",
                 "flow": [{"id": "n", "kind": "step", "lane": "ai", "title": "<script>", "text": "&"}]}]
        out = processes.render(evil)
        self.assertNotIn("<script>", out)
        self.assertNotIn("<b>x</b>", out)
        self.assertIn('id="proc-x"', out)

    def test_admin_page_has_processes_and_emblems(self):
        rows = [{"name": "A", "section": "游戏", "emblem": {"kind": "group", "kind_ja": "グループ", "have": 2, "target": 5, "hi": 10,
                                                          "lo": 3, "state": "low", "skip": False, "shapes": {"切り抜き": 2}}}]
        out = "".join(render.render_admin({"pipeline": {}, "items": rows, "votes": {}}, {}, "u").values())
        for p in processes.PROCESSES:
            self.assertIn(f'data-open="proc-{p["id"]}"', out)
        self.assertIn('id="emblems"', out)
        self.assertIn("順番待ち", out)   # 進捗にまだないものは「進行中（順番待ち）」

    def test_admin_emblem_progress(self):
        rows = [{"name": "A", "section": "游戏", "emblem": {"kind": "group", "kind_ja": "グループ", "have": 2, "target": 5, "hi": 10,
                                                          "lo": 3, "state": "low", "skip": False, "shapes": {}}},
                {"name": "B", "section": "游戏", "emblem": {"kind": "brand", "kind_ja": "ブランド", "have": 1, "target": 1, "hi": 1,
                                                          "lo": 1, "state": "ok", "skip": False, "shapes": {}}}]
        run = {"ok": 1, "total": 2, "started": "10/16 08:00", "last_run": "10/17 06:00", "minutes": 40, "done": 1,
               "items": {"A": {"state": "review", "note": "<残り> 3 枚", "at": "10/17 06:10"}, "B": {"state": "ok", "note": "", "at": None}}}
        out = "".join(render.render_admin({"pipeline": {}, "items": rows, "votes": {}, "emblem_run": run}, {}, "u").values())
        self.assertIn("<b>1</b> / 2 版面が目標に到達", out)
        self.assertIn('aria-valuenow="1"', out)
        self.assertIn("width:50%", out)
        self.assertIn('class="em-review">要確認', out)
        self.assertIn("&lt;残り&gt; 3 枚", out)   # 結果の文は転義する
        self.assertIn("10/17 06:00", out)
        em = out[out.index('id="emblems"'):]
        self.assertLess(em.index(">A<"), em.index(">B<"))   # 要確認が上



class Backend(unittest.TestCase):
    """管理ページ「バックグラウンド」：次の実行（定時）と、版面 × プロセスの表。"""

    def test_runlog_keeps_recent_per_proc(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            for i in range(runlog.KEEP + 5):
                runlog.add("collect", f"c{i}", log_dir=d)
            runlog.add("emblem", "e", "warn", log_dir=d)
            self.assertEqual(len(runlog.load("collect", d)), runlog.KEEP)
            self.assertEqual(runlog.load("collect", d)[-1]["text"], f"c{runlog.KEEP + 4}")
            rows = runlog.recent(3, d)
            self.assertEqual(len(rows), 3)
            self.assertEqual({r["proc"] for r in rows} <= {"collect", "emblem"}, True)
            self.assertEqual(next(r for r in runlog.recent(100, d) if r["proc"] == "emblem")["name"], "小元素の自動補完")

    def test_slots(self):
        by = {p["id"]: p for p in processes.PROCESSES}
        self.assertEqual(processes.slots(by["edit"]), [[0, 0], [9, 0]])   # 日本時間 9:00 / 18:00（gate.SLOTS と同じ）
        import gate
        self.assertEqual(sorted(((h - 9) % 24, m) for h, m in gate.SLOTS["edit"]), [tuple(x) for x in processes.slots(by["edit"])])
        self.assertEqual(processes.slots(by["emblem"]), processes.slots(by["edit"]))   # 選定は AI 編集の回に
        self.assertEqual(len(processes.slots(by["collect"])), 12)
        self.assertEqual(processes.slots(by["render"]), [])
        for p in processes.PROCESSES:
            for h, m in processes.slots(p):
                self.assertTrue(0 <= h < 24 and 0 <= m < 60, p["id"])

    def test_cells(self):
        import digest
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "2026-10-17.json").write_text(json.dumps({"items": [{"name": "A", "entries": [{}] * 3},
                                                                     {"name": "B", "entries": [{}] * 2}]}), encoding="utf-8")
            (d / "2026-10-17.edit.json").write_text(json.dumps({"_covered": {"A": 3, "B": 1}}), encoding="utf-8")
            old = digest.INBOX_DIR
            digest.INBOX_DIR = d
            try:
                items = [{"name": "A", "motif": "m", "theme": {"bg": "#000"}}, {"name": "B"}, {"name": "C", "motif": "m", "theme": {"bg": "#000"}}]
                rows = [{"name": n, "emblem": {"state": st, "have": h, "target": 6}} for n, st, h in
                        (("A", "ok", 6), ("B", "low", 2), ("C", "low", 1))]
                run = {"items": {"C": {"state": "review"}}, "queue": ["B"]}
                digest.backend_cells(items, rows, d / "2026-10-17.json", run)
            finally:
                digest.INBOX_DIR = old
        a, b, c = (r["bg"] for r in rows)
        self.assertEqual((a["collect"]["state"], a["edit"]["state"], a["design"]["state"], a["emblem"]["state"]), ("ok", "ok", "ok", "ok"))
        self.assertEqual(b["edit"], {"state": "wait", "text": "整理待ち 1 件（今日 2 件のうち）"})
        self.assertEqual(b["design"]["state"], "wait")
        self.assertIn("順番 1 番目", b["emblem"]["text"])
        self.assertEqual((c["collect"]["state"], c["edit"]["state"], c["emblem"]["state"]), ("idle", "idle", "review"))

    def test_render(self):
        bg = {k: {"state": "wait", "text": "<x>"} for k in ("collect", "edit", "design", "emblem")}
        rows = [{"name": "A", "section": "游戏", "bg": bg}, {"name": "B", "section": "好物", "bg": {**bg, "emblem": {"state": "failed", "text": ""}}}]
        todo = {"gate": {"text": "小元素 2 版面を Python で", "items": ["<A>", "B"]}}
        log = [{"when": "10/17 08:40", "proc": "emblem", "name": "小元素の自動補完", "level": "error", "text": "<b>x</b>"}]
        out = "".join(render._admin_backend(rows, todo, log).values())
        self.assertIn('class="nxs"', out)
        self.assertIn('id="bgq"', out)
        self.assertIn('href="#term-panel"', out)   # ログは一番上のライブログ（livelog.py）に移した
        cfg = json.loads(out.split('id="bg-cfg">')[1].split("</script>")[0])
        self.assertEqual(next(x for x in cfg if x["id"] == "gate")["items"], ["<A>", "B"])   # JS が textContent で入れる
        self.assertTrue(all(x["slots"] for x in cfg))
        self.assertIn('class="pbar"', out)
        self.assertIn('class="lims"', out)
        self.assertIn('class="aiu"', out)
        self.assertIn('id="livenow"', out)   # いま動いているもの（live_status を 30 秒ごと）
        for job in ("background", "collect", "render"):   # 今すぐ実行（db/run_now.sql の job と同じ名前）
            self.assertIn(f'data-run="{job}"', out)
        sql = (ROOT / "db" / "run_now.sql").read_text(encoding="utf-8")
        for job in set(render.RUN_JOBS.values()):
            self.assertIn(f"when '{job}'", sql)
        for t, k, _ in processes.AI_TASKS:
            self.assertIn(k, processes.AI_STATE_JA)
        for name, _, _ in processes.LIMITS:
            self.assertIn(name, out)
        self.assertIn("ライブログを見る", "".join(render._admin_backend(rows).values()))
        for p in processes.PROCESSES:   # 定時か Actions で動くものは「次の実行」に出る（AI 編集と同じ回のものは出さない）
            shown = f'data-open="proc-{p["id"]}"' in out
            self.assertEqual(shown, not isinstance(p.get("schedule"), str) and bool(processes.slots(p) or p.get("workflow") or p["id"] in render.BG_ON_EVENT), p["id"])
        self.assertIn('data-wf="digest.yml"', out)
        self.assertIn("&lt;x&gt;", out)
        self.assertNotIn("<x>", out)
        self.assertIn('class="bgc s-failed"', out)
        self.assertLess(out.index("ゲーム"), out.index("ショッピング"))   # 板块の順
        page = "".join(render.render_admin({"pipeline": {}, "items": rows, "votes": {}}, {}, "u").values())
        self.assertIn('id="backend"', page)
        self.assertLess(page.index('id="backend"'), page.index('id="procs"'))



class Resources(unittest.TestCase):
    """リソース：サーバーの様子・容量・トークン（管理ページ「バックグラウンド → リソース」）。"""

    def test_snapshot(self):
        import resources
        x = resources.snapshot()
        self.assertGreaterEqual(x["cpu"], 1)
        self.assertEqual(x["disk_total"], x["disk_used"] + x["disk_free"])   # マシン全体ではなく、使える分
        for k in ("mem_total", "mem_free", "disk_total", "disk_free", "peak"):
            self.assertIn(k, x)
            self.assertGreater(x[k], 0)
        self.assertLessEqual(x["mem_free"], x["mem_total"])

    def test_sizes(self):
        import resources
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "docs" / sitedir.SLUG / "emblems").mkdir(parents=True)
            (d / ".git").mkdir()
            (d / "docs" / "a.html").write_bytes(b"x" * 100)
            (d / "docs" / sitedir.SLUG / "emblems" / "b.webp").write_bytes(b"x" * 50)
            (d / ".git" / "big").write_bytes(b"x" * 1000)   # .git は数えない
            sz = resources.repo_sizes(d)
        self.assertEqual((sz["repo"], sz["pages"], sz["emblems"]), (150, 150, 50))

    def test_render(self):
        G = 1024 ** 3
        res = {"sizes": {"repo": 900 * 1024 ** 2, "pages": 100 * 1024 ** 2, "emblems": 5 * 1024 ** 2, "inbox": 1, "state": 1},
               "limits": {"repo": G, "pages": G},
               "runs": {"emblem": {"name": "小元素の自動補完", "when": "10/17 09:40", "secs": 2400, "workers": 4,
                                   "res": {"cpu": 4, "load": 3.1, "mem_total": 16 * G, "mem_free": 3 * G, "peak": 13 * G,
                                           "disk_used": 11 * G, "disk_total": 40 * G, "disk_free": 29 * G}}},
               "tokens": {"edit": {"name": "AI 編集", "last": 12345, "week": 50000, "runs": 4},
                          "collect": {"name": "<収集>", "last": None, "week": 0, "runs": 0}}}
        out = render._admin_resources(res)
        self.assertIn('class="mt warn"', out)   # リポジトリ 88% は赤
        self.assertEqual(out.count('class="mt warn"'), 2)   # メモリのピーク 81% も赤・ディスク 28% は赤にしない
        self.assertIn("<b>11.00 GB</b> / 40.00 GB", out)
        self.assertIn("40 分 0 秒", out)
        self.assertIn("4 本並列", out)
        self.assertIn("12,345", out)
        self.assertIn("未記録", out)
        self.assertIn("&lt;収集&gt;", out)
        self.assertIn("claude.ai/settings/usage", out)
        self.assertEqual(render._admin_resources(None), "")

    def test_runlog_cli_attaches_snapshot(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            code = ("import sys,pathlib;sys.path.insert(0,'scripts');import runlog;runlog.LOG_DIR=pathlib.Path(sys.argv[1]);"
                    "sys.argv=['runlog','emblem','テスト','--tokens','1234'];runlog.main()")
            subprocess.run([sys.executable, "-c", code, d], cwd=ROOT, check=True)
            row = runlog.load("emblem", pathlib.Path(d))[-1]
        self.assertEqual(row["tokens"], 1234)
        self.assertIn("mem_total", row["res"])


if __name__ == "__main__":
    unittest.main()


class CheckWhole(unittest.TestCase):
    """切り抜きの検査（emblem.check_whole）。rembg は使わず、透明度だけの絵で確かめる。"""

    def _img(self, box):
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (200, 240), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse(box, fill=(120, 90, 60, 255))
        return im

    def test_panel_crop_rejected(self):
        try:
            import cv2  # noqa: F401
        except ImportError:
            self.skipTest("opencv がない")
        import emblem
        with self.assertRaises(ValueError):   # 上の端の大半が人物：漫画のコマを枠ごと切ったもの（チャド）
            emblem.check_whole(self._img((10, -300, 190, 200)))
        emblem.check_whole(self._img((40, 20, 160, 239)))   # 余白のある胸像は通る


class FlatCut(unittest.TestCase):
    """形の健康（emblem.trim_flat・flat_flaw・emblem_fill.repair_flat）：左右・上の端の直線の切り口、凹みすぎ。透明度だけの絵で確かめる。"""

    def _bust(self, side_from, size=(200, 300)):
        # 頭の楕円＋体。体の左右は side_from の行から下が枠の端までまっすぐ（元の写真の端で腕が切れた形）。それより上は肩が斜め
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((70, 0, 130, 70), fill=(200, 80, 60, 255))
        d.polygon([(90, 60), (110, 60), (199, side_from - 30), (199, 299), (0, 299), (0, side_from - 30)], fill=(200, 80, 60, 255))
        return im

    def test_straight_sides_trimmed_to_half_body(self):
        import emblem
        im = self._bust(150)   # 切り口は 150 行から（高さの 50%）→ そこで下を切って半身
        self.assertTrue(emblem.flat_flaw(im))
        out = emblem.trim_flat(im)
        self.assertLess(out.height, 160)
        self.assertGreater(out.height, 100)
        self.assertFalse(emblem.flat_flaw(out))
        im = self._bust(290)   # 切り口が高さの 15% 以内（肩が枠に届くだけ）なら、そのまま
        self.assertEqual(emblem.trim_flat(im).size, im.size)
        self.assertFalse(emblem.flat_flaw(im))

    def test_too_early_cut_rejected(self):
        import emblem
        with self.assertRaisesRegex(ValueError, "左右の端に直線の切り口"):
            emblem.trim_flat(self._bust(60))   # 切り口が上のほう：切り落とすと残りが短すぎる
        with self.assertRaises(ValueError):
            emblem.check_whole(self._bust(60))   # 取るときは check_whole の左右の端（SIDE_MAX）が先に外す

    def test_flat_top_and_thin_staff(self):
        import emblem
        from PIL import Image, ImageDraw
        hat = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(hat).rectangle((40, 0, 160, 199), fill=(90, 60, 40, 255))   # 上の端を横幅の 60% 切った
        with self.assertRaisesRegex(ValueError, "上の端に直線の切り口"):
            emblem.trim_flat(hat)
        staff = Image.new("RGBA", (200, 200), (0, 0, 0, 0))   # 端にそった細い杖（幅 3px）は切り口ではない
        d = ImageDraw.Draw(staff)
        d.ellipse((50, 10, 150, 199), fill=(90, 60, 40, 255))
        d.rectangle((0, 20, 2, 190), fill=(90, 60, 40, 255))
        self.assertFalse(emblem.flat_runs(staff)["left"] > emblem.FLAT_RUN)

    def test_concave_shape_rejected(self):
        import emblem
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(im).polygon([(100, 0), (110, 100), (190, 190), (100, 120), (10, 190), (90, 100)], fill=(90, 60, 40, 255))   # 星のように凹んだ
        with self.assertRaisesRegex(ValueError, "凹みすぎ"):
            emblem.trim_flat(im)

    def test_repair_flat_rewrites_fixable_and_leaves_rest(self):
        import tempfile
        from unittest import mock
        im = self._bust(150)
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "emblems").mkdir()
        im.save(tmp / "emblems" / "a.webp")
        self._bust(60).save(tmp / "emblems" / "b.webp")
        item = {"name": "X", "emblem": [{"subject": "A", "image": "emblems/a.webp", "shape": "cutout"}, {"subject": "B", "image": "emblems/b.webp", "shape": "cutout"}]}
        written = []
        with mock.patch.object(ef.emblem.sitedir, "SITE_DIR", tmp), mock.patch.object(ef.emblem, "EMB_DIR", tmp / "emblems"), \
                mock.patch.object(ef.emblem, "write_item", side_effect=lambda n, e, t: written.append(e)):
            self.assertEqual(ef.repair_flat(item, log=lambda *_: None), 1)
            from PIL import Image
            self.assertLess(Image.open(tmp / "emblems" / "a.webp").height, 160)
            self.assertEqual(Image.open(tmp / "emblems" / "b.webp").height, 300)   # 直せないものは触らない
            self.assertEqual([x["subject"] for x in ef.broken_cuts(item)], ["B"])   # 直せなかった B だけ外れる
        self.assertEqual(len(written), 1)


class KeepFraming(unittest.TestCase):
    def test_follow_majority_without_losing_old(self):
        import emblem
        mk = lambda rows: [{"subject": c, "image": "https://x/" + c, "_framing": f} for c, f in rows]
        # 全身が多い：新しい胸像は外すが、前からある胸像（old）は残す
        ems = emblem.keep_framing(mk([("a", "full"), ("b", "full"), ("c", "bust"), ("d", "bust")][:4] + [("e", "full")]),
                                  old=["https://x/c"])
        self.assertEqual([x["subject"] for x in ems], ["a", "b", "c", "e"])
        # 胸像が多い：全身は捨てずに上半身に切る（枚数を減らさない）
        ems = emblem.keep_framing(mk([("a", "bust"), ("b", "bust"), ("c", "full")]))
        self.assertEqual([x["subject"] for x in ems], ["a", "b", "c"])
        self.assertTrue(ems[2]["upper"])
        # 全身が多い：切れば胸像になる全身の立ち絵は、切らずに全身のまま残す
        ems = emblem.keep_framing(mk([("a", "full"), ("b", "full"), ("c", "bust")]) + [
            {"subject": "d", "image": "https://x/d", "_framing": "bust", "_can_full": True}])
        self.assertEqual([x["subject"] for x in ems], ["a", "b", "d"])
        self.assertIs(ems[2]["upper"], False)


class EmblemDetail(unittest.TestCase):
    """管理ページ「小元素の探し方」：取り方の順・次の回・助言・図。"""

    def test_cutout_with_other_people_is_dropped(self):
        import emblem
        from PIL import Image
        from PIL import ImageDraw
        img = Image.new("RGBA", (200, 260), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((40, 30, 160, 259), fill=(200, 150, 120, 255))
        with mock.patch.object(emblem, "other_faces", return_value=1):
            with self.assertRaisesRegex(ValueError, "ほかの人"):
                emblem.check_whole(img, photo=True)
            emblem.check_whole(img, photo=False)   # 絵は数えない

    def test_video_frame_trims_bars_and_subtitles(self):
        import emblem
        from PIL import Image
        img = Image.new("RGB", (480, 360), (0, 0, 0))
        img.paste((180, 160, 140), (0, 45, 480, 315))   # 16:9 の動画（上下 45px の黒い帯）
        out = emblem.video_frame(img)
        self.assertEqual(out.size, (480, 270 - int(270 * emblem.SUBTITLE)))   # 黒い帯と下の字幕の帯を切る

    def test_youtube_titles_need_group_and_name(self):
        data = {"contents": [{"videoRenderer": {"videoId": "a1", "title": {"runs": [{"text": "OA travel vlog"}]}}},
                             {"videoRenderer": {"videoId": "b2", "title": {"runs": [{"text": "A2O LITE OA debut trailer"}]}}},
                             {"videoRenderer": {"videoId": "c3", "title": {"runs": [{"text": "[직캠] A2O LITE OA FanCam"}]}}}]}
        html = "<script>var ytInitialData = " + json.dumps(data) + ";</script>"
        self.assertEqual([v for v, _ in ef.parse_youtube(html)], ["a1", "b2", "c3"])
        with mock.patch.object(ef, "_get", return_value=html.encode()):
            rows = ef.youtube_images("A2O LITE", "OA")
        self.assertEqual([r["image"] for r in rows], ["https://i.ytimg.com/vi/c3/hq2.jpg", "https://i.ytimg.com/vi/c3/hq1.jpg", "https://i.ytimg.com/vi/c3/hq3.jpg", "https://i.ytimg.com/vi/b2/hq2.jpg", "https://i.ytimg.com/vi/b2/hq1.jpg", "https://i.ytimg.com/vi/b2/hq3.jpg"])   # 名前だけの動画は外す・직캠を先に
        self.assertEqual(ef.parse_youtube("<html></html>"), [])

    def test_source_chain_matches_gather(self):
        chain = [s for s, _ in ef.source_chain({"type": "event", "emblem_kind": "group"})]
        self.assertNotIn("Wikidata", chain)   # グループは Wikidata を使わない（gather は本人だけ）
        self.assertEqual(dict(ef.source_chain({"type": "game"}))["Fandom"], True)
        self.assertEqual(dict(ef.source_chain({"type": "game"}))["Wikipedia"], False)   # 絵のキャラは目視だけ
        self.assertEqual(dict(ef.source_chain({"type": "event"}))[ef.WEB], False)

    def test_detail_retry_and_advice(self):
        import datetime as dt
        import digest
        item = {"name": "G", "type": "event", "emblem_kind": "group", "emblem_who": ["a", "b", "c"]}
        failed = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat(timespec="seconds")
        d = digest.emblem_detail(item, {"tried": {"Wikipedia": 1, "Wikimedia Commons": 22}, "failed_at": failed, "at": failed,
                                        "note": "x"}, "failed", [], "Asia/Tokyo")
        self.assertTrue(d["todo"].endswith("以降に再挑戦") or "新しい記事" in d["todo"])
        self.assertIn("emblem_urls", d["advice"])   # Wiki に記事がないグループ → 公式の写真を
        self.assertEqual(d["why"], "メンバー 3 人")
        self.assertEqual([c["n"] for c in d["chain"]][:3], [None, 1, 22])
        brand = digest.emblem_detail({"name": "B", "type": "product"}, {"tried": {"Wikidata": 0}, "at": failed}, "failed", [], "Asia/Tokyo")
        self.assertIn("P154", brand["advice"])
        live = digest.emblem_detail({"name": "H", "type": "show", "emblem_kind": "character", "emblem_people": True},
                                    {"tried": {"役の記事": 36, "作品の動画の場面": 33}, "at": failed}, "failed", [], "Asia/Tokyo")
        self.assertEqual([(c["src"], c["n"]) for c in live["chain"]][1:3], [("役の記事", 36), ("作品の動画の場面", 33)])   # 試した取り方は全部出す（「まだ試していない」にならない）
        ok = digest.emblem_detail({"name": "K", "type": "game", "emblem": [{}] * 6}, {}, "ok", [], "Asia/Tokyo")
        self.assertEqual(ok["advice"], "")

    def test_flow_render(self):
        d = {"kind": "グループ", "why": "<m>", "target": 9, "have": 0, "lo": 3, "hi": 10, "faces": True, "rejects": 2,
             "chain": [{"src": "直接指定", "auto": True, "n": None}, {"src": "Wikipedia", "auto": True, "n": 0},
                       {"src": "Wikimedia Commons", "auto": True, "n": 22}, {"src": "Web 画像検索", "auto": False, "n": 8}],
             "funnel": {"found": 30, "usable": 4, "auto": 0, "review": 4}, "note": "n", "at": "10/17", "todo": "次", "advice": "a"}
        out = render._emblem_flow(d, "failed")
        self.assertIn("ef-st-failed", out)
        self.assertIn('class="ef-na"', out)
        self.assertIn('class="ef-zero"', out)
        self.assertIn('class="ef-got"', out)
        self.assertIn("ef-eye", out)   # Web は目視だけ
        self.assertIn("SFace", out)
        self.assertIn("目で外した 2 枚", out)
        self.assertIn("集めた <b>30</b>", out)
        self.assertIn("&lt;m&gt;", out)
        self.assertNotIn("<m>", out)


class Ladder(unittest.TestCase):
    """取り方の段：① 標準 → ② 名前を広げる → ③ 公式・記事のページ を、届くまで同じ回の中で上がる。"""

    def setUp(self):
        self.saved = {k: getattr(ef, k) for k in ("gather", "gather_wide", "gather_pages", "check", "auto_pick", "commit", "load_items", "_live", "subjects")}
        self.items = [{"name": "X", "type": "game", "emblem_who": ["a", "b"], "emblem": []}]
        ef.load_items = lambda: self.items
        ef._live = lambda *a, **k: None
        ef.check = lambda cands, log, **k: cands
        ef.auto_pick = lambda item, good, **k: list(range(1, len(good) + 1))

        def commit(item, good, picks, log=print):
            self.items[0]["emblem"] = self.items[0]["emblem"] + [{"subject": good[n - 1]["subject"], "image": good[n - 1]["image"]} for n in picks]
        ef.commit = commit
        self.calls = []

        def make(label, rows):
            def fn(item, log, tried):
                self.calls.append(label)
                tried[label] = len(rows)
                return [{"subject": s, "image": f"{label}-{s}", "source": "Fandom"} for s in rows]
            return fn
        ef.gather, ef.gather_wide, ef.gather_pages = make("1", ["a"]), make("2", ["b"]), make("3", [])

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(ef, k, v)

    def test_climbs_until_ok(self):
        r = ef.fill_one(self.items[0], log=lambda m: None)
        self.assertEqual(self.calls, ["1", "2"])   # ②で目標（2 人）に届いたので ③ は試さない
        self.assertEqual(r["state"], "ok")
        self.assertEqual([x["added"] for x in r["steps"]], [1, 1])

    def test_failed_names_people_without_image(self):
        ef.gather_wide = lambda item, log, tried: []   # b には候補が 1 つもない
        r = ef.fill_one(self.items[0], log=lambda m: None)
        self.assertEqual(r["state"], "failed")
        self.assertEqual(r["funnel"]["rejected"].get("画像のない人"), 1)
        self.assertIn("全員が画像のない人", r["note"])

    def test_not_exhausted_while_roster_has_untried_people(self):
        """試した人が全員画像なしでも、名簿にまだ試していない人がいるなら exhausted にしない（24 時間待ちにしない）。"""
        ef.gather = ef.gather_wide = lambda item, log, tried: []
        self.items[0]["emblem_who"] = ["a", "b"] + [f"z{i}" for i in range(ef.STEP + 3)]
        ef.subjects = lambda item, kind, hi: ["a", "b"]
        r = ef.fill_one(self.items[0], log=lambda m: None)
        self.assertFalse(r.get("exhausted"))
        self.assertNotIn("全員が画像のない人", r["note"])

    def test_unnamed_unsure_candidate_is_no_image(self):
        ef.gather_wide = lambda item, log, tried: [{"subject": "b", "image": "https://x/Che_Guevara.jpg", "source": "Wikipedia"}]
        ef.auto_pick = lambda item, good, **k: [1] if good and good[0]["subject"] == "a" else []
        r = ef.fill_one(self.items[0], log=lambda m: None)
        self.assertEqual(r["funnel"]["rejected"].get("画像のない人"), 1)
        self.assertEqual(r["funnel"]["rejected"].get("名前の合わない候補"), 1)
        self.assertIn("全員が画像のない人", r["note"])

    def test_named_in(self):
        self.assertTrue(ef._named_in({"subject": "Phil (GTA VI)", "image": "https://x/Phil-GTAVI-Portrait.png?a=1"}))
        self.assertFalse(ef._named_in({"subject": "Phil (GTA VI)", "image": "https://x/GTAVI_Merch_PromoCard.jpg"}))
        self.assertFalse(ef._named_in({"subject": "Ernesto", "image": "https://x/Che_Guevara_June_2%2C_1959.jpg"}))

    def test_all_steps_then_failed_with_material(self):
        ef.gather_wide = lambda item, log, tried: self.calls.append("2") or []
        r = ef.fill_one(self.items[0], log=lambda m: None)
        self.assertEqual(self.calls, ["1", "2", "3"])
        self.assertEqual(r["state"], "failed")
        self.assertTrue(r["material"])
        self.assertIn("新しい記事が来たらすぐ", r["note"])


class GateWhy(unittest.TestCase):
    def test_waiting_is_not_silent(self):
        import gate
        self.assertEqual(gate._emblem_why([], []), "全部そろっている")
        why = gate._emblem_why(["a"], [("b", "2026-10-17T08:00:00+00:00")])
        self.assertIn("足りない 1 版面", why)
        self.assertIn("失敗 1 版面は再挑戦待ち", why)
        self.assertIn("17:00", why)   # 日本時間


class Gate(unittest.TestCase):
    """後台のゲート：仕事があるか・AI が要るかをプログラムだけで決める（scripts/gate.py）。"""

    def setUp(self):
        import tempfile
        import gate
        self.gate = gate
        self.dir = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.dir.name)
        self.state = self.d / "gate.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_edit_work(self):
        (self.d / "2026-10-17.json").write_text(json.dumps({"items": [{"name": "A", "entries": [{}] * 3},
                                                                  {"name": "B", "entries": [{}] * 2}]}), encoding="utf-8")
        self.assertEqual(self.gate.edit_work(self.d, today="2026-10-17"), {"A": 3, "B": 2})   # edit.json なし = 全部未編集
        (self.d / "2026-10-17.edit.json").write_text(json.dumps({"_covered": {"A": 3, "B": 1}}), encoding="utf-8")
        self.assertEqual(self.gate.edit_work(self.d, today="2026-10-17"), {"B": 1})
        self.assertEqual(self.gate.edit_work(self.d, today="2026-10-18"), {})   # 今日の inbox がない

    def test_photo_work(self):
        (self.d / "photos").mkdir()
        (self.d / "photos" / "7.json").write_text("{}", encoding="utf-8")
        (self.d / "photos" / "7.jpg").write_bytes(b"x")
        self.assertEqual(self.gate.photo_work(self.d), ["7"])

    def _noon(self):
        return mock.patch.object(self.gate, "_now", lambda: dt.datetime(2026, 10, 22, 3, 0, tzinfo=dt.timezone.utc))

    def test_fire_only_with_work_token_and_new_sig(self):
        self._noon().start()
        self.addCleanup(mock.patch.stopall)
        calls = []
        post = lambda url, token: calls.append((url, token)) or (200, '{"claude_code_session_id": "session_x"}')
        self.gate.save({"jobs": {"edit": {"need": True, "sig": "s1", "prog": 0}, "photos": {"need": False, "sig": "p"}}}, self.state)
        res = self.gate.fire(self.state, post=post, env={})
        self.assertEqual(res["edit"], "トークン未設定（定時を待つ）")
        self.assertEqual(res["photos"], "仕事なし（起こさない）")
        self.assertEqual(calls, [])
        res = self.gate.fire(self.state, post=post, env={"ROUTINE_TOKEN_EDIT": "t"})
        self.assertEqual(res["edit"], "Claude を起こした")
        self.assertIn("trig_01Ly92RcW35cBwZ9amWZr11j", calls[0][0])
        fired = self.gate.load(self.state)["jobs"]["edit"]["fired"]
        self.assertEqual((fired["attempts"], fired["resp"]), (1, "session_x"))   # 返事の id を記録する
        res = self.gate.fire(self.state, post=post, env={"ROUTINE_TOKEN_EDIT": "t"})
        self.assertIn("分以内に起こし済み", res["edit"])   # 直後は編集中のはず：重ねて起こさない
        self.assertEqual(len(calls), 1)

    def _aged(self, minutes, **job):
        """edit を minutes 分前に起こした状態にする。"""
        at = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")
        today = self.gate.day_of(dt.datetime.now(dt.timezone.utc))   # 同じ日として数える（北京時間の 0 時をまたいで走っても揺れない）
        fired = {"at": at, "day": today, "sig": "s1", "prog": 10, "attempts": job.pop("attempts", 1)}
        self.gate.save({"jobs": {"edit": {"need": True, "sig": "s1", "prog": job.pop("prog", 10), "prog_day": today, **job,
                                          "fired": fired}}}, self.state)

    def test_stalled_fire_is_retried_then_gives_up(self):
        """起こしたのに編集済みの数が増えない（Claude が動いていない）→ 60 分あとに起こし直す。3 回で止め、6 時間待つ。"""
        calls = []
        post = lambda url, token: calls.append(url) or 200
        env = {"ROUTINE_TOKEN_EDIT": "t"}
        self._aged(70)
        self.assertEqual(self.gate.work_state(self.gate.load(self.state)["jobs"]["edit"])[0], "stalled")
        self.assertIn("2 回目", self.gate.fire(self.state, post=post, env=env)["edit"])
        self.assertEqual(self.gate.load(self.state)["jobs"]["edit"]["fired"]["attempts"], 2)
        self._aged(70, attempts=3)
        self.assertEqual(self.gate.work_state(self.gate.load(self.state)["jobs"]["edit"])[0], "gave_up")
        self.assertIn("停滞", self.gate.fire(self.state, post=post, env=env)["edit"])
        self.assertEqual(len(calls), 1)   # 3 回目まで叫んだあとは叫ばない
        self._aged(60 * self.gate.REFIRE_HOURS + 5, attempts=3)
        self.assertEqual(self.gate.fire(self.state, post=post, env=env)["edit"], "Claude を起こした")   # 6 時間たったら 1 回目から

    def test_progress_is_not_stall(self):
        """編集済みの数が増えていれば動いている：新着が来て仕事の量が同じでも停滞とは言わない。"""
        self._aged(30, prog=25)
        self.assertEqual(self.gate.work_state(self.gate.load(self.state)["jobs"]["edit"])[0], "progress")
        self._aged(30)
        self.assertEqual(self.gate.work_state(self.gate.load(self.state)["jobs"]["edit"])[0], "running")

    def _at(self, fired_jst, prog_now=25, attempts=1):
        """edit を日本時間 fired_jst（'2026-10-19 09:05'）に起こした状態にする。"""
        jst = zoneinfo.ZoneInfo("Asia/Tokyo")
        at = dt.datetime.strptime(fired_jst, "%Y-%m-%d %H:%M").replace(tzinfo=jst).astimezone(dt.timezone.utc).isoformat()
        self.gate.save({"jobs": {"edit": {"need": True, "items": ["A"], "sig": "s1", "prog": prog_now,
                                          "fired": {"at": at, "sig": "s1", "prog": 10, "attempts": attempts}}}}, self.state)

    def _fire_at(self, now_jst, calls, env=None):
        jst = zoneinfo.ZoneInfo("Asia/Tokyo")
        now = dt.datetime.strptime(now_jst, "%Y-%m-%d %H:%M").replace(tzinfo=jst).astimezone(dt.timezone.utc)
        with mock.patch.object(self.gate, "_now", lambda: now):
            return self.gate.fire(self.state, post=lambda u, t: calls.append(u) or 200,
                                  env=env or {"ROUTINE_TOKEN_EDIT": "t"})["edit"]

    def test_twice_a_day_at_9_and_18(self):
        """AI 編集は日本時間 9:00 と 18:00 の 1 日 2 回。その回にもう起こしていれば、整理待ちが残っていても次の回まで待つ。"""
        calls = []
        self._at("2026-10-19 09:05")   # 9:00 の回で起こして、動いた（prog 10 → 25）
        self.assertIn("次は 18:00", self._fire_at("2026-10-19 13:00", calls))
        self.assertEqual(calls, [])
        self.assertEqual(self._fire_at("2026-10-19 18:17", calls), "Claude を起こした")   # 18:00 の回
        self._at("2026-10-19 18:17")
        self.assertIn("次は 09:00", self._fire_at("2026-10-19 23:47", calls))   # 夜のうちは起こさない
        self.assertEqual(self._fire_at("2026-10-20 09:00", calls), "Claude を起こした")
        self.assertEqual(len(calls), 2)

    def test_button_fires_any_time(self):
        calls = []
        self._at("2026-10-19 09:05")
        self.assertEqual(self._fire_at("2026-10-19 13:00", calls, {"ROUTINE_TOKEN_EDIT": "t", "GATE_FORCE": "edit"}), "Claude を起こした")

    def test_pause_blocks_schedule_but_not_button(self):
        """管理ページで一時停止中は 9:00 / 18:00 でも起こさない。ボタン（GATE_FORCE）は起こす（整理待ちがなくても：やり直しのため）。"""
        calls = []
        self.gate.save({"jobs": {"edit": {"need": True, "items": ["A"], "sig": "s1", "prog": 0}}}, self.state)
        self.assertIn("一時停止中", self._fire_at("2026-10-20 09:00", calls, {"ROUTINE_TOKEN_EDIT": "t", "EDIT_MODE": "pause"}))
        self.gate.save({"jobs": {"edit": {"need": False, "items": [], "sig": "s1", "prog": 0}}}, self.state)
        self.assertEqual(self._fire_at("2026-10-20 09:00", calls, {"ROUTINE_TOKEN_EDIT": "t", "EDIT_MODE": "pause", "GATE_FORCE": "edit"}),
                         "Claude を起こした")
        self.assertEqual(len(calls), 1)

    def test_slots(self):
        jst = zoneinfo.ZoneInfo("Asia/Tokyo")
        now = dt.datetime(2026, 10, 19, 13, 0, tzinfo=jst)
        self.assertEqual(self.gate.last_slot("edit", now).astimezone(jst).hour, 9)
        self.assertEqual(self.gate.next_slot("edit", now).astimezone(jst).hour, 18)
        now = dt.datetime(2026, 10, 19, 7, 0, tzinfo=jst)   # 朝 7 時：最近の回は前日の 18:00
        self.assertEqual(self.gate.last_slot("edit", now).astimezone(jst).day, 18)
        self.assertIsNone(self.gate.last_slot("photos", now))

    def test_force_skips_gap_and_switch(self):
        calls = []
        post = lambda url, token: calls.append(url) or 200
        self._aged(5)   # 5 分前に起こしたばかり + GATE_FIRE=0 でも、管理ページのボタン（GATE_FORCE）は起こす
        res = self.gate.fire(self.state, post=post, env={"GATE_FIRE": "0", "GATE_FORCE": "edit", "ROUTINE_TOKEN_EDIT": "t"})
        self.assertEqual(res["edit"], "Claude を起こした")
        self.assertTrue(self.gate.load(self.state)["jobs"]["edit"]["fired"]["forced"])

    def test_edit_done_counts_covered(self):
        (self.d / "2026-10-17.edit.json").write_text(json.dumps({"_covered": {"A": 3, "B": 2}}), encoding="utf-8")
        self.assertEqual(self.gate.edit_done(self.d, today="2026-10-17"), 5)
        self.assertEqual(self.gate.edit_done(self.d, today="2026-10-18"), 0)

    def test_gate_fire_switch(self):
        self.assertEqual(self.gate.enabled_jobs(""), set())
        self.assertEqual(self.gate.enabled_jobs("0"), set())
        self.assertEqual(self.gate.enabled_jobs("1"), {"edit", "photos"})
        self.assertEqual(self.gate.enabled_jobs("all"), {"edit", "photos"})
        self.assertEqual(self.gate.enabled_jobs(" Edit "), {"edit"})
        self.assertEqual(self.gate.enabled_jobs("edit,photos,bogus"), {"edit", "photos"})
        self._noon().start()
        self.addCleanup(mock.patch.stopall)
        calls = []
        post = lambda url, token: calls.append(url) or 200
        self.gate.save({"jobs": {"edit": {"need": True, "sig": "s1"}, "photos": {"need": True, "sig": "p1"}}}, self.state)
        env = {"GATE_FIRE": "edit", "ROUTINE_TOKEN_EDIT": "t", "ROUTINE_TOKEN_PHOTOS": "t"}
        res = self.gate.fire(self.state, post=post, env=env)
        self.assertEqual(res["edit"], "Claude を起こした")   # AI 編集だけ起こす
        self.assertIn("GATE_FIRE で止めている", res["photos"])
        self.assertEqual(len(calls), 1)

    def test_unedited_inbox_means_edit_work(self):
        """版面には AI 編集済みの記事しか載らない：今日の inbox に未整理（_covered より後・edit.json にない版面）があれば AI 編集の仕事。"""
        (self.d / "2026-10-17.json").write_text(json.dumps({"items": [{"name": "新作", "entries": [{}] * 2},
                                                                  {"name": "A", "entries": [{}] * 4}]}), encoding="utf-8")
        (self.d / "2026-10-17.edit.json").write_text(json.dumps({"A": [], "_covered": {"A": 4}}), encoding="utf-8")
        self.assertEqual(self.gate.edit_work(self.d, today="2026-10-17"), {"新作": 2})

    # 2026-10-19〜21 の本物の誤起動（state/gate.json の履歴）：前の日の fired.prog と、日付が変わって 0 に戻った今日の prog を比べて「停滞」と判断し、
    # 定時（9:00 / 18:00）の確認を素通りして夜中（日本時間 1〜2 時）に AI 編集を起こしていた
    NIGHT_MISFIRES = [
        ({"at": "2026-10-19T14:29:20+00:00", "attempts": 1, "forced": True, "prog": 0}, "2026-10-19T16:17:43+00:00"),
        ({"at": "2026-10-20T09:17:20+00:00", "attempts": 1, "prog": 151}, "2026-10-20T17:09:11+00:00"),
        ({"at": "2026-10-21T10:57:16+00:00", "attempts": 1, "prog": 434}, "2026-10-21T16:40:49+00:00"),
    ]

    def test_new_day_is_not_stall(self):
        """日付（北京時間）が変わると編集済みは 0 から数え直す：昨日起こした記録は停滞と数えず、定時でなければ起こさない。"""
        for fired, now in self.NIGHT_MISFIRES:
            with self.subTest(now=now):
                now = dt.datetime.fromisoformat(now)
                j = {"need": True, "items": ["A"], "sig": "s1", "prog": 0, "fired": dict(fired)}   # day のない古い記録
                self.assertEqual(self.gate.work_state(j, now)[0], "none")
                self.gate.save({"jobs": {"edit": j}}, self.state)
                calls = []
                with mock.patch.object(self.gate, "_now", lambda: now):
                    res = self.gate.fire(self.state, post=lambda u, t: calls.append(u) or 200, env={"ROUTINE_TOKEN_EDIT": "t"})
                self.assertIn("次は 09:00", res["edit"])
                self.assertEqual(calls, [])
        # 朝 9:00 の回では 1 回目として起こす
        self.assertEqual(self._fire_at("2026-10-22 09:00", calls := []), "Claude を起こした")
        self.assertEqual(self.gate.load(self.state)["jobs"]["edit"]["fired"]["attempts"], 1)

    def test_fired_records_day_and_same_day_stall_still_retries(self):
        """起こした記録に日付（prog と同じ北京時間の今日）を残す。同じ日のうちの停滞は今までどおり起こし直す。"""
        self.gate.save({"jobs": {"edit": {"need": True, "items": ["A"], "sig": "s1", "prog": 5, "prog_day": "2026-10-22"}}}, self.state)
        self.assertEqual(self._fire_at("2026-10-22 09:00", calls := []), "Claude を起こした")
        fired = self.gate.load(self.state)["jobs"]["edit"]["fired"]
        self.assertEqual(fired["day"], "2026-10-22")
        self.assertIn("2 回目", self._fire_at("2026-10-22 10:30", calls))   # 90 分たっても 5 のまま：停滞

    def test_photos_do_not_reset_by_day(self):
        """写真の prog は残りの枚数（日付で 0 に戻らない）：日付が変わっても停滞は停滞。"""
        j = {"need": True, "items": ["7"], "prog": -1, "fired": {"at": "2026-10-21T10:57:16+00:00", "prog": -1, "attempts": 1}}
        self.assertEqual(self.gate.work_state(j, dt.datetime(2026, 10, 21, 16, 40, tzinfo=dt.timezone.utc), job="photos")[0], "stalled")

    def test_running_label_only_near_last_batch(self):
        """「動いている」は最後のバッチ（state/log/edit.json の出刊）から 30 分以内だけ。過ぎたら前回の時刻と次の定時。"""
        utc = dt.timezone.utc
        j = {"need": True, "items": ["A"], "prog": 510, "prog_day": "2026-10-22",
             "fired": {"at": "2026-10-22T00:08:31+00:00", "day": "2026-10-22", "prog": 60, "attempts": 1}}
        lb = "2026-10-22T01:32:56+00:00"
        self.assertEqual(self.gate.work_state(j, dt.datetime(2026, 10, 22, 1, 50, tzinfo=utc), last_batch=lb)[0], "progress")
        st, why = self.gate.work_state(j, dt.datetime(2026, 10, 22, 8, 50, tzinfo=utc), last_batch=lb)
        self.assertEqual(st, "idle")
        self.assertEqual(why, "前回 10:32（日本時間）に終わった・次は 18:00")   # 時刻だけ。「あと N 分」は書かない（網页で固まる。列の見出し・カードが端末で数える）
        # 18:00 の回をまだ起こしていない（cron の遅れ・次のゲート待ち）：次の日の 9:00 ではなく、今の回がまもなく
        st, why = self.gate.work_state(j, dt.datetime(2026, 10, 22, 9, 7, tzinfo=utc), last_batch=lb)
        self.assertEqual((st, why), ("idle", "前回 10:32（日本時間）に終わった・18:00 の回はまもなく（次のゲートで起こす）"))
        self.assertEqual(self.gate.due_slot(j, dt.datetime(2026, 10, 22, 9, 7, tzinfo=utc), last_batch=lb), "18:00")   # 列の見出しも今の回
        self.assertEqual(self.gate.due_slot(j, dt.datetime(2026, 10, 22, 8, 50, tzinfo=utc), last_batch=lb), "")       # 9:00 の回は済み
        self.assertEqual(self.gate.due_slot(j, dt.datetime(2026, 10, 22, 16, 47, tzinfo=utc), last_batch=lb), "")      # 北京 0 時すぎ：前の日の回は拾わない
        # 起こすかの規則は progress と同じ：この回（9:00）はもう起こした → 18:00 を待つ
        self.gate.save({"jobs": {"edit": {**j, "last_batch": lb}}}, self.state)
        self.assertIn("次は 18:00", self._fire_at("2026-10-22 17:50", calls := []))
        self.assertEqual(self._fire_at("2026-10-22 18:00", calls), "Claude を起こした")

    def test_progress_without_batch_since_firing_is_not_idle(self):
        """起こしたあと編集済みは増えた（510 → 521）が、出刊の行がまだない・失敗した（2026-10-22 18:18 JST の本物）：
        最後のバッチは今朝のもの（01:32Z）なので「前回 10:32 に終わった」とは言わない。60 分までは progress、過ぎたら unpublished。"""
        utc = dt.timezone.utc
        j = {"need": True, "items": ["A"], "prog": 521, "prog_day": "2026-10-22",
             "fired": {"at": "2026-10-22T09:18:11+00:00", "day": "2026-10-22", "prog": 510, "attempts": 1}}
        lb = "2026-10-22T01:32:56+00:00"
        err = {"at": "2026-10-22T09:25:20+00:00", "text": "出刊に失敗：No module named 'requests'"}
        for m in (30, 45):
            st, why = self.gate.work_state(j, dt.datetime(2026, 10, 22, 9, m, tzinfo=utc), last_batch=lb, last_error=err)
            self.assertEqual(st, "progress")
            self.assertNotIn("終わった", why)
        st, why = self.gate.work_state(j, dt.datetime(2026, 10, 22, 10, 30, tzinfo=utc), last_batch=lb, last_error=err)
        self.assertEqual(st, "unpublished")
        self.assertIn("18:18（日本時間）に起こして編集済みは 510 → 521 件に進んだが、そのあと出刊の記録がない", why)
        self.assertIn("No module named", why)
        # 起こす前の失敗は理由に出さない
        st, why = self.gate.work_state(j, dt.datetime(2026, 10, 22, 10, 30, tzinfo=utc), last_batch=lb,
                                       last_error={"at": "2026-10-22T05:00:00+00:00", "text": "古い失敗"})
        self.assertNotIn("古い失敗", why)
        # 今回起こしたあとのバッチがあれば、今までどおり 30 分で idle
        st, why = self.gate.work_state(j, dt.datetime(2026, 10, 22, 10, 30, tzinfo=utc), last_batch="2026-10-22T09:40:00+00:00")
        self.assertEqual((st, why), ("idle", "前回 18:40（日本時間）に終わった・次は 09:00"))
        # 起こすかの規則は progress と同じ：起こして 60 分以内は待つ、この回（18:00）はもう起こした → 次は 9:00
        self.gate.save({"jobs": {"edit": {**j, "last_batch": lb, "last_error": err}}}, self.state)
        self.assertIn("分以内に起こし済み", self._fire_at("2026-10-22 19:00", calls := []))
        self.assertIn("次は 09:00", self._fire_at("2026-10-22 19:40", calls))
        self.assertEqual(calls, [])

    def test_previous_days_slot_is_not_picked_up_after_midnight(self):
        """18:00 の回に仕事がなかった日：北京時間 0 時すぎ（持ち越しで整理待ちができる）に、前の日の 18:00 の回を拾い直して起こさない。次は 9:00。"""
        utc = dt.timezone.utc
        j = {"need": True, "items": ["A"], "prog": 0, "prog_day": "2026-10-23", "fired": {"at": "2026-10-22T00:08:31+00:00", "prog": 60, "attempts": 1}}
        self.gate.save({"jobs": {"edit": j}}, self.state)
        calls = []
        with mock.patch.object(self.gate, "_now", lambda: dt.datetime(2026, 10, 22, 16, 47, tzinfo=utc)):
            self.assertIn("次は 09:00", self.gate.fire(self.state, post=lambda u, t: calls.append(u) or 200, env={"ROUTINE_TOKEN_EDIT": "t"})["edit"])
        self.assertEqual(calls, [])
        self.assertEqual(self._fire_at("2026-10-23 09:00", calls), "Claude を起こした")
        # 同じ北京時間の日のうちなら、遅れた 18:00 の回は今までどおり拾う（JST 20:47 = 北京 19:47）
        self.gate.save({"jobs": {"edit": {**j, "prog": 100, "prog_day": "2026-10-22"}}}, self.state)   # 9:00 の回で 60 → 100 に進んだ
        self.assertEqual(self._fire_at("2026-10-22 20:47", calls), "Claude を起こした")

    def test_last_batch_reads_edit_log(self):
        log = self.d / "log"
        log.mkdir()
        (log / "edit.json").write_text(json.dumps([{"at": "2026-10-22T01:29:27+00:00", "batch": 23},
                                                   {"at": "2026-10-22T01:32:56+00:00", "batch": 24},
                                                   {"at": "2026-10-22T02:00:00+00:00", "text": "一時停止で止めた"}]), encoding="utf-8")
        self.assertEqual(self.gate.last_batch(log), "2026-10-22T01:32:56+00:00")   # 出刊していない行は「進んだ」に数えない
        self.assertEqual(self.gate.last_batch(self.d / "none"), "")

    def test_log_counts_retry_as_woke(self):
        """「Claude を起こした（2 回目…）」もログでは「起こした」（前は完全一致で「起こさなかった」と書いていた）。"""
        res = {"edit": "Claude を起こした（2 回目：前は動かなかった）", "photos": "仕事なし（起こさない）"}
        with mock.patch.object(self.gate, "fire", return_value=res), mock.patch.object(self.gate.runlog, "add") as add, \
                mock.patch.object(sys, "argv", ["gate.py", "fire"]), mock.patch("builtins.print"):
            self.gate.main()
        self.assertEqual(add.call_args.args[1], "Claude を起こした：AI 編集")
        self.assertEqual(add.call_args.args[2], "ok")

    def test_fire_failure_is_recorded(self):
        def post(url, token):
            raise RuntimeError("403")
        self.gate.save({"jobs": {"edit": {"need": True, "sig": "s1"}}}, self.state)
        with self._noon():
            self.assertTrue(self.gate.fire(self.state, post=post, env={"ROUTINE_TOKEN_EDIT": "t"})["edit"].startswith("起こせなかった"))


class CutRules(unittest.TestCase):
    """前は Claude が目で見ていた判断を、数で決める規則。"""

    def test_photo_problem(self):
        self.assertEqual(face_id.photo_problem({"faces": 0}), "顔なし")
        self.assertEqual(face_id.photo_problem({"faces": 1, "ratio": 0.05, "second": 0}), "遠景")
        self.assertEqual(face_id.photo_problem({"faces": 2, "ratio": 0.3, "second": 0.8}), "何人も写っている")
        self.assertIsNone(face_id.photo_problem({"faces": 2, "ratio": 0.3, "second": 0.2}))   # 後ろに小さく写っているのはよい

    def test_strict_identity(self):
        old = (face_id.engine, face_id.similarity)
        face_id.engine = lambda: ("det", "rec")
        face_id.similarity = lambda a, b: 1.0 if a == b else 0.0
        try:
            self.assertEqual(face_id.same_person([5], None, strict=True), set())   # 基準なしで 1 枚 = 本人と言えない
            self.assertEqual(face_id.same_person([5, 5], None, strict=True), {0, 1})
            self.assertEqual(face_id.same_person([5], None), {0})   # 手動のときは前のまま
            self.assertEqual(face_id.same_person([5], 0, strict=True), {0})   # 記事の代表画像（基準）だけ = 本人（前は「別人」にしていた）
            self.assertEqual(face_id.same_person([5, 7], 0, strict=True), {0})   # 基準と違う顔は落とす
        finally:
            face_id.engine, face_id.similarity = old

    def test_hole_share(self):
        import emblem
        import numpy as np
        solid = np.zeros((100, 100), bool)
        solid[20:100, 20:80] = True
        self.assertEqual(emblem.hole_share(solid), 0.0)
        solid[70:100, 40:60] = False   # 服の下の方が抜けた（下の端につながる穴）
        self.assertGreater(emblem.hole_share(solid), emblem.HOLE_MAX)


class JudgeTable(unittest.TestCase):
    """判断の一覧（emblem_rules.py）が 1 つだけの元：コードが落とす理由は全部そこにあり、流れの図の手順は全部 AI かルールの札を持つ。"""

    def test_every_drop_reason_is_listed(self):
        import re
        import emblem_rules
        listed = emblem_rules.reasons()
        src = (ROOT / "scripts" / "emblem.py").read_text(encoding="utf-8")
        body = src[src.index("def check_whole("):src.index("_SESSIONS = {}")]
        raised = {re.split(r"[（{]", m)[0] for m in re.findall(r'raise ValueError\(f?"([^"]+)"', body)}
        fid = (ROOT / "scripts" / "face_id.py").read_text(encoding="utf-8")
        body = fid[fid.index("def photo_problem("):fid.index("def main_face(")]
        raised |= set(re.findall(r'return "([^"]+)"', body))
        fill = (ROOT / "scripts" / "emblem_fill.py").read_text(encoding="utf-8")
        raised |= set(re.findall(r'drop\("([^"]+)"', fill)) | set(re.findall(r'why = "([^"]+)"', fill))
        raised |= set(re.findall(r'reasons\["([^"]+)"\]', fill)) - {"切り抜きの検査"}   # 切り抜きの検査は ⑥ の各行の合計
        self.assertFalse(raised - listed, "emblem_rules.py に書いていない落とす理由")

    def test_numbers_come_from_code(self):
        import emblem
        import emblem_rules
        text = " ".join(r["rule"] for r in emblem_rules.rules())
        self.assertIn(f"{emblem.TOP_MAX:.0%}", text)
        self.assertIn(str(face_id.THRESHOLD), text)
        self.assertIn(f"天井：キャラ・グループ {ef.CEIL['character']}", text)
        self.assertTrue(all(r["by"] in processes.BY for r in emblem_rules.rules()))
        self.assertTrue(all(r["stage"] in emblem_rules.STAGES for r in emblem_rules.rules()))

    def test_every_step_says_ai_or_rule(self):
        for p in processes.PROCESSES:
            for n in p["flow"]:
                by = processes.judged_by(n)
                if n["kind"] == "store":
                    self.assertIsNone(by)
                    continue
                self.assertIn(by, processes.BY, (p["id"], n["id"]))
                if by == "ai":   # AI の手順は Claude を使う（札）か、by: ai と書いてある
                    self.assertTrue(n.get("by") == "ai" or {"claude", "claude-api"} & set(n.get("uses", [])), (p["id"], n["id"]))
        cron = next(p for p in processes.PROCESSES if p["id"] == "emblem-cron")
        self.assertEqual(processes.by_count(cron)["ai"], 0)   # 自動補完は AI を使わない
        html = processes.render()
        self.assertIn('class="by by-ai"', html)
        self.assertIn("dn-by-ai", html)
        self.assertIn("判断の一覧", html)

    def test_examples_are_real_and_linked(self):
        import emblem_rules
        titles = {r["title"] for r in emblem_rules.rules()}
        for x in emblem_rules.EXAMPLES:
            self.assertIn(x["rule"], titles, x)   # 例は一覧の判断にひもづく
            for f, _ in x["before"] + x["after"]:
                self.assertTrue((ROOT / "docs" / sitedir.SLUG / f"{emblem_rules.EX}{f}.webp").exists(), f)
        html = processes.examples_panel()
        self.assertEqual(html.count('<article class="ex '), len(emblem_rules.EXAMPLES))
        self.assertIn("外す", html)


class Framing(unittest.TestCase):
    """全身か胸像か・全身の背の高さ・ロゴ・カードの比率（emblem.want_full / body_marks / clear_flat_bg、render._body_len）。"""

    def test_want_full_order(self):
        import emblem
        from unittest import mock
        with mock.patch.object(emblem, "official_render", return_value=True):
            self.assertTrue(emblem.want_full({}, drawn=True))                       # 絵のキャラの公式の立ち絵 → 全身
            self.assertFalse(emblem.want_full({}, drawn=False))                     # 写真 → 胸像
            self.assertFalse(emblem.want_full({}, drawn=True, item_framing="bust"))  # 版面の指定が先
            self.assertTrue(emblem.want_full({"framing": "full"}, drawn=False, item_framing="bust"))   # 1 枚の指定がいちばん先
        with mock.patch.object(emblem, "official_render", return_value=False):
            self.assertFalse(emblem.want_full({}, drawn=True))                      # 背景から切り抜いた絵 → 胸像

    def _figure(self, tail=False, base=False):
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (200, 400), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((80, 10, 120, 60), fill=(200, 160, 120, 255))     # 頭
        d.rectangle((75, 60, 125, 220), fill=(40, 40, 120, 255))    # 胴
        d.rectangle((80, 220, 96, 340), fill=(40, 40, 40, 255))     # 脚
        d.rectangle((104, 220, 120, 340), fill=(40, 40, 40, 255))
        if tail:   # 足より下まで垂れた尻尾（横の離れたところ）
            d.rectangle((10, 200, 30, 395), fill=(90, 90, 90, 255))
            d.rectangle((30, 200, 75, 215), fill=(90, 90, 90, 255))
        if base:   # 金の台座
            d.ellipse((0, 340, 200, 398), fill=(200, 160, 40, 255))
        return im

    def test_body_marks_ignore_tail_and_pedestal(self):
        import emblem
        from unittest import mock
        with mock.patch.object(emblem, "_pose_model", return_value=None):   # 姿勢モデルなし：輪郭から
            plain = emblem.body_marks(self._figure())
            tail = emblem.body_marks(self._figure(tail=True))
            base = emblem.body_marks(self._figure(base=True))
        self.assertAlmostEqual(plain[1], 340 / 400, delta=0.01)
        self.assertAlmostEqual(tail[1], 340 / 400, delta=0.01)    # 尻尾の先（いちばん下）は足ではない
        self.assertLess(base[1], 0.87)                             # 台座の底でなく、台の上の縁
        self.assertEqual(len(plain), 6)

    def test_crouching_measured_by_size(self):
        import render
        stand = {"body": [0.1, 0.9, 0.5, 0.5, 0.40]}
        crouch = {"body": [0.4, 0.9, 0.5, 0.9, 0.55]}   # 目から足が短いのに体は大きい
        alts = [dict(stand), dict(stand), dict(stand), crouch]
        render._body_len(alts)
        self.assertAlmostEqual(alts[0]["body"][5], 0.8)
        self.assertGreater(alts[3]["body"][5], 0.5)      # 目から足（0.5）より長く測る = 大きくしすぎない

    def test_cut_and_full_compared_separately(self):
        import render
        cut = {"body": [0.2, 2.2, 0.5, 0.6, 0.9]}
        mascot = {"body": [0.06, 1.0, 0.5, 0.7, 0.73]}   # 全身のままのマスコット（ポチタ）：体が大きくても、切った人と比べてしゃがみ扱いしない
        alts = [{"body": list(cut["body"])}, {"body": list(cut["body"])}, mascot]
        render._body_len(alts)
        self.assertAlmostEqual(mascot["body"][5], 0.94)

    def test_real_body_without_model_follows_board(self):
        import emblem
        from unittest import mock
        with mock.patch.object(emblem, "_pose_model", return_value=None), mock.patch.object(emblem, "face_box", return_value=(1, 2, 3, 4)):
            fig = self._figure()
            real, why = emblem.real_body(fig, emblem.body_marks(fig))
        self.assertIsNone(real)   # Actions（モデルなし）で顔があるとき：決めず、fit_all が版面の多いほうに合わせる（顔がなければ全身：test_real_body_no_model_no_face）

    def test_logo_flat_background(self):
        import emblem
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (300, 150), "white")
        ImageDraw.Draw(im).ellipse((60, 20, 240, 130), outline=(20, 20, 90), width=6)
        out = emblem.clear_flat_bg(im)
        self.assertEqual(out.mode, "RGBA")
        self.assertLess(out.size[0], 200)                  # 余白を切り詰めた
        self.assertEqual(out.getpixel((0, 0))[3], 0)       # 外の地は透明
        self.assertEqual(out.getpixel((out.size[0] // 2, out.size[1] // 2))[3], 255)   # 楕円の中の白はロゴの一部なので残る
        self.assertTrue(emblem.is_logo({"subject": "gelato pique のロゴ"}))
        self.assertTrue(emblem.is_logo({"subject": "x"}, kind="brand"))

    def test_same_wikimedia_file(self):
        a = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/bb/1203%E5%92%AA.jpg/500px-1203%E5%92%AA.jpg"
        b = "https://commons.wikimedia.org/wiki/Special:FilePath/1203%E5%92%AA.jpg?width=500"
        self.assertEqual(ef.file_key(a), ef.file_key(b))
        self.assertEqual(len(ef._dedupe([{"image": a}, {"image": b}])), 1)

    def test_title_logo_not_card(self):
        import emblem, io, tempfile, pathlib, render
        from unittest import mock
        from PIL import Image, ImageDraw
        logo = Image.new("RGB", (400, 100), "white")
        ImageDraw.Draw(logo).rectangle((40, 30, 360, 70), fill="black")   # 白い地に横長の字
        photo = Image.effect_noise((300, 300), 60).convert("RGB")           # 縁まで絵がある写真
        def png(im):
            b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(emblem, "EMB_DIR", pathlib.Path(d)):
            with mock.patch.object(emblem, "_get", return_value=png(logo)):
                path, ar, plate = emblem.wordmark_local("https://x/logo.png", "t")
            self.assertFalse(plate)   # 白い地は抜いて字だけ
            dark = Image.new("RGB", (400, 160), (50, 20, 60))
            ImageDraw.Draw(dark).rectangle((40, 50, 360, 110), fill="white")   # 濃い紫の板に白い字（HBO）
            with mock.patch.object(emblem, "_get", return_value=png(dark)):
                self.assertTrue(emblem.wordmark_local("https://x/hbo.png", "h")[2])   # 抜くと読めないので板ごと
            with mock.patch.object(emblem, "_get", return_value=png(photo)):
                self.assertIsNone(emblem.wordmark_local("https://x/p.png", "p"))
        self.assertLess(ar, render.WIDE_LOGO)
        self.assertIn('class="logo wide"', render._emblem_img({"src": "emblems/t.webp", "shape": "logo", "ar": ar}))

    def test_card_crops_only_close_ratio(self):
        import render
        wide = render._emblem_img({"src": "https://x/a.jpg", "shape": "badge", "ar": 0.52})
        near = render._emblem_img({"src": "https://x/a.jpg", "shape": "badge", "ar": 1.25})
        self.assertIn("badge whole", wide)
        self.assertNotIn("whole", near)

    def test_bust_from_body_cuts_at_same_body_point(self):
        import emblem
        from unittest import mock
        with mock.patch.object(emblem, "_pose_model", return_value=None):
            fig = self._figure(tail=True)
            mk = emblem.body_marks(fig)
            out, body = emblem.bust_from_body(fig, mk)
        eye, foot = mk[0] * 400, mk[1] * 400
        self.assertAlmostEqual(out.size[1], eye + (foot - eye) * emblem.BUST_CUT - 10, delta=6)   # 頭のてっぺん（y=10）から腰まで
        self.assertGreater(body[1], 1)                    # 足の裏は切った画像の外
        self.assertAlmostEqual((body[1] - body[0]) * out.size[1], foot - eye, delta=2)   # 目から足の長さは全身のときと同じ（そろえる尺度）



class LiveAction(unittest.TestCase):
    """実写の作品は役の姿（emblem_fill.role_of / check の anchor_only・trust_noface）。ネットに出ない。"""

    def test_role_from_actor_page_and_validation(self):
        from unittest import mock
        pages = {
            "Chris Evans": "{{Actor|image=Chris Evans.jpg|DOB=1981\n|character = [[Steve Rogers|Steve Rogers/Captain America]]<br>[[Johnny Storm]]\n}}",
            "Giancarlo Esposito": "{|\n|2019||[[Chapter 1]]||''[[The Mandalorian]]''||[[Moff]] [[Gideon]]\n|2020||[[Chapter 9]]||''The Mandalorian''||[[Moff]] [[Gideon]]\n|}",
            "Gideon": "{{Character|name=Gideon}}\nGideon was portrayed by [[Giancarlo Esposito]] in the series.",
            "Moff": "{{Title|name=Moff}}",
            "Katee Sackhoff": "{|\n|2020||\"[[Chapter 11]]\"||''[[Star Wars: The Mandalorian]]''||Bo-Katan Kryze<ref name=\"c11\">{{TheMandalorian|Chapter 11}}</ref>\n|2023||\"[[Chapter 17]]\"||''The Mandalorian''||Bo-Katan Kryze<ref>{{TheMandalorian|Chapter 17}}</ref>\n|}",
            "Bo-Katan Kryze": "{{Character|name=Bo-Katan}}\nBo-Katan was portrayed by [[Katee Sackhoff]] in live action.",
            "Harold Perrineau": "",
            "Boyd Stevens": "{{Character Info|name=Boyd Stevens|actor=[[Harold Perrineau]]|gender=Male}}",
            "Lauren Mary Kim": "{{Actor|occupation=Actress|nationality=American}} [[Harold Perrineau]] played with her",
        }
        wt = lambda api, titles: {t: pages.get(t, "") for t in titles}
        search = {"query": {"search": [{"title": t} for t in ["Harold Perrineau", "From", "Lauren Mary Kim", "Boyd Stevens", "Season 2"]]}}
        with mock.patch.object(ef, "_wikitext", side_effect=wt), mock.patch.object(ef, "_json", return_value=search):
            self.assertEqual(ef.role_of("x", "Chris Evans", ["Avengers"]), "Steve Rogers")              # 役の欄の最初のリンク
            self.assertEqual(ef.role_of("x", "Giancarlo Esposito", ["The Mandalorian"]), "Gideon")     # 表の役の列の最後（称号より名前）
            self.assertEqual(ef.role_of("x", "Katee Sackhoff", ["The Mandalorian"]), "Bo-Katan Kryze")  # 役の列がリンクなしの字だけ（<ref> を除いて役の記事で確かめる）
            self.assertEqual(ef.role_of("x", "Harold Perrineau", ["FROM", "From"]), "Boyd Stevens")    # 検索：役の記事の actor 欄（実在の人の記事は除く）

    def test_anchor_only_and_trusted_helmet(self):
        from unittest import mock
        from PIL import Image
        img = Image.effect_noise((300, 300), 60).convert("RGB")   # 一色だと「白紙」で落ちる
        cands = [{"subject": "Din（P）", "image": "a", "source": "基準（出演者の写真）", "anchor": True, "anchor_only": True},
                 {"subject": "Din（P）", "image": "b", "source": "役の記事", "trust_noface": True}]
        info = {"a": ("feat", {"faces": 1, "ratio": 0.5, "second": 0}), "b": (None, {"faces": 0})}
        with mock.patch.object(ef, "_get", return_value=b"x"), \
             mock.patch.object(ef, "inspect", side_effect=lambda d: ("badge", (0, 0, 0), img.copy())), \
             mock.patch.object(ef.face_id, "face_info", side_effect=[info["a"], info["b"]]), \
             mock.patch.object(ef.face_id, "same_person", return_value={0}):
            good = ef.check(cands, need_face=True, strict=True)
        self.assertEqual([c["image"] for c in good], ["b"])   # 基準は選ばない・兜で顔のない役の記事の代表画像は残る

    def test_actor_page_role_photo(self):
        """作り直しの剧：役の記事は前の映画の役者。出演者の記事の「X as 役」の写真を先に（哈利波特剧集）。"""
        from unittest import mock
        imgs = {"query": {"pages": {"1": {"images": [{"title": t} for t in [
            "File:Nick Frost.jpeg", "File:Nick Frost as Rubeus Hagrid.jpg", "File:Harry Potter HBO logo no background.png", "File:WP favicon.PNG"]]}},
                           "search": [{"title": "File:Nick Frost as Rubeus Hagrid.jpg"}, {"title": "File:HPTV BTS Nick Frost as Hagrid 2.jpg"}]}}
        info = lambda api, files, width=500: [{"title": t, "image": t, "page": "", "license": "", "area": 1} for t in files]
        with mock.patch.object(ef, "_json", return_value=imgs), mock.patch.object(ef, "_files_info", side_effect=info):
            rows = ef.actor_role_images("x", "Nick Frost", "Rubeus Hagrid")
        self.assertEqual([r["title"] for r in rows], ["File:Nick Frost as Rubeus Hagrid.jpg", "File:HPTV BTS Nick Frost as Hagrid 2.jpg"])   # 本人の写真・ロゴは除く・検索の写真も（重ねない）
        self.assertTrue(ef.is_role_image({"why": "Rubeus Hagrid（Nick Frost）：Fandom の出演者の記事の役の写真"}))
        self.assertLess(ef.PICK_ORDER.index("出演者の記事の役の写真"), ef.PICK_ORDER.index("役の記事"))

    def test_assign_stills_by_face(self):
        """作品の記事の剧照（ファイル名に役名がない）を名簿の出演者の顔の基準でいちばん近い人へ。近い人が 2 人いる・遠い剧照は割り当てない。"""
        from unittest import mock
        import numpy as np
        vec = {"a": np.array([1.0, 0, 0]), "b": np.array([0, 1.0, 0]), "s1": np.array([0.9, 0.1, 0]), "s2": np.array([0.5, 0.5, 0]),
               "s3": np.array([0, 0, 1.0])}
        item = {"name": "W", "emblem_who": ["Actor A", "Actor B"], "type": "show", "emblem_people": True}
        stills = [{"title": f"File:Still {k}.jpg", "image": k, "page": "", "license": ""} for k in ("s1", "s2", "s3")]
        ef._ANCHOR_FEAT.clear()
        cos = lambda x, y: float(x @ y / np.linalg.norm(x) / np.linalg.norm(y))
        with mock.patch.object(ef.face_id, "engine", return_value=object()), \
             mock.patch.object(ef, "work_stills", return_value=stills), mock.patch.object(ef, "wiki_titles", return_value={"en": "W"}), \
             mock.patch.object(ef, "anchor_rows", side_effect=lambda api, a: [(a[-1].lower(), "p")]), \
             mock.patch.object(ef, "_get", side_effect=lambda u, n: u), mock.patch.object(ef, "inspect", side_effect=lambda d: (0, 0, d)), \
             mock.patch.object(ef.face_id, "face_info", side_effect=lambda k: (vec[k], {"faces": 1, "ratio": 0.5, "second": 0})), \
             mock.patch.object(ef.face_id, "similarity", side_effect=cos):
            rows = ef.assign_stills("api", item, {"Actor A": "Role A"}, log=lambda s: None)
        ef._ANCHOR_FEAT.clear()
        self.assertEqual([(r["subject"], r["source"]) for r in rows], [("Role A（Actor A）", "基準（出演者の写真）"), ("Role A（Actor A）", "作品の剧照")])
        self.assertTrue(ef.is_role_image(rows[1]))   # 実写の版面に残る（役の姿）
        self.assertLess(ef.PICK_ORDER.index("作品の剧照"), ef.PICK_ORDER.index("役の記事"))

    def test_live_action_skips_actor_photos(self):
        self.assertTrue(ef.live_action({"type": "show", "emblem_people": True}))
        self.assertFalse(ef.live_action({"type": "anime"}))


class FindSources(unittest.TestCase):
    """新しいキャラの関注項：Fandom と分類を規則で見つけて書く（AI が設計を飛ばしても小元素が埋まる）。"""

    def test_fandom_and_category_are_found_and_written(self):
        item = {"name": "ちいかわ", "type": "anime", "subs": {"kind": "シリーズ"}, "emblem_kind": "character",
                "keywords": ["ちいかわ", "Chiikawa"], "subtitle": "ちいかわ なんか小さくてかわいいやつ"}
        def fake_json(url, *a):
            if "siteinfo" in url:
                if "chiikawa.fandom" in url:
                    return {"query": {"general": {"sitename": "Chiikawa Wiki"}}}
                raise OSError("no wiki")
            members = 12 if "Category%3ACharacters" in url else 0
            return {"query": {"categorymembers": [{"title": str(i)} for i in range(members)]}}
        wrote = {}
        with mock.patch.object(ef, "_json", fake_json), mock.patch.object(ef, "kind_of", lambda i: "character"), \
             mock.patch.object(ef, "_set_field", lambda name, k, v: wrote.__setitem__(k, v.split("#")[0].strip())):
            self.assertTrue(ef.find_sources(item, log=lambda *a: None))
        self.assertEqual(wrote["emblem_fandom"], "chiikawa")
        self.assertEqual(wrote["emblem_category"], '"Characters"')

    def _find(self, item, sites, cats, search=(), wd=None):
        """sites：{wiki: sitename}、cats：{分類: 人数}、search：分類の検索の結果。→ 書いた {key: 値}。"""
        def fake_json(url, *a):
            if "siteinfo" in url:
                w = url.split("//")[1].split(".")[0]
                if w in sites:
                    return {"query": {"general": {"sitename": sites[w]}}}
                raise OSError("404")
            if "list=search" in url:
                return {"query": {"search": [{"title": f"Category:{c}"} for c in search]}}
            n = next((v for c, v in cats.items() if urllib.parse.quote(f"Category:{c}") in url), 0)
            return {"query": {"categorymembers": [{"title": str(i)} for i in range(n)]}}
        wrote = {}
        import library_emblem
        with mock.patch.object(ef, "_json", fake_json), mock.patch.object(ef, "_set_field", lambda name, k, v: wrote.__setitem__(k, v.split("#")[0].strip())), \
             mock.patch.object(library_emblem, "wd_entity", lambda q, get=None: wd or {}):
            ef.find_sources({"emblem_kind": "character", **item}, log=lambda *a: None)
        return wrote

    def test_work_category_first_and_dead_fandom_from_wikidata(self):
        """GTA 6：書いてあった gtawiki は開けない → Wikidata の Fandom（gta）→ 作品の名前の付いた分類（Characters in GTA V は別の作品）。"""
        w = self._find({"name": "GTA 6", "subtitle": "Grand Theft Auto VI · 侠盗猎车手 6", "keywords": ["GTA VI"], "emblem_fandom": "gtawiki", "wikidata": "Q1"},
                       {"gta": "GTA Wiki"}, {"Characters": 500}, ["Characters in GTA V", "Characters in GTA VI"], {"fandom": "gta"})
        self.assertEqual(w, {"emblem_fandom": "gta", "emblem_category": '"Characters in GTA VI"'})

    def test_series_wiki_generic_category_and_anilist_does_not_stop_it(self):
        """BLEACH Mirrors High（Bleach Wiki）・チェンソーマン（AniList の主役 4 人）：その作品の wiki なら「Characters」。"""
        self.assertEqual(self._find({"name": "BLEACH Mirrors High", "emblem_fandom": "bleach"}, {"bleach": "Bleach Wiki"}, {"Characters": 500}),
                         {"emblem_category": '"Characters"'})
        self.assertEqual(self._find({"name": "チェーンソーマン", "keywords": ["Chainsaw Man"], "emblem_fandom": "chainsaw-man", "anilist_id": 1},
                                    {"chainsaw-man": "Chainsaw Man Wiki"}, {"Characters": 171}), {"emblem_category": '"Characters"'})

    def test_other_works_wiki_and_handwritten_are_left(self):
        """ぐでたま（Hello Kitty Wiki の Characters はサンリオ全部）は数えない。手で書いた分類・実写（出演者が名簿）は触らない。"""
        self.assertEqual(self._find({"name": "ぐでたま", "keywords": ["Gudetama"], "emblem_fandom": "hellokitty"}, {"hellokitty": "Hello Kitty Wiki"}, {"Characters": 500}), {})
        self.assertEqual(self._find({"name": "X", "emblem_fandom": "x", "emblem_category": "Agents"}, {"x": "X Wiki"}, {"Characters": 9}), {})
        self.assertEqual(self._find({"name": "FROM", "emblem_people": True}, {"from": "From Wiki"}, {"Characters": 9}), {})
        # 手で数えた人数が先：数が合わない分類（Characters 192）は使わない。合う分類（Heroes 127）があればそれ
        self.assertNotIn("emblem_category", self._find({"name": "dota2", "emblem_pool": 126}, {"dota2": "Dota 2 Wiki"}, {"Characters": 192}))
        self.assertEqual(self._find({"name": "dota2", "emblem_pool": 126, "emblem_fandom": "dota2"}, {"dota2": "Dota 2 Wiki"},
                                    {"Characters": 192, "Heroes": 127}), {"emblem_category": '"Heroes"'})

    def test_category_without_the_works_leads_is_replaced(self):
        """GTA 6：grand-theft-auto-vi の「Playable characters」は GTA IV・V の主役（Jason・Lucia がいない）→ その分類から入れた名前を外し、
        Wikidata の wiki（gta）の「Characters in GTA VI」（Jason が入っている）へ。"""
        def fake_json(url, *a):
            u = urllib.parse.unquote_plus(url)
            if "siteinfo" in u:
                return {"query": {"general": {"sitename": "GTA VI Wiki" if "grand-theft" in u else "GTA Wiki"}}}
            if "list=search" in u:
                return {"query": {"search": [{"title": "Category:Characters in GTA VI"}] if "//gta." in u else []}}
            if "prop=categories" in u:
                ok = "//gta." in u and "Characters in GTA VI" in u
                return {"query": {"pages": {"1": {"title": "Jason Duval", **({"categories": [{"title": "x"}]} if ok else {})}}}}
            if "grand-theft" in u and "Playable characters" in u:
                return {"query": {"categorymembers": [{"title": t} for t in ("Michael De Santa", "Trevor Phillips", "Niko Bellic")]}}
            n = 40 if "//gta." in u and "Characters in GTA VI" in u else 0
            return {"query": {"categorymembers": [{"title": str(i)} for i in range(n)]}}
        wrote = {}
        import library_emblem
        item = {"name": "GTA 6", "emblem_kind": "character", "subtitle": "Grand Theft Auto VI", "keywords": ["GTA VI"], "wikidata": "Q1", "emblem_fandom": "grand-theft-auto-vi",
                "emblem_category": "Playable characters", "emblem_pool": 7, "emblem_who": ["Jason Duval", "Lucia Caminos", "Michael De Santa", "Trevor Phillips", "Niko Bellic"]}
        with mock.patch.object(ef, "_json", fake_json), mock.patch.object(ef, "_set_field", lambda name, k, v: wrote.__setitem__(k, v.split("#")[0].strip())), \
             mock.patch.object(library_emblem, "wd_entity", lambda q, get=None: {"fandom": "gta", "leads": ["Jason Duval", "Lucia Caminos"]}):
            self.assertTrue(ef.find_sources(item, log=lambda *a: None))
        self.assertEqual(json.loads(wrote["emblem_who"]), ["Jason Duval", "Lucia Caminos"])
        self.assertEqual((wrote["emblem_fandom"], wrote["emblem_category"]), ("gta", '"Characters in GTA VI"'))

    def test_off_roster_emblems_are_dropped(self):
        """名簿が勝つ：dota2 の名簿（ヒーロー）にいない伝承のキャラ（Pololo）を外す。「Soldier 11」は名前のまま比べる。実写は見ない。"""
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "items.yaml").write_text('items:\n  - name: dota2\n    emblem_kind: character\n    emblem:\n'
                                            '      - {subject: "Axe", image: "a.webp"}\n      - {subject: "Axe 2", image: "a2.webp"}\n'
                                            '      - {subject: "Soldier 11", image: "s.webp"}\n      - {subject: "Pololo", image: "p.webp"}\n'
                                            '      - {subject: "Unnamed Officer 1", image: "u.webp"}\n', encoding="utf-8")
            item = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
            item["emblem_who"] = ["Axe", "Soldier 11", "Unnamed Officer"]   # 名簿にいても名前のない端役は人でない
            with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef.emblem, "ROOT", tmp):
                self.assertEqual(ef.off_roster(item, log=lambda *_: None), 2)
                self.assertEqual(ef.off_roster({**item, "emblem_people": True, "type": "show"}, log=lambda *_: None), 0)
            got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        self.assertEqual([x["subject"] for x in got["emblem"]], ["Axe", "Axe 2", "Soldier 11"])

    def test_redirected_page_does_not_take_the_leads_picture(self):
        """BLEACH Mirrors High：「Zangetsu (Quincy Powers)」の Fandom ページは黒崎一護のページへの転送で、一護の代表画像を先に取った。
        一護本人は「もう使っている画像」で 1 枚も取れなかった。別の人のページの画像は取らず、前からのものは emblem_reject に入れずに外す。"""
        who = ["Ichigo Kurosaki", "Rukia Kuchiki", "Zangetsu (Quincy Powers)", "Tōshirō Hitsugaya"]
        ich = "https://bleach.fandom.com/wiki/Ichigo_Kurosaki"
        self.assertEqual(ef.page_owner(ich, "Zangetsu (Quincy Powers)", who), "Ichigo Kurosaki")
        self.assertIsNone(ef.page_owner(ich, "Ichigo Kurosaki", who))
        self.assertIsNone(ef.page_owner("https://bleach.fandom.com/wiki/Toushirou_Hitsugaya", "Tōshirō Hitsugaya", who))   # 同じ人の書き方違い
        self.assertIsNone(ef.page_owner("https://bleach.fandom.com/wiki/File:BBSMaster_Ichigo.png", "Ichigo Kurosaki 2", who))
        self.assertIsNone(ef.page_owner("https://bleach.fandom.com/wiki/Zangetsu", "Zangetsu (Quincy Powers)", who))   # 名簿の人のページでなければ可
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "items.yaml").write_text('items:\n  - name: b\n    emblem_kind: character\n    emblem:\n'
                                            f'      - {{subject: "Zangetsu (Quincy Powers)", image: "z.webp", page: "{ich}"}}\n'
                                            '      - {subject: "Rukia Kuchiki", image: "r.webp", page: "https://bleach.fandom.com/wiki/Rukia_Kuchiki"}\n', encoding="utf-8")
            item = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
            item["emblem_who"] = who
            with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef.emblem, "ROOT", tmp):
                self.assertEqual(ef.wrong_owner(item, log=lambda *_: None), 1)
            got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        self.assertEqual([x["subject"] for x in got["emblem"]], ["Rukia Kuchiki"])
        self.assertNotIn("emblem_reject", got)

    def test_head_missing_counts_leads_without_emblem(self):
        """名簿の先頭 3 人（主役）のうち小元素がいない人。実写は「役（出演者）」、(…) つきの名前も同じ人。"""
        item = {"emblem_who": ["Ichigo Kurosaki", "Rukia Kuchiki", "Renji Abarai", "Uryuu Ishida"],
                "emblem": [{"subject": "Rukia Kuchiki"}, {"subject": "Uryuu Ishida"}]}
        self.assertEqual(ef.head_missing(item), ["Ichigo Kurosaki", "Renji Abarai"])
        live = {"emblem_who": ["Chris Hemsworth", "Pedro Pascal"], "emblem": [{"subject": "Thor（Chris Hemsworth）"}]}
        self.assertEqual(ef.head_missing(live), ["Pedro Pascal"])
        self.assertEqual(ef.head_missing({"emblem_who": ["Inklings"], "emblem": [{"subject": "Inklings 2"}]}), [])

    def test_closeup_is_face_only_without_shoulders(self):
        """BLEACH の黒崎一護 372×519：顔の幅 54〜68%・顔の下 5% = 顔だけのアップ。胸像（顔の下 26%）は可。顔が測れないものは None（落とさない）。"""
        from PIL import Image
        im = Image.new("RGBA", (372, 519))
        with mock.patch.object(ef.emblem_face, "measure", return_value=[0.733, 0.22, 0.54, 0.51, 372, 519]), \
                mock.patch.object(ef.emblem_face, "_boxes", return_value=[(60, 114, 252, 380)]):
            self.assertTrue(ef.closeup_of(im))
        with mock.patch.object(ef.emblem_face, "measure", return_value=[0.31, 0.08, 0.5, 0.5, 372, 519]), \
                mock.patch.object(ef.emblem_face, "_boxes", return_value=[(130, 40, 110, 161)]):
            self.assertFalse(ef.closeup_of(im))   # 顔の幅 30%・顔の下 61%
        with mock.patch.object(ef.emblem_face, "measure", return_value=[0.2, 0.75, 0.5, 0.5, 372, 519]), \
                mock.patch.object(ef.emblem_face, "_boxes", return_value=[(130, 389, 80, 104)]):
            self.assertTrue(ef.closeup_of(im))   # 顔は小さいが顔の下が 5%（肩・胸が写っていない）
        with mock.patch.object(ef.emblem_face, "measure", return_value=[0, 0, 0.5, 0.5, 372, 519]):
            self.assertIsNone(ef.closeup_of(im))

    def test_drop_closeups_rejects_source_and_marks_redo(self):
        """顔だけのアップは外して元の画像を emblem_reject・人を emblem_redo に。顔が測れないものは残す。固定は替えない。半分以上が当たる前からの版面は外さず報告だけ（取るときは無条件）。"""
        from PIL import Image
        def run(flags, only=None):
            with tempfile.TemporaryDirectory() as d:
                tmp = pathlib.Path(d)
                (tmp / "emblems").mkdir()
                lines = ["items:", "  - name: b", "    emblem_kind: character", "    emblem:"]
                for i in range(len(flags)):
                    Image.new("RGBA", (40, 50), (9, 9, 9, 255)).save(tmp / "emblems" / f"p{i}.png")
                    lines.append(f'      - {{subject: "P{i}", image: "emblems/p{i}.png", source: "https://x/p{i}.png", shape: cutout}}')
                lines.append(f'      - {{subject: "Locked", image: "emblems/p0.png", source: "https://x/l.png", shape: cutout, lock: true}}')
                (tmp / "items.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
                item = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
                it = iter(flags)
                with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef.emblem, "ROOT", tmp), mock.patch.object(ef.emblem.sitedir, "SITE_DIR", tmp), \
                        mock.patch.object(ef, "closeup_of", side_effect=lambda im: next(it)):
                    n = ef.drop_closeups(item, log=lambda *_: None, only=only)
                return n, yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        n, got = run([True, False, None, False, False, False])   # 1/7 当たる
        self.assertEqual(n, 1)
        self.assertEqual([x["subject"] for x in got["emblem"]], ["P1", "P2", "P3", "P4", "P5", "Locked"])
        self.assertEqual((got["emblem_reject"], got["emblem_redo"]), (["https://x/p0.png"], ["P0"]))
        with mock.patch.object(ef, "stage_closeups", return_value=(0, 0)) as st:
            n, got = run([True, True, True, False])   # 3/5 = 半分以上：外さず段階的な入れ替えへ
        self.assertEqual((n, len(got["emblem"]), st.call_count), (0, 5, 1))
        n, got = run([True, True, True, False], only={"https://x/p0.png", "https://x/p1.png", "https://x/p2.png"})   # 取るときは無条件
        self.assertEqual((n, len(got["emblem"])), (3, 2))

    def test_stage_closeups_swaps_bust_and_drops_after_three_tries(self):
        """BLEACH 型（半分以上が顔だけのアップ）：胸像が取れた人から入れ替え（取れるまで元のまま）、取れないまま 3 回で外す。名簿の上位 12 人は外さず探し続ける。
        探す順は回数の少ない人 → 名簿の上の人（一護が先）。1 回の人数は CLOSE_PER_ROUND。"""
        from PIL import Image
        who = ["Ichigo Kurosaki"] + [f"W{i}" for i in range(1, 14)] + ["Low"]
        self.assertEqual(ef.close_order(["Low", "W3", "Ichigo Kurosaki"], who, {"W3": 1})[0], "Ichigo Kurosaki")
        self.assertEqual(ef.close_order(["Low", "W3", "Ichigo Kurosaki"], who, {"Ichigo Kurosaki": 2}), ["W3", "Low", "Ichigo Kurosaki"])
        self.assertTrue(ef.close_top("Ichigo Kurosaki", who))
        self.assertFalse(ef.close_top("Low", who))
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "emblems").mkdir()
            lines = ["items:", "  - name: b", "    emblem_kind: character", "    emblem:"]
            for s in ("Ichigo Kurosaki", "W1", "Low"):
                Image.new("RGBA", (40, 50), (9, 9, 9, 255)).save(tmp / "emblems" / f"{s[:3]}.png")
                lines.append(f'      - {{subject: "{s}", image: "emblems/{s[:3]}.png", source: "https://x/{s[:3]}.png", shape: cutout}}')
            (tmp / "items.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
            (tmp / "state").mkdir()
            item = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
            item["emblem_who"] = who
            bust = ("https://x/bust.png", Image.new("RGBA", (120, 150), (50, 50, 50, 255)), 0.3)
            with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef.emblem, "ROOT", tmp), mock.patch.object(ef.emblem.sitedir, "SITE_DIR", tmp), \
                    mock.patch.object(ef.emblem, "EMB_DIR", tmp / "emblems"), \
                    mock.patch.object(ef.emblem_face, "measure_item") as meas:
                def run(found):
                    now = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
                    now["emblem_who"] = who
                    bad = [x for x in now["emblem"] if x["subject"] in ("Ichigo Kurosaki", "W1", "Low") and x.get("source") != "https://x/bust.png"]   # 胸像に替わった人はもう顔だけのアップでない
                    with mock.patch.object(ef, "bust_replacement", side_effect=lambda it, x, skip, log=print, **kw: bust if x["subject"] in found else None):
                        return ef.stage_closeups(now, bad, log=lambda *_: None)
                self.assertEqual(run({"Ichigo Kurosaki"}), (1, 0))   # 1 回目：一護だけ胸像が取れた
                got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
                ich = next(x for x in got["emblem"] if x["subject"] == "Ichigo Kurosaki")
                self.assertEqual((ich["source"], ich["fs"]), ("https://x/bust.png", 0.3))
                self.assertIn("https://x/Ich.png", got["emblem_reject"])   # 顔だけのアップの元の画像は二度と選ばない
                self.assertEqual(len(got["emblem"]), 3)   # 取れていない人は元のまま
                st = ef.closeup_state()["b"]
                self.assertEqual({s: v["n"] for s, v in st.items()}, {"W1": 1, "Low": 1})
                self.assertTrue(all(v.get("next") for v in st.values()))   # 各人の次に試す見込みを保存
                self.assertEqual(ef.closeup_eta_state()["b"]["waiting"], 2)   # 版面の見込みも保存
                self.assertEqual(run(set()), (0, 0))
                self.assertEqual(run(set()), (0, 1))   # 3 回目：名簿の外の Low は外す。上位の W1 は探し続ける
                got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
                self.assertEqual(sorted(x["subject"] for x in got["emblem"]), ["Ichigo Kurosaki", "W1"])
                self.assertEqual(got["emblem_redo"], ["Low"])
                self.assertEqual({s: v["n"] for s, v in ef.closeup_state()["b"].items()}, {"W1": 3})

    def test_close_round_top_every_time_and_eta(self):
        """上位 12 人は毎回（巡回の 8 人に入れない）・ほかは回数の少ない順に 8 人。見込みは 足りない回数 ÷ 8 回・次の回は毎時 47 分。"""
        import datetime as dt
        who = [f"P{i}" for i in range(20)]
        subj = [f"P{i}" for i in range(20)] + [f"X{i}" for i in range(10)]
        r = ef.close_round(subj, who, {s: 2 for s in subj[:12]})   # 上位は何回探しても毎回入る
        self.assertEqual(r[:12], [f"P{i}" for i in range(12)])
        self.assertEqual(len(r), 12 + ef.CLOSE_PER_ROUND)
        mine = {"X0": {"n": 1}, "X1": {"n": 0}, "P0": {"n": 5}}
        e = ef.close_eta(mine, who, dt.datetime(2026, 10, 27, 7, 50, tzinfo=dt.timezone(dt.timedelta(hours=9))))
        self.assertEqual((e["waiting"], e["top"], e["rounds"], e["next"]), (3, 1, 1, "08:47"))
        self.assertIn("次の回 08:47", ef.close_line("b", mine, who, dt.datetime(2026, 10, 27, 7, 50, tzinfo=dt.timezone(dt.timedelta(hours=9)))))

    def test_close_plan_saved_times(self):
        """保存する見込み：上位は次の回、ほかは回数の少ない順に 8 人ずつ 1 時間おき。版面の見込みは外れる時刻（done）つき。"""
        import datetime as dt
        who = [f"P{i}" for i in range(20)]
        now = dt.datetime(2026, 10, 27, 7, 50, tzinfo=dt.timezone(dt.timedelta(hours=9)))
        tries = {"P0": 5, **{f"X{i}": 0 for i in range(10)}}
        at, eta = ef.close_plan(tries, who, now)
        self.assertEqual(at["P0"], "2026-10-27T08:47+09:00")
        self.assertEqual(at["X0"], "2026-10-27T08:47+09:00")
        self.assertEqual(at["X9"], "2026-10-27T09:47+09:00")   # 9 人目は次の次の回
        self.assertEqual((eta["waiting"], eta["rounds"], eta["done"]), (11, 4, "2026-10-27T11:47+09:00"))   # 30 回 ÷ 8 = 4 回
        self.assertIsNone(ef.close_plan({"P0": 1}, who, now)[1]["done"])   # 上位だけ残る版面は外れる時刻がない

    def test_every_entrance_uses_close_round(self):
        """胸像を探す入口（店長 stage_closeups・お客さま stage_holds）は close_round を使う。close_order の先頭 8 人だけを取る書き方は禁止。"""
        root = pathlib.Path(__file__).resolve().parent.parent / "scripts"
        for p in root.glob("*.py"):
            src = p.read_text(encoding="utf-8")
            self.assertNotRegex(src, r"close_order\([^)]*\)\[:", p.name)
        self.assertIn("close_round(", (root / "library_emblem.py").read_text(encoding="utf-8"))
        self.assertIn("close_round(", (root / "emblem_fill.py").read_text(encoding="utf-8"))

    def test_library_stage_holds_top_every_time(self):
        """お客さまの版面も店長と同じ：上位 12 人は何回探しても毎回入る・外さない。"""
        import io
        import library_emblem as le
        who = [f"P{i}" for i in range(20)]
        names = [f"P{i}" for i in range(20)] + [f"X{i}" for i in range(10)]
        hold = [{"subject": s, "image": f"https://x/{s}.png"} for s in names]
        called = []
        with mock.patch.object(ef, "bust_replacement", side_effect=lambda it, x, skip, log=print, **kw: called.append(x["subject"])):
            rows, dropped, new = le.stage_holds({"name": "b", "emblem_who": who}, list(hold), hold, {s: 2 for s in names})
        self.assertEqual(called[:12], who[:12])
        self.assertEqual(len(called), 12 + ef.CLOSE_PER_ROUND)
        self.assertEqual(sorted(x["subject"] for x in dropped), sorted(called[12:]))   # 上位以外の 3 回目は外す
        self.assertTrue(all(new[s] == 3 for s in who[:12]))   # 上位は外さず探し続ける

    def test_admin_wait_uses_close_line(self):
        import render
        with mock.patch.object(ef, "closeup_state", return_value={"b": {"X": {"n": 1}}}), mock.patch.object(ef, "load_items", return_value=[{"name": "b", "emblem_who": []}]):
            self.assertIn("次の回", render._admin_closeup_wait())

    def test_better_cut_floor_and_gain(self):
        """入れ替えの質の下限：短い辺 256px 未満は取らない（一護 146×225）。元より質が上がらないものも取らない。元が下限未満なら下限以上のとき取る。"""
        from PIL import Image
        em = ef.emblem
        mk = lambda w, h: Image.new("RGBA", (w, h), (80, 80, 80, 255))
        with mock.patch.object(em, "face_sharp", return_value=None):
            self.assertFalse(em.better_cut(mk(146, 225), mk(372, 519)))   # 下限未満
            self.assertFalse(em.better_cut(mk(300, 300), mk(372, 519)))   # 下限は満たすが元より小さい
            self.assertTrue(em.better_cut(mk(400, 600), mk(372, 519)))
            self.assertTrue(em.better_cut(mk(256, 300), mk(100, 100)))   # 元が下限未満：候補が下限以上なら
            self.assertFalse(em.better_cut(mk(255, 400), mk(100, 100)))
            self.assertTrue(em.better_cut(mk(300, 300)))
        with mock.patch.object(em, "face_sharp", side_effect=[(50, 0.5, .5)]):
            self.assertFalse(em.better_cut(mk(400, 400)))   # ぼやけ（SHARP_MIN 未満）
        with mock.patch.object(em, "face_sharp", side_effect=[(50, 2.0, .5), (50, 3.0, .5)]):
            self.assertFalse(em.better_cut(mk(400, 600), mk(372, 519)))   # 元よりぼやける

    def test_official_bust_not_rejected_by_sharpness_or_missing_fs(self):
        """公式の立ち絵は顔の鋭さを元と比べず（大きい絵ほど数が低く出る：一護 3.06<3.45 で 15 回外れた）、顔が測れず fs なしでも
        bust_replacement が通し、書き込み分（bust_fields・店長もお客さまも同じ）は fs を書かず「公式サイトの絵」と言う。"""
        from PIL import Image
        em = ef.emblem
        mk = lambda w, h: Image.new("RGBA", (w, h), (80, 80, 80, 255))
        with mock.patch.object(em, "face_sharp", side_effect=[(50, 3.06, .5), (50, 3.45, .5)]):
            self.assertFalse(em.better_cut(mk(1026, 1256), mk(372, 519)))
        with mock.patch.object(em, "face_sharp", side_effect=[(50, 3.06, .5), (50, 3.45, .5)]):
            self.assertTrue(em.better_cut(mk(1026, 1256), mk(372, 519), official=True))
        with mock.patch.object(em, "face_sharp", side_effect=[(50, 0.5, .5)]):
            self.assertFalse(em.better_cut(mk(1026, 1256), official=True))   # 下限のぼやけは公式でも取らない
        item = {"name": "B", "site": "https://s.example/", "emblem_fandom": "bleach"}
        x = {"subject": "Ichigo Kurosaki", "image": "emblems/a.webp"}
        u = "https://s.example/top/character/ichigo/body.webp"
        with mock.patch.object(em, "official_for", return_value=[u]), \
                mock.patch.object(em, "find_bust", return_value=(u, mk(900, 1100), None)), \
                mock.patch.object(ef, "closeup_of", return_value=False), mock.patch.object(ef, "broken_image", return_value=False):
            self.assertEqual(ef.bust_replacement(item, x, set())[0], u)
        with mock.patch.object(em, "official_for", return_value=[]), \
                mock.patch.object(em, "find_bust", return_value=("https://f.example/x.png", mk(900, 1100), None)):
            self.assertIsNone(ef.bust_replacement(item, x, set()))   # 公式でない fs なし（顔なしの控え）は通さない
        y = ef.bust_fields(item, x, u, "b-ichigo", None)
        self.assertNotIn("fs", y)
        self.assertIn("公式サイトの絵", y["why"])
        self.assertEqual(ef.bust_fields(item, x, "https://f.example/x.png", "s", 0.3)["fs"], 0.3)

    def test_gather_official_first_skips_fandom(self):
        """名簿の取り方（gather）も公式サイトの立ち絵が先：公式で取れた人は Fandom に行かず、取れない人だけ Fandom（トップは 1 回しか取りに行かない）。"""
        em = ef.emblem
        em._OFFICIAL_HTML.clear()
        html = b'<img src="/top/character/ichigo/body.webp">'
        item = {"name": "BLEACH", "type": "anime", "emblem_kind": "character", "site": "https://s.example/", "emblem_fandom": "bleach",
                "emblem_who": ["Ichigo Kurosaki", "Rukia Kuchiki"]}
        fandom = mock.Mock(side_effect=ValueError("none"))
        with mock.patch.object(em, "_get", return_value=html) as g, mock.patch.object(em, "cutout_on_page", return_value=None) as cut, \
                mock.patch.object(em, "page_image", fandom), mock.patch.object(ef, "wikipedia_photos", return_value=[]), \
                mock.patch.object(ef, "commons_photos", return_value=[]), mock.patch.object(ef, "news_images", return_value=[]), \
                mock.patch.object(ef, "site_images", return_value=[]), mock.patch.object(ef, "bing_images", return_value=[]):
            tried = {}
            cands = ef.gather(item, log=lambda *a: None, tried=tried)
        self.assertEqual([c["image"] for c in cands if c["source"] == "公式サイト"], ["https://s.example/top/character/ichigo/body.webp"])
        self.assertEqual([c[0][1] for c in cut.call_args_list], ["Rukia Kuchiki"])   # Ichigo は Fandom に行かない
        self.assertEqual(g.call_count, 1)

    def test_gather_wide_official_first(self):
        """名前を広げる（gather_wide）も公式が先：公式で取れた人は Fandom の別名を引かない。"""
        em = ef.emblem
        em._OFFICIAL_HTML.clear()
        item = {"name": "BLEACH", "type": "anime", "emblem_kind": "character", "site": "https://s.example/", "emblem_fandom": "bleach",
                "emblem_who": ["Ichigo Kurosaki", "Rukia Kuchiki"]}
        with mock.patch.object(em, "_get", return_value=b'<img src="/top/character/ichigo/body.webp">'), \
                mock.patch.object(em, "page_image", side_effect=ValueError("none")) as pi:
            cands = ef.gather_wide(item, log=lambda *a: None, tried={})
        self.assertEqual([c["source"] for c in cands], ["公式サイト"])
        self.assertFalse(any(c[0][1].startswith("Ichigo") for c in pi.call_args_list))

    def test_official_images_and_site(self):
        """胸像の入れ替えは公式サイトの立ち絵が先：パスに char… と名前の語が入るものだけ（-sp・サムネ・ロゴ・ほかのキャラは除く）。site がなければアイコンの出どころの網域。"""
        em = ef.emblem
        em._OFFICIAL_HTML.clear()
        html = ('<img src="/top/character/ichigo/body.webp"><img src="/top/character/ichigo/body-sp.webp">'
                '<img data-src="/assets/character/thumb_01.jpg"><img src="/top/character/rukia/body.webp"><img src="/common/logo.webp">')
        with mock.patch.object(em, "_get", return_value=html.encode()):
            self.assertEqual(em.official_images("https://s.example/", ["Ichigo", "Kurosaki"]), ["https://s.example/top/character/ichigo/body.webp"])
            self.assertEqual(em.official_images("https://s.example/", ["Orihime"]), [])
        self.assertEqual(em.official_images(None, ["Ichigo"]), [])
        self.assertEqual(em.official_site({"icon": {"source": "https://s.example/ogp/a.jpg"}}), "https://s.example/")
        self.assertTrue(em.SCENE_FILE.search("File:Ep308IchigoBankai.png") and not em.SCENE_FILE.search("File:Ep363HitsugayaProfile.png"))

    def test_known_first_puts_other_versions_last(self):
        """ポケモン：漫画の (Adventures) の人がアニメの主役より先に来ない。元の順は保つ。小元素の並びも名簿の順。"""
        who = ["Red (Adventures)", "Ash Ketchum", "Gold (Adventures)", "Goh", "Red (Origins)", "Roy"]
        self.assertEqual(ef.emblem.known_first(who), ["Ash Ketchum", "Goh", "Roy", "Red (Adventures)", "Gold (Adventures)", "Red (Origins)"])
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "items.yaml").write_text('items:\n  - name: poke\n    emblem_kind: character\n    emblem:\n'
                                            '      - {subject: "Red (Adventures)", image: "r.webp"}\n      - {subject: "Goh", image: "g.webp"}\n'
                                            '      - {subject: "Ash Ketchum", image: "a.webp"}\n', encoding="utf-8")
            item = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
            item["emblem_who"] = ef.emblem.known_first(["Red (Adventures)", "Ash Ketchum", "Goh"])
            with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef.emblem, "ROOT", tmp):
                self.assertEqual(ef.off_roster(item, log=lambda *_: None), 1)
                self.assertEqual(ef.off_roster(item, log=lambda *_: None), 1)   # 2 回目は並び済みでも item は古い（呼び側が読み直す）
            got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        self.assertEqual([x["subject"] for x in got["emblem"]], ["Ash Ketchum", "Goh", "Red (Adventures)"])

    def test_locked_emblem_stays_and_redo_goes_first(self):
        """固定（lock）した小元素は名簿の外でも外さない。「別の写真に替える」を押した人（emblem_redo）は次の集めで先に。"""
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "items.yaml").write_text('items:\n  - name: dota2\n    emblem_kind: character\n    emblem:\n'
                                            '      - {subject: "Axe", image: "a.webp"}\n      - {subject: "Pololo", image: "p.webp", lock: true}\n'
                                            '      - {subject: "Zed", image: "z.webp"}\n', encoding="utf-8")
            item = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
            item["emblem_who"] = ["Axe"]
            with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef.emblem, "ROOT", tmp):
                self.assertEqual(ef.off_roster(item, log=lambda *_: None), 1)
            got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        self.assertEqual([(x["subject"], x.get("lock")) for x in got["emblem"]], [("Axe", None), ("Pololo", True)])
        who = [f"c{i}" for i in range(30)]
        got = ef.subjects({"type": "game", "emblem_who": who, "emblem_redo": ["c25", "c3"]}, "character", 30)
        self.assertEqual(got[:2], ["c3", "c25"])

    def test_live_action_roster_is_the_cast(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "items.yaml").write_text('items:\n  - name: FROM\n    type: show\n    emblem_kind: character\n', encoding="utf-8")
            item = {"name": "FROM", "type": "show", "emblem_kind": "character", "emblem_people": True, "wikidata": "Q9", "emblem_who": ["B"]}
            with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef, "wd_cast", return_value=["A", "B", "C"]):
                self.assertEqual(ef.roster(item, log=lambda *_: None), 3)
            got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        self.assertEqual((got["emblem_pool"], got["emblem_who"]), (3, ["B", "A", "C"]))

    def test_live_action_roster_from_articles(self):
        """漫威电影（フランチャイズ、P161 なし）は wiki: の記事の作品の P161、哈利波特剧集は記事の Cast の節も。同じ人は 1 回、役も入る。"""
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "items.yaml").write_text('items:\n  - name: M\n    type: show\n    emblem_kind: character\n', encoding="utf-8")
            item = {"name": "M", "type": "show", "emblem_kind": "character", "emblem_people": True, "wikidata": "Q1",
                    "wiki": ["en:Avengers: Doomsday", "en:Marvel Cinematic Universe"], "emblem_who": ["A"], "emblem_roles": {"A": "Thor"}}
            cast = lambda q, title=None: ["A", "B"] if title == ("en", "Avengers: Doomsday") else []   # 1 言語に記事 2 つでも 1 つ目を読む
            with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef, "wd_cast", side_effect=cast), \
                    mock.patch.object(ef, "wiki_cast", return_value=[("B", "Hulk"), ("C", "Doctor Doom")]):
                self.assertEqual(ef.roster(item, log=lambda *_: None), 3)
            got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        self.assertEqual((got["emblem_who"], got["emblem_roles"]), (["A", "B", "C"], {"B": "Hulk", "C": "Doctor Doom", "A": "Thor"}))

    def test_cast_section_lines(self):
        s = ("* [[Dominic McLaughlin]] as [[Harry Potter (character)|Harry Potter]]\n* Arabella Stanton as [[Hermione Granger]], a student\n"
             "* ''[[Paapa Essiedu]]'' as Severus Snape\n* A note without the word\n")
        self.assertEqual([(m.group(2) or m.group(1) or m.group(3), m.group(4) or m.group(5)) for m in ef.CAST_LINE.finditer(s)],
                         [("Dominic McLaughlin", "Harry Potter"), ("Arabella Stanton", "Hermione Granger"), ("Paapa Essiedu", "Severus Snape")])

    def test_cast_section_drops_editor_comments(self):
        """役の中の <!-- 編集者への注意 --> は役ではない（Doomsday の Chris Evans）。"""
        wt = "* [[Chris Evans]] as Steve Rogers<!-- Do NOT add Captain America here -->\n* [[Tom Hiddleston]] as [[Loki]]\n"
        pages = iter([{"parse": {"sections": [{"line": "Cast", "index": "2"}]}}, {"parse": {"wikitext": {"*": wt}}}])
        with mock.patch.object(ef, "_json", lambda url, *a: next(pages)):
            self.assertEqual(ef.wiki_cast("en", "Avengers: Doomsday"), [("Chris Evans", "Steve Rogers"), ("Tom Hiddleston", "Loki")])

    def test_cast_section_from_wikidata_article_when_no_wiki(self):
        """wiki: を書いていない実写の版面（哈利波特剧集）も Wikidata の英語の記事の Cast の節を読む。"""
        item = {"name": "H", "type": "show", "emblem_people": True, "wikidata": "Q1"}
        with mock.patch.object(ef, "wd_cast", return_value=["A"]), mock.patch.object(ef, "wd_enwiki", return_value="Harry Potter (TV series)"), \
                mock.patch.object(ef, "wiki_cast", side_effect=lambda l, t: [("A", "Harry"), ("B", "McGonagall")] if t == "Harry Potter (TV series)" else []):
            self.assertEqual(ef.live_cast(item, log=lambda *_: None), (["A", "B"], {"A": "Harry", "B": "McGonagall"}))

    def test_surname_added_is_same_person(self):
        """Wikidata の「Tenoch Huerta」と Cast の節の「Tenoch Huerta Mejía」は同じ人（名簿 34 → 33）。役は先の名前へ。"""
        self.assertTrue(ef._same_person("Tenoch Huerta", "Tenoch Huerta Mejía"))
        self.assertFalse(ef._same_person("Chris Hemsworth", "India Rose Hemsworth"))
        self.assertFalse(ef._same_person("Chris", "Chris Evans"))   # 1 語だけの名前は前の一致で同じにしない
        item = {"name": "M", "type": "show", "emblem_people": True, "wikidata": "Q1"}
        with mock.patch.object(ef, "wd_cast", return_value=["Tenoch Huerta", "Mabel Cadena"]), \
                mock.patch.object(ef, "wiki_cast", return_value=[("Tenoch Huerta Mejía", "Namor")]), mock.patch.object(ef, "wd_enwiki", return_value="X"):
            self.assertEqual(ef.live_cast(item, log=lambda *_: None), (["Tenoch Huerta", "Mabel Cadena"], {"Tenoch Huerta": "Namor"}))

    def test_full_roster_is_recounted_when_rules_change(self):
        """名簿がそろっていても（pool 12・who 12）、名簿の規則の版が上がった回は roster を呼ぶ（哈利波特剧集）。"""
        item = {"name": "H", "type": "show", "emblem_kind": "character", "emblem_people": True, "wikidata": "Q1",
                "emblem_pool": 2, "emblem_who": ["A", "B"], "emblem": []}
        calls = []
        with mock.patch.object(ef, "find_sources", return_value=False), mock.patch.object(ef, "roster", side_effect=lambda i, log: calls.append(1)), \
                mock.patch.object(ef, "off_roster", return_value=0), mock.patch.object(ef, "drop_broken", return_value=0), \
                mock.patch.object(ef, "status", return_value={"state": "ok", "have": 2, "target": 2}):
            ef.fill_one(item, log=lambda *_: None)
            self.assertEqual(calls, [])
            ef.fill_one({**item, "_recount": True}, log=lambda *_: None)
            self.assertEqual(calls, [1])

    def test_sliver_cuts_are_dropped(self):
        """読めない（0 バイト）・切れ端（60×10）・帯（209×45）の切り抜きは外して emblem_reject へ。ロゴ・カードは見ない。"""
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "emblems").mkdir()
            for n, size in (("ok", (120, 160)), ("bar", (60, 10)), ("band", (209, 45)), ("wide", (400, 100))):
                Image.new("RGBA", size).save(tmp / "emblems" / f"{n}.webp")
            (tmp / "emblems" / "zero.webp").write_bytes(b"")
            (tmp / "items.yaml").write_text('items:\n  - name: M\n    emblem_kind: character\n    emblem:\n'
                                            '      - {subject: "a", image: "emblems/ok.webp", shape: cutout}\n'
                                            '      - {subject: "b", image: "emblems/bar.webp", source: "http://s/b", shape: cutout}\n'
                                            '      - {subject: "c", image: "emblems/band.webp", shape: cutout}\n'
                                            '      - {subject: "d", image: "emblems/zero.webp", shape: cutout}\n'
                                            '      - {subject: "e", image: "emblems/wide.webp", shape: badge}\n', encoding="utf-8")
            item = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
            with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(ef.emblem, "ROOT", tmp), mock.patch.object(ef.emblem.sitedir, "SITE_DIR", tmp):
                with mock.patch.object(ef, "drop_same", return_value=0):   # 真っ白の試験画像どうしは同じ見た目になる
                    self.assertEqual(ef.drop_broken(item, log=lambda *_: None), 3)
            got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        self.assertEqual([x["subject"] for x in got["emblem"]], ["a", "e"])
        self.assertEqual(got["emblem_reject"], ["http://s/b", "emblems/band.webp", "emblems/zero.webp"])

    def test_same_person_other_spelling_is_not_added_twice(self):
        self.assertEqual(ef._name_key("Uryuu Ishida"), ef._name_key("Uryū Ishida"))
        self.assertEqual(ef._name_key("Toushirou Hitsugaya"), ef._name_key("Tōshirō Hitsugaya"))
        self.assertNotEqual(ef._name_key("Ichigo Kurosaki"), ef._name_key("Rukia Kuchiki"))

    def test_full_character_board_is_rechecked_once(self):
        """そろったキャラの版面も、名簿の手がかりがあれば今の名簿の規則で 1 回だけ数え直す（BLEACH 6 人で止まっていた）。"""
        item = {"name": "B", "emblem_kind": "character", "emblem_fandom": "bleach", "emblem_who": ["a"], "emblem": [{"subject": "a", "image": "x"}]}
        prog = {"items": {}}
        self.assertEqual([i["name"] for i in ef.due(prog, [item], "2026-10-25T00:00:00")], ["B"])
        ef.record(prog, item, {"state": "ok", "tried": {}}, "2026-10-25T00:00:00")
        self.assertEqual(ef.due(prog, [item], "2026-10-25T00:00:00"), [])
        item["emblem_category"] = "Characters"   # 分類はあるのに人数を数えられなかった（429）→ 次の回も
        self.assertEqual([i["name"] for i in ef.due(prog, [item], "2026-10-25T00:00:00")], ["B"])

    def test_other_wiki_with_same_letters_is_not_used(self):
        item = {"name": "FROM", "keywords": ["FROM"]}
        with mock.patch.object(ef, "_json", lambda url, *a: {"query": {"general": {"sitename": "Some Other Wiki"}}}):
            self.assertIsNone(ef.fandom_api(item, strict=True))

    def test_fit_all_does_not_refit_its_own_output(self):
        """commit のたびに fit_all が前の切り抜きを face_fit で切り詰め直して縮んだ（Black Panther 73×23 → 60×10）。自分の出力は触らない。"""
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "emblems").mkdir()
            Image.new("RGBA", (73, 120), (200, 0, 0, 255)).save(tmp / "emblems" / "a.webp")
            y = '  - name: "A"\n    emblem:\n      - {subject: "x", image: "emblems/a.webp", shape: "cutout", fs: 0.3}\n'
            (tmp / "items.yaml").write_text("items:\n" + y, encoding="utf-8")
            with mock.patch.object(ef.emblem, "ROOT", tmp), mock.patch.object(ef.emblem.sitedir, "SITE_DIR", tmp), \
                 mock.patch.object(ef.emblem, "face_fit", side_effect=AssertionError("refit")):
                ef.emblem.fit_all("A")
                ef.emblem.fit_all("A")
            self.assertEqual(Image.open(tmp / "emblems" / "a.webp").size, (73, 120))
