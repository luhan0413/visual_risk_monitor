"""
系統設定。

換串流、換模型、換評分方法、調門檻，都只改這個檔案。
有寫 "driver" 的項目，名稱必須是 drivers/loader.py 裡登記過的名稱。
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXEMPLAR_DIR = DATA_DIR / "exemplars"
VIDEO_DIR = DATA_DIR / "videos"
MODEL_DIR = BASE_DIR / "models"  # 模型權重，一個模型一個資料夾

# ============================================================
# SERVER
# ============================================================

SERVER = {
    "host": "0.0.0.0",
    "port": 5100,
}

# ============================================================
# SOURCES（影像來源）
# ============================================================

SOURCES = {
    # 串流 API：只要填 url，格式自動判斷
    #   MJPEG 串流（multipart/x-mixed-replace）、單張 JPEG（自動輪詢）、rtsp://
    # 可選參數：timeout_s（預設 5）、reconnect_s（斷線重連間隔，預設 1）
    # ⚠ 以下 url 為範例，請改成實際的串流 API
    "left_wrist": {
        "url": "http://127.0.0.1:5001/api/perception/get_camera_stream?camera_name=left",
    },
    "right_wrist": {
        "url": "http://127.0.0.1:5001/api/perception/get_camera_stream?camera_name=right",
    },
    # 回放 data/videos/ 裡的錄影（不用開手臂也能測試）
    "replay": {
        "driver": "video_file",
        "kwargs": {
            "video_dir": str(VIDEO_DIR),
            "loop": True,
        },
    },
}

DEFAULT_SOURCE = "replay"

# ============================================================
# MODEL SERVER（模型 API 服務，python -m model_server.main）
# ============================================================
# 模型只在 model server 裡載入。主系統透過 HTTP 呼叫它，
# 所以 model server 可以放在另一台 GPU 主機，主系統只要改 ENCODERS 的 base_url。

MODEL_SERVER = {
    "host": "0.0.0.0",
    "port": 5200,
    "default_model": "vjepa2_vitl",  # 啟動時自動載入；None 表示不自動載入
}

MODEL_SERVER_MODELS = {
    "vjepa2_vitl": {
        "driver": "vjepa2_hf",
        "kwargs": {
            "model_path": str(MODEL_DIR / "vjepa2-vitl-fpc64-256"),
            "device": "cuda",
            "dtype": "float16",
        },
    },
    "dummy": {
        "driver": "dummy",
        "kwargs": {},
    },
}

# ============================================================
# ENCODERS（主系統使用的特徵模型）
# ============================================================

ENCODERS = {
    # 呼叫 model server API
    "vjepa2_vitl": {
        "driver": "remote_http",
        "kwargs": {
            "base_url": "http://127.0.0.1:5200",
            "model_name": "vjepa2_vitl",  # 對應 MODEL_SERVER_MODELS 的名稱
            "timeout_s": 10.0,
            "resize_short_side": 320,  # 傳送前縮圖（模型輸入為 256），減少傳輸量
        },
    },
    # 不需要 GPU / 權重的測試用 encoder（顏色直方圖），用來驗證整條流程
    "dummy": {
        "driver": "dummy",
        "kwargs": {},
    },
}

DEFAULT_ENCODER = "vjepa2_vitl"

# ============================================================
# SCORERS（評分方法）
# ============================================================

SCORERS = {
    "knn": {
        "driver": "knn",
        "kwargs": {"k": 3},
    },
    "centroid": {
        "driver": "centroid",
        "kwargs": {},
    },
}

DEFAULT_SCORER = "knn"

# ============================================================
# EXEMPLARS（範例庫）
# ============================================================

# 分數 = 像 POSITIVE_LABEL 的程度（0～100）
POSITIVE_LABEL = "collision"
NEGATIVE_LABEL = "normal"
EXEMPLAR_LABELS = (NEGATIVE_LABEL, POSITIVE_LABEL)

# 每一類至少要有幾個範例才開始打分數
MIN_EXEMPLARS_PER_LABEL = 3

# ============================================================
# PIPELINE（即時分析）
# ============================================================

PIPELINE = {
    "capture_fps": 8.0,  # 從來源取樣的頻率
    "clip_frames": 16,  # 每次分析使用的影格數（16 張 / 8 fps = 最近 2 秒）
    "analysis_interval_s": 0.5,  # 每隔多久分析一次
    "history_size": 1200,  # 時間軸保留幾筆
    "stream_fps": 15.0,  # 網頁影像串流的更新頻率
    "stream_quality": 80,
}

# ============================================================
# RISK（分級門檻）
# ============================================================

RISK = {
    "smoothing_window": 3,  # 取最近幾次分數的平均
    "levels": [
        {"name": "LOW", "min": 0, "color": "#2e9d5b"},
        {"name": "MEDIUM", "min": 60, "color": "#e0a526"},
        {"name": "HIGH", "min": 85, "color": "#d64545"},
    ],
}

# ============================================================
# RISK API（給 brain-device 等外部系統查詢：GET /api/risk/get_risk_level）
# ============================================================

RISK_API = {
    # 最後一次分析超過這個秒數，回報 STALE（相機停住、來源斷線、分析卡住）
    "stale_after_s": 2.0,
    # 這些等級的 alert = true
    "alert_levels": ["MEDIUM", "HIGH"],
}
