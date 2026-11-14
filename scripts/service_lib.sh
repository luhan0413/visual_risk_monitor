# 背景服務管理（由 start.sh / stop.sh source）
#
#   PID 檔：run/<服務>.pid
#   Log  ：data/logs/<服務>.log
#
# 服務清單：名稱、port、啟動指令、用來確認 PID 身分的關鍵字（避免 PID 被其他程式重用時誤殺）

RUN_DIR="run"
LOG_DIR="data/logs"
PYTHON=".venv/bin/python"
SERVICES=(model_server monitor)

service_port() {
  case "$1" in
    model_server) echo 5200 ;;
    monitor) echo 5100 ;;
  esac
}

service_cmd() {
  case "$1" in
    model_server) echo "$PYTHON -m model_server.main" ;;
    monitor) echo "$PYTHON main.py" ;;
  esac
}

service_marker() {
  case "$1" in
    model_server) echo "model_server.main" ;;
    monitor) echo "main.py" ;;
  esac
}

service_health_url() {
  case "$1" in
    model_server) echo "http://127.0.0.1:5200/api/model_server/get_status" ;;
    monitor) echo "http://127.0.0.1:5100/api/monitor/get_monitor_status" ;;
  esac
}

pid_file() { echo "$RUN_DIR/$1.pid"; }

# 確認 PID 真的是本專案的這個服務（避免 PID 被重用時誤殺其他程式，
# 例如 brain-device 也是 python main.py）。三個條件都要符合：
#   1. 工作目錄是本專案
#   2. 執行檔是 python
#   3. 某個參數「完全等於」服務關鍵字
is_our_process() {
  local pid="$1" marker="$2" cwd arg
  local -a args=()
  cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null)" || return 1
  [ "$cwd" = "$(pwd -P)" ] || return 1
  mapfile -d '' args < "/proc/$pid/cmdline" 2>/dev/null || return 1
  [ "${#args[@]}" -gt 1 ] || return 1
  [[ "$(basename "${args[0]}")" == python* ]] || return 1
  for arg in "${args[@]:1}"; do
    [ "$arg" = "$marker" ] && return 0
  done
  return 1
}

# 回傳 PID（服務在執行且 PID 身分正確時），否則回傳空字串
service_pid() {
  local file pid
  file="$(pid_file "$1")"
  [ -f "$file" ] || return 0
  pid="$(cat "$file" 2>/dev/null)"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  if kill -0 "$pid" 2>/dev/null && is_our_process "$pid" "$(service_marker "$1")"; then
    echo "$pid"
  fi
}

port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

validate_target() {
  local target="$1"
  if [ "$target" = "all" ]; then
    echo "${SERVICES[@]}"
    return 0
  fi
  for name in "${SERVICES[@]}"; do
    if [ "$name" = "$target" ]; then
      echo "$name"
      return 0
    fi
  done
  echo "未知的服務：$target（可用：all ${SERVICES[*]}）" >&2
  return 1
}

start_service() {
  local name="$1" pid port
  pid="$(service_pid "$name")"
  if [ -n "$pid" ]; then
    echo "  $name 已在執行（PID $pid）"
    return 0
  fi
  rm -f "$(pid_file "$name")"

  port="$(service_port "$name")"
  if port_in_use "$port"; then
    echo "  ✗ $name 無法啟動：port $port 已被其他程式使用" >&2
    echo "    查看是誰在用：ss -ltnp 'sport = :$port'" >&2
    return 1
  fi

  mkdir -p "$RUN_DIR" "$LOG_DIR"
  echo "===== $(date '+%F %T') start =====" >> "$LOG_DIR/$name.log"
  # shellcheck disable=SC2046
  nohup $(service_cmd "$name") >> "$LOG_DIR/$name.log" 2>&1 < /dev/null &
  pid=$!
  echo "$pid" > "$(pid_file "$name")"
  echo "  $name 啟動中（PID $pid，log：$LOG_DIR/$name.log）"
}

wait_healthy() {
  local name="$1" timeout="${2:-60}" url pid
  url="$(service_health_url "$name")"
  for _ in $(seq 1 $((timeout * 2))); do
    pid="$(service_pid "$name")"
    if [ -z "$pid" ]; then
      echo "  ✗ $name 啟動失敗，最後的 log：" >&2
      tail -n 15 "$LOG_DIR/$name.log" >&2
      return 1
    fi
    if curl -sf -o /dev/null --max-time 2 "$url"; then
      echo "  ✓ $name 就緒（PID $pid，port $(service_port "$name")）"
      return 0
    fi
    sleep 0.5
  done
  echo "  ✗ $name 在 ${timeout} 秒內沒有回應，請查看 $LOG_DIR/$name.log" >&2
  return 1
}

stop_service() {
  local name="$1" pid
  pid="$(service_pid "$name")"
  if [ -z "$pid" ]; then
    echo "  $name 未在執行"
    rm -f "$(pid_file "$name")"
    return 0
  fi
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "  $name 10 秒內沒有結束，強制終止"
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$(pid_file "$name")"
  echo "===== $(date '+%F %T') stop =====" >> "$LOG_DIR/$name.log"
  echo "  $name 已停止（PID $pid）"
}

status_service() {
  local name="$1" pid health
  pid="$(service_pid "$name")"
  if [ -z "$pid" ]; then
    printf "  %-13s 停止\n" "$name"
    return 0
  fi
  if curl -sf -o /dev/null --max-time 2 "$(service_health_url "$name")"; then
    health="正常"
  else
    health="無回應"
  fi
  printf "  %-13s 執行中  PID %-8s port %-5s %s\n" "$name" "$pid" "$(service_port "$name")" "$health"
}
