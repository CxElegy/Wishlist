"""出来事ごとに束ねる（AI なし・規則だけ。BENCHMARKS 4-1）。

1 つの版面の記事を「同じ出来事」の束にまとめ、AI 編集には束ごとに見せる・前回の編集のあとに増えた束だけ見せる（digest.edit_brief）。
束ねる条件（2 本のあいだ）：
  - 見出しが同じ（媒体名を外して）か、
  - 「どの出来事かを言う語」（digest.story_tokens から版面の名前・版面の中でよく出る語を引いたもの）の重なりが
    重み 2 以上（英字・カナ・ハングル 1 語 = 1、漢字 2 字 = 0.5）で、少ないほうの語の 4 割以上が重なる、か
  - 言語が違い、バージョン番号か見出しの月日が同じ（lang.keys）
  かつ、日付の差が DAYS 日以内。
束どうしをつなぐときは、束の中のどの 2 本にも「食い違う数字」がないことを確かめる（別の試合をまとめない）：
  スコア（3-1・2:0）・バージョン・見出しの月日・第 N 話／N 日目・勝ち上がりの回（初戦・準決勝・決勝…）が両方にあって違う → つながない。
"""
import datetime as dt
import re
import unicodedata

import lang

DAYS = 3            # 同じ出来事とみなす記事の日付の差（日）
MIN_WEIGHT = 2.0    # 重なる語の重みの合計
MIN_JACCARD = 0.2  # 両方の語を合わせたうち重なる割合（MinHash と同じ考え：言葉の組の重なり率）
MIN_SHARE = 0.4     # 少ないほうの語のうち重なる割合
LINK = 0.5        # 2 つの束のあいだで近い組がこの割合以上ならつなぐ
COMMON = 0.2        # 版面の記事の 2 割を超えて出る語は「どの出来事か」を言わない

SCORE = re.compile(r"(?<![\d.])(\d{1,3})\s*[-–:対]\s*(\d{1,3})(?![\d.])")
NTH = re.compile(r"(?:第\s*(\d+)\s*[話回戦節期弾章]|(\d+)\s*(?:日目|話|回戦|節)|\b(?:ep(?:isode)?|round|day|game|week|stage|leg)\.?\s*(\d+)\b|\b(\d+)(?:st|nd|rd|th)\s+(?:round|leg|stage|game))", re.I)


ROUNDS = [("準々決勝", "qf"), ("準決勝", "sf"), ("決勝", "f"), ("初戦", "r1"), ("1回戦", "r1"), ("2回戦", "r2"), ("3回戦", "r3"),
          ("ベスト8", "qf"), ("8強", "qf"), ("ベスト4", "sf"), ("4強", "sf"),
          ("quarterfinal", "qf"), ("quarter-final", "qf"), ("semifinal", "sf"), ("semi-final", "sf"), ("final", "f"),
          ("first round", "r1"), ("second round", "r2"), ("third round", "r3")]


def _date(e):
    try:
        return dt.date.fromisoformat(str(e.get("date") or "")[:10])
    except ValueError:
        return None


def facts(title):
    """見出しの「食い違えば別の出来事」の数字：{種類: 値の集合}。"""
    t = unicodedata.normalize("NFKC", title or "").lower()   # 簡体字にしない（「初戦」が「初战」になる）
    out = {}
    sc = {"%s-%s" % (a, b) for a, b in SCORE.findall(t) if not (int(a) > 31 and int(b) > 12)}
    if sc:
        out["score"] = sc
    for k in lang.keys(title or ""):
        out.setdefault(k[0], set()).add(k)
    rest, rounds = t, set()
    for w, k in ROUNDS:   # 長い語から：「準決勝」を「決勝」と数えない
        pat = r"(?<![a-z])" + re.escape(w) + r"s?(?![a-z])" if w[0].isascii() else re.escape(w)   # 英語だけ語の境（「OP初戦」は初戦）
        if re.search(pat, rest):
            rounds.add(k)
            rest = rest.replace(w, " ")
    if rounds:
        out["round"] = rounds
    nth = {next(g for g in m if g) for m in NTH.findall(t)}
    if nth:
        out["nth"] = nth
    return out


def conflict(fa, fb):
    """2 本の数字が食い違うか：同じ種類が両方にあって、重なる値がない。"""
    return any(k in fb and not (fa[k] & fb[k]) for k in fa)


