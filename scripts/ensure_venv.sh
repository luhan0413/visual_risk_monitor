# 由 start*.sh source：第一次執行時建立 .venv（沿用系統已安裝的 torch）並安裝 requirements.txt
PYTHON_BIN="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
  echo "建立虛擬環境 .venv（--system-site-packages，沿用系統的 torch）…"
  "$PYTHON_BIN" -m venv --system-site-packages .venv
  .venv/bin/pip install -r requirements.txt
fi
