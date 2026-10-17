"""記事の言語と、読者の言語の好み（主言語・副言語）。全部ルール（AI なし）。

- 主言語（primary）：同じニュースが何語でも来ているとき、残すのはこの言語の版。網页の UI もこの言語（いまは日本語だけ）。
- 副言語（secondary）：主言語の版がないニュースはこの順で拾う。主言語・副言語のどれでもない言語の記事は載せない。
- 設定は items.yaml の settings.languages（いずれ読者ごとに ⚙ 設定ページで選ぶ）。

同じニュースか（言語が違うと文字で比べられない）は、作品ごとに次のどれかで判断する：
  ① 予定（event）の日付が同じで、ラベルか鍵が同じ　② 見出しのバージョン番号（Ver.3.3 / v3.3 / 3.3 버전 / 3.3版本）が同じ
  ③ 見出しの「月日」（10月21日 / October 21 / 10월 21일）が同じ。どれも記事の日付が DAYS 日以内のときだけ。"""
import datetime as dt
import re

NAMES = {"ja": "日本語", "en": "英語", "zh": "中国語", "ko": "韓国語"}
DEFAULT = {"primary": "ja", "secondary": ["en", "zh", "ko"]}
DAYS = 10   # 違う言語の同じニュースとみなす記事の日付の差（日）

KANA = re.compile(r"[぀-ゟ゠-ヿ]")
HANGUL = re.compile(r"[가-힯ᄀ-ᇿ]")
HAN = re.compile(r"[一-鿿]")
LATIN = re.compile(r"[A-Za-z]")


def detect(text):
    """見出しの言語：仮名 2 字以上 = ja、ハングル 2 字以上 = ko、漢字 2 字以上 = zh、ローマ字 3 字以上 = en、わからない = ""。
    （台湾の宣伝文の「の」1 字で日本語にしない。ローマ字の言語はまとめて en）"""
    text = text or ""
    if len(KANA.findall(text)) >= 2:
        return "ja"
    if len(HANGUL.findall(text)) >= 2:
        return "ko"
    if len(HAN.findall(text)) >= 2:
        return "zh"
    if len(LATIN.findall(text)) >= 3:
        return "en"
    return ""


def order(settings=None):
    """好みの順の言語のリスト [主言語, 副言語…]。settings.languages がなければ DEFAULT。"""
    conf = (settings or {}).get("languages") or DEFAULT
    out = [conf.get("primary") or DEFAULT["primary"]]
    for code in conf.get("secondary") or []:
        if code not in out:
            out.append(code)
    return out


def rank(code, langs):
    """小さいほど好み。わからない言語（""）は副言語の最後と同じ扱い、リストにない言語はその後ろ。"""
    if code in langs:
        return langs.index(code)
    return len(langs) - 1 if not code else len(langs)


def allowed(text, langs):
    """載せてよい言語か（主言語・副言語、または判断できない見出し）。"""
    code = detect(text)
    return not code or code in langs


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
VERSION = re.compile(r"(?:\bv(?:er(?:sion)?)?\.?\s*|バージョン\s*)(\d+\.\d+(?:\.\d+)?)"
                     r"|(\d+\.\d+(?:\.\d+)?)\s*(?:版本?|버전|バージョン|アップデート|大型更新|\s(?:update|patch))", re.I)
MD_CJK = re.compile(r"(\d{1,2})\s*[月월]\s*(\d{1,2})\s*[日일]")
MD_EN = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
PREFIX = re.compile(r"^\s*\d{1,2}/\d{1,2}\s+")   # 回顧号で AI 編集が付ける「10/9 」（記事の日付で、中身ではない）


def keys(headline):
    """言語が違っても同じになる見出しの鍵：バージョン番号（v3.3）と月日（m10-21）。"""
    t = PREFIX.sub("", headline or "")
    out = {"v" + (a or b) for a, b in VERSION.findall(t)}
    out |= {f"m{int(m):02d}-{int(d):02d}" for m, d in MD_CJK.findall(t)}
    out |= {f"m{MONTHS[m[:3].lower()]:02d}-{int(d):02d}" for m, d in MD_EN.findall(t)}
    return out


