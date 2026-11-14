#!/usr/bin/env bash
# 重新啟動服務（預設兩個系統一起）
#
#   ./restart.sh               重啟 Model Server 與主系統
#   ./restart.sh model_server  只重啟 Model Server
#   ./restart.sh monitor       只重啟主系統
set -euo pipefail
cd "$(dirname "$0")"

./stop.sh "${1:-all}"
echo
exec ./start.sh "${1:-all}"
