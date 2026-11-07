#!/usr/bin/env bash
# コミットした中身でページを作り、コンテナの中で自己点検する（harness/self_review.py）。→ <出力先>/review.png
#   bash harness/self_review.sh <出力先の絶対パス> [--page home/index.html ...]
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1
out=$1; shift
image=wishlist-ci:$(git hash-object requirements.txt harness/ci.Dockerfile | tr -d '\n' | cut -c1-12)
docker image inspect "$image" >/dev/null 2>&1 || docker build -q -t "$image" -f harness/ci.Dockerfile . >/dev/null || exit 1
git archive HEAD | MSYS_NO_PATHCONV=1 docker run --rm -i -v "$out:/out" "$image" bash -c '
  mkdir /w && cd /w && tar x
  git init -q && git add -A >/dev/null && git -c user.name=ci -c user.email=ci@example.com commit -qm ci
  python scripts/digest.py render >/dev/null || exit 2
  python harness/self_review.py --dir docs --out /out "$@"
' _ "$@"
