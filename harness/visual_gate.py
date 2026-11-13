"""見た目の関所（HARNESS_V2.md「ハーネス v3」C）：測った結果を審美基準の番号に直し、✗ が 1 つでもあれば終了コード 1。

  python harness/visual_gate.py RESULT.json [RESULT2.json …] [--strict] [--map harness/aesthetic_map.json]

読める結果の形（検査の名前 → 件数。0 が合格）：
  harness/aesthetic_count.py --json の出力  {"home/index.html@1400": {"counts": {"edge": 0, "cgap": 2, …}}, …}
  harness/self_review.py の review.json      [{"width": 1400, "counts": {"gap": 1, …}}, …]
  まとめた形（ux_check の結果を写すとき）   {"checks": {"gap": 0, "over": 3, "wide": false}}   数＝✗ の件数／bool は True＝合格・False＝✗
同じ検査の名前が複数の画面幅・ページにあれば合計する。結果に名前が無い検査は「未測定」（既定は落とさない。--strict で落とす）。
番号に検査が 1 つも無い項目（aesthetic_map.json の checks が空）は「人の目」＝ここでは判定しない。
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_MAP = HERE / "aesthetic_map.json"


def load_map(path=None):
    d = json.loads(pathlib.Path(path or DEFAULT_MAP).read_text(encoding="utf-8-sig"))
    return {k: list(v.get("checks") or []) for k, v in d["items"].items()}


def checks_to_items(mapping):
    """逆向き：検査の名前 → それが関わる番号。"""
    rev = {}
    for it, cs in mapping.items():
        for c in cs:
            rev.setdefault(c, []).append(it)
    return rev


def _add(tot, name, v):
    if isinstance(v, bool):
        n = 0 if v else 1
    elif isinstance(v, (int, float)):
        n = int(v)
    else:
        return
    tot[name] = tot.get(name, 0) + n


def collect(data):
    """結果 JSON → {検査の名前: ✗ の件数}。知らない形は ValueError。"""
    tot = {}
    if isinstance(data, dict) and isinstance(data.get("checks"), dict):
        for k, v in data["checks"].items():
            _add(tot, k, v)
        return tot
    rows = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else None
    if rows is None or not all(isinstance(r, dict) and isinstance(r.get("counts"), dict) for r in rows):
        raise ValueError("読めない形（counts を持つ辞書の列・{page@w: {counts}}・{checks: {…}} のどれか）")
    for r in rows:
        for k, v in r["counts"].items():
            _add(tot, k, v)
    return tot


def judge(counts, mapping, strict=False):
    """→ (rows, failed)。rows: [(番号, 'ok'|'ng'|'unmeasured'|'eye', 詳細)]"""
    rows, failed = [], False
    for it, cs in mapping.items():
        if not cs:
            rows.append((it, "eye", "測る検査なし（人の目）"))
            continue
        seen = [c for c in cs if c in counts]
        bad = [f"{c}×{counts[c]}" for c in seen if counts[c] > 0]
        if bad:
            rows.append((it, "ng", "、".join(bad)))
            failed = True
        elif not seen:
            rows.append((it, "unmeasured", "検査 " + "/".join(cs) + " の結果なし"))
            failed = failed or strict
        else:
            miss = [c for c in cs if c not in counts]
            rows.append((it, "ok", ("未測定の検査 " + "/".join(miss)) if miss else ""))
    return rows, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", nargs="+")
    ap.add_argument("--map")
    ap.add_argument("--strict", action="store_true", help="未測定（結果に検査の名前が無い番号）も ✗ にする")
    a = ap.parse_args(argv)
    try:
        counts = {}
        for f in a.results:
            for k, n in collect(json.loads(pathlib.Path(f).read_text(encoding="utf-8-sig"))).items():
                counts[k] = counts.get(k, 0) + n
        rows, failed = judge(counts, load_map(a.map), a.strict)
    except (OSError, ValueError, KeyError) as e:
        print(f"✗ 読めない：{e}")
        return 2
    mark = {"ok": "○", "ng": "✗", "unmeasured": "－", "eye": "・"}
    for it, st, note in rows:
        if st != "eye":
            print(f"{mark[st]} {it} {note}".rstrip())
    n_ng = sum(1 for r in rows if r[1] == "ng")
    n_un = sum(1 for r in rows if r[1] == "unmeasured")
    print(f"見た目の関所：{'✗ ' + str(n_ng) + ' 番' if n_ng else '○'}（未測定 {n_un} 番" + ("、--strict で ✗" if a.strict and n_un else "") + "）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