TAIL = re.compile(r"(?:\s*(?:[（(【\[<＜][^（）()【】\[\]<>＜＞]{1,40}[）)】\]>＞]|\s[-|｜–—]\s*[^-|｜–—]{1,40}))+\s*$")
DATED = re.compile(r"[（(]\s*\d{4}\s*年[^）)]{0,20}[）)]")


def words(entry):
    """「どの出来事か」を言う語の候補：見出しの最後の（媒体名）［大会名］・（2026年10月20日掲載）を外し、出典の名前の語も引く。"""
    import digest
    t = DATED.sub(" ", entry.get("title") or "")
    t = TAIL.sub("", t) or t
    return digest.story_tokens(t) - digest.story_tokens(str(entry.get("source") or ""))


def generic(item, titles):
    """titles = 記事ごとの語の集合（words）。この版面で「どの出来事か」を言わない語：版面の名前・検索語・匹配词の語と、記事の COMMON を超えて出る語。"""
    import digest
    out = set()
    for w in [item.get("name", ""), *(item.get("keywords") or []), *(item.get("match") or [])]:
        out |= digest.story_tokens(re.sub(r"^re:", "", str(w)))
    df = {}
    for ws in titles:
        for x in ws:
            df[x] = df.get(x, 0) + 1
    out |= {x for x, n in df.items() if n > max(2, len(titles) * COMMON)}
    return out


def _key(title):
    import digest
    return re.sub(r"\W+", "", digest._clean_title(title or ""))


def close(a, b, ta, tb):
    """記事 a・b（inbox の dict）と、その語の集合 ta・tb：同じ出来事か（数字の食い違いは別に見る）。"""
    import digest
    da, db = _date(a), _date(b)
    if da and db and abs((da - db).days) > DAYS:
        return False
    if _key(a.get("title")) and _key(a.get("title")) == _key(b.get("title")):
        return True
    common = ta & tb
    w = sum(digest._token_weight(x) for x in common)
    small = min(sum(digest._token_weight(x) for x in ta), sum(digest._token_weight(x) for x in tb)) or 1
    union = sum(digest._token_weight(x) for x in ta | tb) or 1
    if w >= MIN_WEIGHT and w / small >= MIN_SHARE and w / union >= MIN_JACCARD:
        return True
    la, lb = lang.detect(a.get("title")), lang.detect(b.get("title"))
    return bool(la and lb and la != lb and lang.keys(a.get("title") or "") & lang.keys(b.get("title") or ""))


def bundles(item, entries):
    """版面 item の記事 entries（inbox の dict、"n" つき）→ 束のリスト [[n, …], …]（束の中は n の小さい順、束は最初の n の順）。
    つなぎ方（平均のつながり）：近い 2 本を重なりの大きい順に見て、2 つの束のあいだで近い組が LINK 割以上・数字の食い違いがないときだけ 1 つに。
    1 本ずつ鎖のようにつながって別の話（発売日のうわさとケースの流出）まで 1 つになるのを防ぐ。"""
    import digest
    titles = [e.get("title") or "" for e in entries]
    raw = [words(e) for e in entries]
    gen = generic(item, raw)
    toks = [w - gen for w in raw]
    fs = [facts(t) for t in titles]
    near = {}
    for i in range(len(entries)):
        for j in range(i):
            if close(entries[i], entries[j], toks[i], toks[j]):
                near[(j, i)] = sum(digest._token_weight(x) for x in toks[i] & toks[j])
    group = list(range(len(entries)))
    members = {i: [i] for i in range(len(entries))}
    for (j, i), _ in sorted(near.items(), key=lambda kv: (-kv[1], kv[0])):
        gi, gj = group[i], group[j]
        if gi == gj:
            continue
        a, b = members[gi], members[gj]
        if any(conflict(fs[x], fs[y]) for x in a for y in b):
            continue
        if sum((min(x, y), max(x, y)) in near for x in a for y in b) < LINK * len(a) * len(b):
            continue
        keep, drop = min(gi, gj), max(gi, gj)
        for x in members.pop(drop):
            group[x] = keep
            members[keep].append(x)
    return [sorted(entries[x]["n"] for x in m) for _, m in sorted(members.items())]
