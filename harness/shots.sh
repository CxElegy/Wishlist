#!/usr/bin/env bash
# コミットした中身でページを作り、コンテナの中で絵を撮る（harness/shots.py）と自己点検（harness/self_review.py）。→ <出力先>/*.png・shots.json・review.json
#   bash harness/shots.sh <出力先の絶対パス> --page home/index.html --sel "#sec-bleach"
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1
out=$1; shift
image=wishlist-ci:$(git hash-object requirements.txt harness/ci.Dockerfile | tr -d '\n' | cut -c1-12)
docker image inspect "$image" >/dev/null 2>&1 || docker build -q -t "$image" -f harness/ci.Dockerfile . >/dev/null || exit 1
git archive HEAD | MSYS_NO_PATHCONV=1 docker run --rm -i -v "$out:/out" "$image" bash -c '
  mkdir /w && cd /w && tar x
  git init -q && git add -A >/dev/null && git -c user.name=ci -c user.email=ci@example.com commit -qm ci
  python scripts/digest.py render >/dev/null || exit 2
  python harness/shots.py --dir docs --out /out "$@"; s=$?
  pages=(); while [ $# -gt 0 ]; do [ "$1" = --page ] && pages+=(--page "$2"); shift; done
  python harness/self_review.py --dir docs --out /out "${pages[@]}"; r=$?
  [ $s = 0 ] && [ $r = 0 ]
' _ "$@"
