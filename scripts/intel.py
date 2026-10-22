"""地域ごとの情報員（2026-10-22，用户定的）：今の情報源（Google・Bing・Reddit・GDELT…）は全世界共通の検索。
情報員はその地域の専門サイトの RSS / Atom を分類（板块）ごとに持ち、関注項の言語・板块で担当が決まる。全部規則、AI なし。

- 情報員 = intel/<地域>.yaml（データだけ。足すのにコードは要らない）：id・ja・langs・sources（id・name・url・cats・exclude・terms）
- 担当（agents_for）：settings.intel（items.yaml、開關）に入っている地域のうち、
  関注項が自分で書いた news_langs と langs が重なるもの（settings の既定の言語は数えない：全部の関注項に付いてしまう）。
  関注項に intel: [japan] と書けばその地域、intel: [] と書けば付けない
- 読む情報源（entries_for）：cats が関注項の板块（section と also）と重なるもの（cats: "*" は全部）
- 同じフィードは 1 回の収集で 1 回だけ取る（関注項が 20 あっても取得は 1 回、スレッド間で共有）
- 集めた記事は digest.filter_entries で今までどおり match・exclude・垃圾站・去重を通る
- 情報源ごとの結果（ok・記事なし・断られた・時間切れ・読めない）を health() で数え、収集のログに 1 行
  （last30days の考え方：「取れなかった」と「記事がなかった」を分ける）

    python scripts/intel.py            # 情報員と担当の一覧
    python scripts/intel.py --fetch    # 全部の情報源を実際に取ってみる
"""

import copy
import pathlib
import socket
import sys
import threading
import urllib.error

import yaml

import sources
import taxonomy

ROOT = pathlib.Path(__file__).resolve().parent.parent
INTEL_DIR = ROOT / "intel"

_regions = None
_feeds = {}             # url → [Entry]（この回で取ったもの）
_status = {}            # url → (状態, 件数, 名前, 地域)
_locks = {}
_lock = threading.Lock()


def regions():
    """intel/*.yaml を読む（id → 情報員）。"""
    global _regions
    if _regions is None:
        _regions = {}
        for path in sorted(INTEL_DIR.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if data.get("id"):
                _regions[data["id"]] = data
    return _regions


def agents_for(item, settings):
    """この関注項を担当する情報員（id の並び）。"""
    on = [r for r in settings.get("intel") or [] if r in regions()]
    if "intel" in item:   # 関注項が自分で決めた（[] = 付けない）
        return [r for r in item.get("intel") or [] if r in on]
    langs = set(item.get("news_langs") or [])
    return [r for r in on if langs & set(regions()[r].get("langs") or [])]


def boards(item):
    """関注項の板块：section（書いていなければ type から。digest.section_of と同じ規則）と also。"""
    main = taxonomy.canonical(item.get("section") or taxonomy.BY_TYPE.get(item.get("type", "product"), "好物"))
    return {main} | {taxonomy.canonical(k) for k in item.get("also") or {}}


def sources_for(item, settings):
    """(地域, 情報源) の並び。"""
    mine = boards(item)
    out = []
    for r in agents_for(item, settings):
        for src in regions()[r].get("sources") or []:
            cats = src.get("cats") or []
            if cats == "*" or mine & set(cats):
                out.append((r, src))
    return out


def _state(err):
    if isinstance(err, urllib.error.HTTPError):
        return "rate-limited" if err.code == 429 else "blocked" if err.code in (401, 403, 405, 451) else f"http {err.code}"
    if isinstance(err, (socket.timeout, TimeoutError)) or "timed out" in str(err):
        return "timeout"
    return "unreachable"


def fetch(region, src):
    """情報源を 1 回だけ取る（2 回目からは覚えたもの）。"""
    url = src["url"]
    with _lock:
        lock = _locks.setdefault(url, threading.Lock())
    with lock:
        if url in _feeds:
            return _feeds[url]
        try:
            data = sources._get(url)
            got = sources.rss_bytes(data, src.get("name") or url)
            state = "ok" if got else "no-results" if data.strip() else "schema-drift"
        except Exception as e:  # noqa: BLE001  一つ取れなくてもほかは続ける
            sources._warn(f"情報員 {src.get('name') or url}", e)
            got, state = [], _state(e)
        drop = [w.lower() for w in src.get("exclude") or []]
        got = [e for e in got if not any(w in e.title.lower() for w in drop)]
        with _lock:   # health() が読む間に、待つのをやめた（固まった）版面のスレッドが書き足しても壊れないように
            _feeds[url] = got
            _status[url] = (state, len(got), src.get("name") or url, region)
        return got


def entries_for(item, settings):
    """この関注項の分の記事（情報員が持つフィードの記事。絞り込みは digest.filter_entries で）。
    同じフィードを別の関注項も使うので、記事は写しを返す（出刊で image_via・link が書き足される）。"""
    out = []
    for region, src in sources_for(item, settings):
        out += [copy.copy(e) for e in fetch(region, src)]
    return out


def health():
    """この回の情報源の様子（収集のログに書く 1 行）。何も取っていなければ空。"""
    with _lock:   # 写しを取ってから回す（収集の締め切りのあとも daemon のスレッドが _status に書き足すことがある）
        rows_all = list(_status.values())
    if not rows_all:
        return ""
    by = {}
    for state, n, name, region in rows_all:
        by.setdefault(region, []).append((state, n, name))
    parts = []
    for region, rows in by.items():
        ok = [r for r in rows if r[0] == "ok"]
        bad = [f"{name}（{state}）" for state, n, name in rows if state not in ("ok", "no-results")]
        ja = regions().get(region, {}).get("ja", region)
        parts.append(f"{ja}：{len(ok)}/{len(rows)} 本・{sum(r[1] for r in rows)} 件" + (f"・取れない {'、'.join(bad)}" if bad else ""))
    return " / ".join(parts)


def reset():
    """テスト・次の回のために、覚えたフィードを忘れる。"""
    global _regions
    _regions = None
    _feeds.clear()
    _status.clear()
    _locks.clear()


def main(argv):
    import digest
    settings, items = digest.load_config()
    print("開關 settings.intel：", settings.get("intel") or "（なし = 情報員は動かない）")
    for r, data in regions().items():
        print(f"\n■ {data.get('ja', r)}（{r}）言語 {data.get('langs')}・情報源 {len(data.get('sources') or [])} 本")
        for item in items:
            srcs = [s["name"] for rr, s in sources_for(item, dict(settings, intel=[r]))]
            if srcs:
                print(f"  {item['name']}（{item.get('section')}）← {'、'.join(srcs)}")
    if "--fetch" in argv:
        for r, data in regions().items():
            for src in data.get("sources") or []:
                fetch(r, src)
        print("\n" + health())


if __name__ == "__main__":
    main(sys.argv[1:])
