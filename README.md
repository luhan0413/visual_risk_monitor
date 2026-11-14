# Visual Risk Monitor

以 V-JEPA 2 比對「正常」與「碰撞」範例，即時顯示畫面像碰撞的程度（0～100 分）。

> **輔助警示，不是安全功能。** 分數只代表「畫面像碰撞範例的程度」。顯示 LOW 不代表安全，
> 手臂的力矩保護與 safety range 必須保持開啟。

## 系統組成

系統分成兩個獨立的 API 服務：

```
┌───────────────────────────┐   HTTP    ┌──────────────────────────────┐
│ 主系統  main.py  :5100     │ ────────▶ │ Model Server  :5200           │
│ 網頁、影像來源、範例庫、    │  /encode  │ 載入 models/ 裡的權重，        │
│ 評分、分級、時間軸          │ ◀──────── │ 把影格轉成特徵向量             │
└───────────────────────────┘  特徵向量  └──────────────────────────────┘
```

- **Model Server**（`model_server/`）：唯一會載入模型、用到 GPU 的地方。權重只從 `models/` 讀取，不會連網下載。
- **主系統**：本身不載入模型，透過 `remote_http` encoder 呼叫 Model Server。
  Model Server 搬到另一台 GPU 主機時，只要改 `config.ENCODERS` 的 `base_url`。

## 模型權重

```
models/
  vjepa2-vitl-fpc64-256/      V-JEPA 2 ViT-L（1024 維，約 1.3 GB）
    config.json
    model.safetensors
    video_preprocessor_config.json
```

新增其他模型（例如 ViT-g）：

```bash
.venv/bin/python scripts/download_model.py --repo facebook/vjepa2-vitg-fpc64-384
```

再到 `config.MODEL_SERVER_MODELS` 新增一筆指向 `models/vjepa2-vitg-fpc64-384`，
並在 `config.ENCODERS` 新增一筆 `remote_http`，`model_name` 對應同一個名稱。

## 啟動

服務都在背景執行，關掉終端機也不會停止。

```bash
./start.sh                 # 啟動 Model Server 與主系統
./stop.sh                  # 停止全部
./restart.sh               # 兩個一起重啟
```

`./start.sh` 結束時會顯示兩個服務的狀態與 PID。

每個指令都可以指定單一服務：`model_server` 或 `monitor`，例如 `./restart.sh monitor`。
Model Server 在別台主機時，這台只執行 `./start.sh monitor`。

| 服務 | port | PID 檔 | log |
|---|---|---|---|
| model_server | 5200 | `run/model_server.pid` | `data/logs/model_server.log` |
| monitor（主系統） | 5100 | `run/monitor.pid` | `data/logs/monitor.log` |

手動 kill：`kill $(cat run/monitor.pid)`。建議用 `./stop.sh`，它會先確認 PID 真的是本系統的程式
（工作目錄與指令都要符合），避免 PID 被重用時誤殺其他程式（例如同樣是 `python main.py` 的 brain-device）。

即時看 log：`tail -f data/logs/monitor.log`

瀏覽器開啟 `http://localhost:5100`（同網段其他電腦：`http://<這台 IP>:5100`）。

## 使用流程

1. **開啟影像**：選擇來源後按「開啟」
   - `replay`：回放 `data/videos/` 裡的影片（不用開手臂就能測試）
   - `left_wrist` / `right_wrist`：串流 API（網址在 `config.SOURCES` 設定）
2. **建立範例庫**：畫面出現正常或接近碰撞的狀況時，按「存為正常範例」或「存為碰撞範例」，
   存下的是最近一段影格（預設 16 張，約 2 秒）。也可以直接上傳圖片。
3. **開始打分數**：每一類達到 3 個範例後（`MIN_EXEMPLARS_PER_LABEL`），系統會自動開始打分數。
4. **評估準確率**：範例收得差不多之後，執行離線評估（需要 Model Server 執行中），確認模型分得出兩組、門檻要設多少：

   ```bash
   .venv/bin/python scripts/evaluate_exemplars.py
   ```

## 影像來源

串流 API 只要在 `config.SOURCES` 填網址，不需要 driver：

```python
SOURCES = {
    "left_wrist": {"url": "http://<串流主機>/stream?camera=left"},
    "front_cam":  {"url": "rtsp://192.168.50.20/stream1", "timeout_s": 10},
}
```

格式自動判斷：MJPEG 串流（`multipart/x-mixed-replace`）、單張 JPEG（自動輪詢）、`rtsp://`。
背景只保留最新一張，不會累積延遲；斷線會自動重連。

## 分數與分級

```
最近 16 張影格 → V-JEPA 2 特徵 → 與範例庫比對 → 0～100 分 → 最近 3 次平均 → 分級
```

| 分數 | 等級 |
|---|---|
| < 60 | LOW |
| 60～85 | MEDIUM |
| ≥ 85 | HIGH |

分數 = 離碰撞組多近、離正常組多遠（兩組距離相等時為 50）。門檻在 `config.py` 的 `RISK` 調整。

## 架構

```
web/            網頁介面（HTML / CSS / JS，不需要建置）
routes/         主系統 API（Flask Blueprint，命名方式同 brain-device：/api/<module>/<action>）
model_server/   Model Server API（/api/model_server/<action>）
services/       業務流程：來源、模型、範例庫、評分、即時分析（兩個服務共用）
drivers/        可替換的元件，由 drivers/loader.py 依 config.py 動態載入
  sources/        http_stream（串流 API）、video_file（回放）、usb_camera
  encoders/       vjepa2_hf（本機載入權重，Model Server 用）
                  remote_http（呼叫 Model Server，主系統用）
                  dummy（測試用）
  scorers/        knn、centroid
core/           共用底層：資料型別、driver 介面、分級、緩衝區、事件
models/         模型權重
config.py       所有設定
```

