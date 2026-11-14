#!/usr/bin/env bash
# 在背景啟動服務，PID 記在 run/<服務>.pid，log 在 data/logs/<服務>.log
#
#   ./start.sh                 啟動 Model Server（:5200）與主系統（:5100）
#   ./start.sh model_server    只啟動 Model Server（部署到 GPU 主機時）
#   ./start.sh monitor         只啟動主系統（Model Server 在別台時）
set -euo pipefail
cd "$(dirname "$0")"
source scripts/ensure_venv.sh
source scripts/service_lib.sh

target="${1:-all}"
if [ "${SKIP_MODEL_SERVER:-0}" = "1" ] && [ "$target" = "all" ]; then
  target="monitor"  # 舊用法相容
fi
names="$(validate_target "$target")"

echo "啟動服務："
failed=0
for name in $names; do
  if start_service "$name"; then
    # model server 先就緒再啟動主系統（主系統啟動時會連線 model server）
    wait_healthy "$name" 60 || failed=1
  else
    failed=1
  fi
done

echo
echo "服務狀態："
for name in "${SERVICES[@]}"; do
  status_service "$name"
done
if [[ " $names " == *" monitor "* ]] && [ "$failed" = 0 ]; then
  echo
  echo "監控網頁：http://localhost:5100"
fi
echo "停止：./stop.sh   重啟：./restart.sh"
exit "$failed"
