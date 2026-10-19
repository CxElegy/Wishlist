"""头版的板块一览（sections.yaml）：事先定全的板块、各自的小分类分法和常用值，和「对号入座」的规则。

新关注项不临时开新板块：设置页的向导（docs/additem.js）和这里用同一张表，按维基数据的说明、名字里的词推荐板块（classify），
小分类从 values 里选（guess_subs）。都是规则，不用 AI。
"""
import pathlib
import re

import yaml

FILE = pathlib.Path(__file__).resolve().parent.parent / "sections.yaml"
OTHER = "其他"
# 向导「这是什么？」的答案 → 没有词命中时的板块（和以前的 SECTION_BY_TYPE 一样）
BY_TYPE = {"game": "游戏", "anime": "影视", "show": "影视", "product": "好物", "category": "好物", "event": "演出"}
# 以前的 17 个板块 → 现在的 8 个大类（2026-10-19 合并）。items.yaml・设置页的请求里写着旧名字的照这个换
LEGACY = {"时尚": "好物", "数码": "好物", "汽车": "好物", "书刊": "影视",
          "宠物": "生活", "美食": "生活", "爱好": "生活", "家居": "生活", "健康": "生活", "艺术": "出行"}
SERIES = "シリーズ"   # 方法 4：同一个板块里有两种以上媒体的作品（ちいかわ = 漫画・アニメ・映画）的小分类
# 题材型的面：板块里没写 facets 的（「咖啡」「滑雪板」…）用这一套。sec 不写 = 这个板块
GENERIC_FACETS = [
    {"id": "new", "label": "新商品・新作", "kw": ["新商品", "新作"], "re": "新商品|新作|新発売|発売|新品|新款|新登場", "rec": True},
    {"id": "shop", "label": "お店・オープン", "kw": ["新店", "オープン"], "re": "オープン|開店|开店|新店|閉店|店舗|ショップ", "rec": True},
    {"id": "event", "label": "イベント・展示", "kw": ["イベント", "展"], "re": "イベント|展覧会|展示|フェス|ポップアップ|POP ?UP|展",
     "sec": "出行", "subs": {"kind": "季節イベント"}},
    {"id": "collab", "label": "コラボ", "kw": ["コラボ"], "re": "コラボ|联名|聯名|collab", "sec": "好物", "subs": {"kind": "雑貨・食器", "owner": "ジャンル"}},
    {"id": "sale", "label": "セール・値下げ", "kw": ["セール"], "re": "セール|値下げ|割引|特価|sale|折扣"},
]


def canonical(key):
    """旧い板块名（宠物・时尚…）は今の大類に。"""
    return LEGACY.get(key, key)


def _load():
    rows = (yaml.safe_load(FILE.read_text(encoding="utf-8")) or {}).get("sections") or []
    return {r["key"]: r for r in rows}


SECTIONS = _load()   # {key: {ja, en, color, icon, kind, words, schemes}}，按 sections.yaml 的顺序


def sub_schemes():
    """items.yaml 以前的 settings.sub_schemes：{板块: [{id, label}]}。"""
    return {k: [{"id": x["id"], "label": x["label"]} for x in r.get("schemes") or []] for k, r in SECTIONS.items()}


def _hit(words, text):
    return bool(words) and re.search(words, text, re.I) is not None


def classify(text, type_=None):
    """说明・名字里的词 → 板块（prio の小さい順、同じなら sections.yaml の順。先命中的算）；都没命中按 type；还没有就「其他」。"""
    for key, r in sorted(SECTIONS.items(), key=lambda kv: kv[1].get("prio", 50)):
        if _hit(r.get("words"), text or ""):
            return key
    return BY_TYPE.get(type_ or "", OTHER)


def values(scheme):
    """分法的常用值（写成 {v: 雑誌, re: magazine|杂志} 的取 v）。"""
    return [v["v"] if isinstance(v, dict) else v for v in scheme.get("values") or []]


def _says(value, text):
    """值が text に出てくるか。値そのもの（「家具・インテリア」は「家具」でも「インテリア」でも、英字は単語として）か、
    {v, re} の re（英語・中国語の言い方）。"""
    if isinstance(value, dict):
        return _hit(value.get("re"), text) or _says(value["v"], text)
    for p in filter(None, re.split(r"[・/]", value)):
        if re.search(rf"\b{re.escape(p)}\b" if p.isascii() else re.escape(p), text, re.I):
            return True
    return False


def guess_subs(section, text=""):
    """每种分法选一个值：说明・名字里出现了的值，没有就第一个值。"""
    out = {}
    for x in (SECTIONS.get(section) or SECTIONS[OTHER]).get("schemes") or []:
        vals = x.get("values") or []
        pick = next((v for v in vals if _says(v, text or "")), None)
        if pick is not None or vals:
            pick = vals[0] if pick is None else pick
            out[x["id"]] = pick["v"] if isinstance(pick, dict) else pick
    return out


def facets(key, kind=None):
    """题材型（「猫」这种普通词）的「面」：sections.yaml 的 facets[第一种分法的值]（ペット：用品・フード・健康…），
    没写就用 GENERIC_FACETS（新商品・お店・イベント・コラボ・セール）。sec・subs が書いてなければこの板块・この値。"""
    r = SECTIONS.get(key) or SECTIONS[OTHER]
    first = (r.get("schemes") or [{}])[0]
    got = (r.get("facets") or {}).get(kind) if kind else None
    return [{**f, "sec": f.get("sec") or key, "subs": f.get("subs") or ({first.get("id"): kind} if kind else {})}
            for f in (got or GENERIC_FACETS)]


def for_page():
    """设置页的向导用（render_settings 的 wl-cfg）：板块的日语名、颜色、默认的「这是什么」、对号入座的词、分法和常用值、题材型的面。"""
    return [{"key": k, "ja": r["ja"], "color": r["color"], "kind": r.get("kind") or "product", "words": r.get("words") or "",
             "schemes": r.get("schemes") or [], "prio": r.get("prio", 50),
             "facets": {v: facets(k, v) for v in (r.get("facets") or {})}, "facets_any": facets(k)} for k, r in SECTIONS.items()]
