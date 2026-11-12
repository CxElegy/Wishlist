#!/usr/bin/env bash
# CI と同じ検査を、コミットした中身そのままで手元の Linux コンテナで流す（2026-11-07，店長「失敗をなくして」）。
# Windows だけの赤（test_free_tier_gate など）に惑わされず、CI の結果を push の前に知る。
#   bash harness/ci_local.sh            # コンテナが動かない PC では失敗として止まる（push を --no-verify で通さない）
#   bash harness/ci_local.sh test_wall_shapes test_gate_ripe   # 名前を言えば、その試験だけ（同じ合併した形・同じコンテナで）。落ちた試験だけの流し直しに使う
#   bash harness/ci_local.sh --affected   # origin/main から変わったファイルに当たる試験だけ（harness/affected.py が決める。分からない時は全部）＋網页の生成と JS。pre-push の ④ がこれ
#   bash harness/ci_local.sh --fast       # 上のうち、ブラウザを使わない試験だけ（軽い検査を先に。網页の生成は飛ばす）
# 終了コード：0 緑／1 赤／3 赤は「負荷で落ちる基盤の不安定」だけ（Playwright の goto・起動の時間切れなど。harness/run_tests.py が分ける）。
# 2026-11-12 run 1112b：ほかの係の ci_local.sh が鍵なしで同時に走り、test_wall_shapes が Page.goto 30 秒切れ → 合併 0 件。
# だから CI のコンテナは、この台本が自分で鍵（harness/lock.py ci）を取って 1 つずつ。鍵を持たない古い台本のコンテナが動いていれば、終わるまで待つ。
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1
py=""
for c in "${HF_PYTHON:-}" .venv/Scripts/python.exe D:/Claude/Wishlist/.venv/Scripts/python.exe python3 python; do
  [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && { py=$c; break; }
done
if [ -z "${HF_LOCK_CI:-}" ]; then
  if [ -n "$py" ] && "$py" -c "import sys; sys.path.insert(0, 'harness'); import lock" >/dev/null 2>&1; then
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' PYTHONIOENCODING=utf-8 "$py" harness/lock.py ci --wait "${CI_LOCK_WAIT:-2400}" -- bash "$0" "$@"
    exit $?
  fi
  echo "（鍵を取る python が無い：鍵なしで流す）"
fi
# --affected / --fast：当たる試験の名前に置き換える（ALL＝全部なら引数なしと同じ＝緑の印も残る。空なら流す物が無い）
pages=0
if [ "${1:-}" = --affected ] || [ "${1:-}" = --fast ]; then
  sel=ALL
  git fetch -q origin main 2>/dev/null
  if [ -n "$py" ]; then
    flag=""; [ "$1" = --fast ] && flag=--fast
    sel=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE PYTHONIOENCODING=utf-8 "$py" harness/affected.py --base origin/main --names $flag 2>/dev/null) || sel=ALL
  fi
  [ "$1" = --affected ] && pages=1
  if [ "$sel" = ALL ]; then
    [ "$1" = --fast ] && { echo "✗ fast の試験の名前が取れない（harness/affected.py）"; exit 1; }
    echo "当たる試験：全部（分からない・試験の流し方が変わった。harness/affected.py）"
    set --
  elif [ -z "$sel" ]; then
    echo "✓ 当たる試験なし（文章・絵だけ。harness/affected.py）"
    exit 0
  else
    # shellcheck disable=SC2086
    set -- $sel
    echo "当たる試験 $# 本（harness/affected.py。全部は GitHub の CI が流す）：$*"
  fi
fi
image=wishlist-ci
if command -v docker >/dev/null 2>&1; then
  for i in $(seq 1 "${CI_FOREIGN_WAIT:-120}"); do   # 鍵を使わない古い台本・別の作業ツリーのコンテナ（10 秒 × 既定 120 回＝20 分まで待つ）
    [ "$(docker ps --format '{{.Image}}' 2>/dev/null | grep -c "^$image")" = 0 ] && break
    [ "$i" = 1 ] && echo "ほかの CI のコンテナが動いている：終わるまで待つ"
    sleep 10
  done
fi
stamp=$(git hash-object requirements.txt harness/ci.Dockerfile | tr -d '\n' | cut -c1-12)
if ! docker image inspect "$image:$stamp" >/dev/null 2>&1; then
  echo "検査の環境を作る（初回だけ数分）"
  docker build -q -t "$image:$stamp" -f harness/ci.Dockerfile . >/dev/null || { echo "✗ 検査の環境を作れない"; exit 1; }
fi
# CI は PR を「main と合併した形」で試す。手元も同じ形で試す（2026-11-09：枝が古い main のままで手元は緑、CI だけ test_wall_shapes が赤になった）
git fetch -q origin main 2>/dev/null
tree=HEAD
if git rev-parse -q --verify origin/main >/dev/null && ! git merge-base --is-ancestor origin/main HEAD; then
  if m=$(git merge-tree --write-tree origin/main HEAD 2>/dev/null | head -1) && [ -n "$m" ]; then tree=$m; echo "main と合併した形で試す"
  else echo "✗ main と競合する：先に main を取り込む"; exit 1; fi
fi
git archive "$tree" | docker run --rm -i -e TEST_JOBS="${TEST_JOBS:-8}" -e PAGES="$pages" "$image:$stamp" bash -c '
  mkdir /w && cd /w && tar x
  git init -q && git add -A >/dev/null && git -c user.name=ci -c user.email=ci@example.com commit -qm ci
  python -c "import sys; sys.path.insert(0, \"scripts\"); import digest; digest.load_config(); digest.load_wishlist()" || exit 1
  python harness/run_tests.py "$@"; rc=$?; [ $rc = 0 ] || exit $rc
  [ $# -gt 0 ] && [ "$PAGES" != 1 ] && { echo "✓ 選んだ試験が緑：$*"; exit 0; }
  python scripts/digest.py render >/dev/null && test -s docs/home/index.html || { echo "✗ 網页が生成できない"; exit 1; }
  python harness/js_check.py docs/home docs/index.html || exit 1
  python harness/page_errors.py home/index.html index.html || exit 1
  [ $# -gt 0 ] && { echo "✓ 当たる試験と網页の生成が緑（$# 本。全部は GitHub の CI）"; exit 0; }
  echo "✓ CI と同じ検査が緑"
' ci "$@"
rc=$?
# 全部緑（引数なし）なら、この中身（tree の指紋）の緑の印を残す。pre-push の ④ が同じ中身なら流さない。赤・3・一部だけの試験は残さない
if [ "$rc" = 0 ] && [ $# = 0 ]; then
  green_dir="${HF_CI_GREEN_DIR:-}"
  [ -z "$green_dir" ] && [ -d D:/Claude/hf/state ] && green_dir=D:/Claude/hf/state/ci_green
  if [ -n "$green_dir" ] && mkdir -p "$green_dir" 2>/dev/null; then
    head_tree=$(git rev-parse 'HEAD^{tree}' 2>/dev/null) && [ -n "$head_tree" ] && date +%s > "$green_dir/$head_tree" 2>/dev/null && echo "緑の印を残した：$green_dir/$head_tree"
  fi
fi
exit $rc
