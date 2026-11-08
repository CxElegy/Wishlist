#!/usr/bin/env bash
# CI と同じ検査を、コミットした中身そのままで手元の Linux コンテナで流す（2026-11-07，店長「失敗をなくして」）。
# Windows だけの赤（test_free_tier_gate など）に惑わされず、CI の結果を push の前に知る。
#   bash harness/ci_local.sh            # コンテナが動かない PC では失敗として止まる（push を --no-verify で通さない）
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1
image=wishlist-ci
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
git archive "$tree" | docker run --rm -i -e TEST_JOBS="${TEST_JOBS:-8}" "$image:$stamp" bash -c '
  mkdir /w && cd /w && tar x
  git init -q && git add -A >/dev/null && git -c user.name=ci -c user.email=ci@example.com commit -qm ci
  python -c "import sys; sys.path.insert(0, \"scripts\"); import digest; digest.load_config(); digest.load_wishlist()" || exit 1
  python harness/run_tests.py || exit 1
  python scripts/digest.py render >/dev/null && test -s docs/home/index.html || { echo "✗ 網页が生成できない"; exit 1; }
  python harness/js_check.py docs/home docs/index.html || exit 1
  python harness/page_errors.py home/index.html index.html || exit 1
  echo "✓ CI と同じ検査が緑"
'