上層只依賴 `core/interfaces.py` 定義的介面，所以：

| 想要… | 只需要 |
|---|---|
| 換成更大的 V-JEPA 2 | 下載權重到 `models/`，在 `config.MODEL_SERVER_MODELS` 與 `config.ENCODERS` 各加一筆 |
| 換成別的模型 | 在 `drivers/encoders/` 寫一個 `EncoderDriver`，到 `loader.py` 登記，Model Server 就能載入 |
| Model Server 搬到別台 | 改 `config.ENCODERS` 的 `base_url` |
| 換評分方法（例如訓練分類器） | 在 `drivers/scorers/` 寫一個 `ScorerDriver` |
| 加新串流 | 在 `config.SOURCES` 新增一筆 `{"url": "..."}`，不用寫程式 |
| 調門檻、取樣頻率 | 改 `config.py` 的 `RISK`、`PIPELINE` |

範例庫存的是原始影格，特徵依模型分開快取（`emb_<encoder>.npy`），換模型時會自動重算，不用重收範例。

## 範例庫

```
data/exemplars/<label>/<exemplar_id>/
    frames/000.jpg …     原始影格
    thumb.jpg            縮圖
    meta.json            來源、時間
    emb_<encoder>.npy    特徵快取
```

## API

### 風險等級查詢（給 brain-device）

```
GET http://<主系統 IP>:5100/api/risk/get_risk_level
GET http://<主系統 IP>:5100/api/risk/get_risk_level?stale_after_s=1.0
```

```json
{
  "status": "success",
  "data": {
    "level": "MEDIUM",        // LOW / MEDIUM / HIGH / NOT READY / STALE
    "score": 69.6,            // 0～100，NOT READY / STALE 時可能為 null
    "alert": true,            // level 為 MEDIUM 或 HIGH，且結果有效
    "ready": true,            // 結果是否有效
    "stale": false,           // 最後一次分析是否太舊
    "age_s": 0.17,            // 最後一次分析距今秒數
    "reason": null,           // 無效時的原因
    "source": "left_wrist",
    "nearest": {"exemplar_id": "...", "label": "collision", "distance": 0.028},
    "timestamp": 1794672438.03,
    "server_time": 1794672438.20
  }
}
```

| level | 意思 | 建議處理方式 |
|---|---|---|
| LOW | 不像碰撞範例 | 照常（**不代表安全**） |
| MEDIUM | 有點像碰撞範例 | 降速 / 提醒操作人員 |
| HIGH | 很像碰撞範例 | 暫停，等人員確認 |
| NOT READY | 來源未開、模型未就緒、範例不足、分析暫停 | 視為「不知道」 |
| STALE | 超過 `stale_after_s`（預設 2 秒）沒有新結果，例如相機凍結 | 視為「不知道」 |

`alert_levels` 與 `stale_after_s` 的預設值在 `config.RISK_API`。

brain-device 端呼叫範例：

```python
import requests

RISK_URL = "http://127.0.0.1:5100/api/risk/get_risk_level"

def get_visual_risk(timeout_s=0.5):
    """回傳 (level, alert)。查詢失敗時回傳 ("UNAVAILABLE", False)，呼叫端應視為不知道。"""
    try:
        data = requests.get(RISK_URL, timeout=timeout_s).json()["data"]
        return data["level"], data["alert"]
    except Exception:
        return "UNAVAILABLE", False
```

### Model Server（:5200）

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/model_server/get_status` | 目前模型、GPU 狀態 |
| GET | `/api/model_server/get_models` | 可用模型與權重是否存在 |
| POST | `/api/model_server/load_model` | `{"model_name": "vjepa2_vitl"}` |
| POST | `/api/model_server/unload_model` | 卸載模型 |
| POST | `/api/model_server/encode` | multipart：`frames`（JPEG，可多張，依時間排序）+ `model_name` → `{"embedding": [...], "dim": 1024}` |

其他系統（例如 brain-device）也可以直接呼叫：

```bash
curl -F model_name=vjepa2_vitl -F frames=@a.jpg -F frames=@b.jpg \
     http://localhost:5200/api/model_server/encode
```

### 主系統（:5100）

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/source/get_sources` | 可用來源與選項（例如影片清單） |
| POST | `/api/source/start_source` | `{"source_name": "replay", "options": {"video": "x.mp4"}}` |
| POST | `/api/source/stop_source` | 關閉來源 |
| GET | `/api/source/get_stream` | MJPEG 影像串流 |
| GET | `/api/model/get_model_status` | 模型與評分狀態 |
| POST | `/api/model/select_encoder` | `{"encoder_name": "vjepa2_vitl"}` |
| POST | `/api/model/select_scorer` | `{"scorer_name": "knn"}` |
| GET | `/api/exemplar/get_exemplars` | 範例清單 |
| POST | `/api/exemplar/capture_exemplar` | `{"label": "collision"}`，存目前畫面 |
| POST | `/api/exemplar/upload_exemplar` | multipart：`label` + `files` |
| POST | `/api/exemplar/delete_exemplar` | `{"exemplar_id": "..."}` |
| GET | `/api/monitor/get_events` | SSE，即時推送每次分析結果 |
| GET | `/api/monitor/get_history` | 本次時間軸資料 |

## 測試

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

測試使用假的影像來源和 dummy encoder，不需要相機與 GPU。