def _date(story):
    try:
        return dt.date.fromisoformat(str(story.get("date") or story.get("_issue") or "")[:10])
    except ValueError:
        return None


def _event(story):
    ev = story.get("event")
    return ev if isinstance(ev, dict) and len(str(ev.get("date") or "")) >= 10 else None


def same_news(a, b):
    """同じ作品の 2 本が「言語違いの同じニュース」か。同じ言語どうしは AI 編集・タイトルの重複判定に任せて False。"""
    la, lb = detect(a.get("headline")), detect(b.get("headline"))
    if not la or not lb or la == lb:
        return False
    da, db = _date(a), _date(b)
    if da and db and abs((da - db).days) > DAYS:
        return False
    ka, kb = keys(a.get("headline")), keys(b.get("headline"))
    ea, eb = _event(a), _event(b)
    if ea and eb and str(ea["date"])[:10] == str(eb["date"])[:10]:
        if (ea.get("label") or "") == (eb.get("label") or "") or ka & kb:
            return True
    return bool(ka & kb)


WEIGHT = {"hero": 0, "lead": 1}
EXTRA = ("event", "price", "video", "gallery")


def dedupe(stories, langs):
    """同じ作品の記事から、言語違いの同じニュースを 1 本にまとめる（PRODUCT.md 原則 4「同じニュースは 2 回出さない」）。
    残すのは好みの言語（主言語 → 副言語の順）の版。残す方は消す方の重み（hero / lead）・新しい号・予定や価格・出典（refs）を引き継ぐ。
    主言語・副言語にない言語の記事は落とす。順番は残した記事の元の位置。"""
    out = [dict(s) for s in stories if allowed(s.get("headline"), langs)]
    i = 0
    while i < len(out):
        j = i + 1
        while j < len(out):
            a, b = out[i], out[j]
            if not same_news(a, b):
                j += 1
                continue
            win, lose = (a, b) if rank(detect(a.get("headline")), langs) <= rank(detect(b.get("headline")), langs) else (b, a)
            if WEIGHT.get(lose.get("weight"), 2) < WEIGHT.get(win.get("weight"), 2):
                win["weight"] = lose["weight"]
            for k in EXTRA:
                if not win.get(k) and lose.get(k):
                    win[k] = lose[k]
            if lose.get("_issue") and str(lose["_issue"]) > str(win.get("_issue") or ""):
                win["_issue"] = lose["_issue"]
            if "refs" in win or "refs" in lose:
                win["refs"] = list(dict.fromkeys(list(win.get("refs") or []) + list(lose.get("refs") or [])))
            out[i] = win
            del out[j]
            j = i + 1   # まとめた記事の鍵が増えたかもしれないので、残りをもう一度比べる
        i += 1
    return out


def clean_title(title):
    """出典の見出しから末尾の「 - 媒体名」「｜媒体名」を取る（大文字・小文字はそのまま）。"""
    return re.sub(r"\s*[-|｜–—]\s*[^-|｜–—]{1,40}$", "", (title or "").strip()) or (title or "").strip()


def prefer_ref(story, titles, langs):
    """AI 編集の見出しの言語より好みの言語の出典が refs にあれば、見出しをその出典の原題にして、その出典を refs の先頭に。
    titles：{ref 番号: 原題}。blurb は見出しと言語が違えば消す（翻訳はしない）。"""
    refs = [r for r in story.get("refs") or [] if r in titles]
    if not refs:
        return story
    best = min(refs, key=lambda r: (rank(detect(titles[r]), langs), refs.index(r)))
    if rank(detect(titles[best]), langs) >= rank(detect(story.get("headline")), langs):
        return story
    s = {**story, "headline": clean_title(titles[best]), "refs": [best] + [r for r in story["refs"] if r != best]}
    if s.get("highlight") and s["highlight"] not in s["headline"]:
        s["highlight"] = ""
    if s.get("blurb") and detect(s["blurb"]) not in ("", detect(s["headline"])):
        s["blurb"] = ""
    return s
