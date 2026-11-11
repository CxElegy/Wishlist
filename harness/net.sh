#!/usr/bin/env bash
# 網の命令（git fetch / push・gh）を、落ちたら間をあけてやり直す（ハーネス v2。GitHub が不安定な日に係が止まらないように）。
#   bash harness/net.sh git push --no-verify -u origin harness/T-0003
#   bash harness/net.sh gh pr create …
# 5 回まで（10 秒 → 30 秒 → 60 秒 → 120 秒）。1 回は 5 分で打ち切る。最後まで落ちたらその終了コードで返す。
set -u
n=0
for wait in 10 30 60 120 0; do
  n=$((n + 1))
  timeout "${NET_TIMEOUT:-300}" "$@" && exit 0
  code=$?
  [ "$wait" = 0 ] && break
  echo "net.sh：$n 回目が落ちた（$code）。${NET_WAIT:-$wait} 秒あけてやり直す" >&2
  sleep "${NET_WAIT:-$wait}"
done
echo "net.sh：$n 回とも落ちた（$code）：$*" >&2
exit "$code"
