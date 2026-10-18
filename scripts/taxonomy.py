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
    """说明・名字里的词 → 板块（sections.yaml 从上到下，先命中的算）；都没命中按 type；还没有就「其他」。"""
    for key, r in SECTIONS.items():
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


def facets(key):
    """题材型（「猫」这种普通词）的「面」：sections.yaml 的 facets，没写就用第一种分法的值（每个值 = 一个面，关键词就是这个值）。"""
    r = SECTIONS.get(key) or SECTIONS[OTHER]
    if r.get("facets"):
        return [{**f, "sec": f.get("sec") or key} for f in r["facets"]]
    first = (r.get("schemes") or [{}])[0]
    out = []
    for v in first.get("values") or []:
        name = v["v"] if isinstance(v, dict) else v
        if name == "その他":
            continue
        words = [p for p in re.split(r"[・/]", name) if p]
        out.append({"id": name, "label": name, "kw": words[:2], "sec": key, "subs": {first["id"]: name},
                    "re": "|".join([re.escape(w) for w in words] + ([v["re"]] if isinstance(v, dict) and v.get("re") else []))})
    return out


def for_page():
    """设置页的向导用（render_settings 的 wl-cfg）：板块的日语名、颜色、默认的「这是什么」、对号入座的词、分法和常用值、题材型的面。"""
    return [{"key": k, "ja": r["ja"], "color": r["color"], "kind": r.get("kind") or "product", "words": r.get("words") or "",
             "schemes": r.get("schemes") or [], "facets": facets(k)} for k, r in SECTIONS.items()]
