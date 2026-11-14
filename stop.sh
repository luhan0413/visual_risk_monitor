#!/usr/bin/env bash
# 停止背景服務（依 run/<服務>.pid）
#
#   ./stop.sh                  停止全部
#   ./stop.sh model_server     只停止 Model Server
#   ./stop.sh monitor          只停止主系統
set -euo pipefail
cd "$(dirname "$0")"
source scripts/service_lib.sh

names="$(validate_target "${1:-all}")"

echo "停止服務："
# 反向停止：先停主系統，再停 model server
for name in $(echo "$names" | tr ' ' '\n' | tac); do
  stop_service "$name"
done
