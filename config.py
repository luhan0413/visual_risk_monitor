"""
系統設定：只放「值」，不做任何計算。改完執行 ./restart.sh 生效。

讀取與計算（例如路徑解析、套用預設值）都在 services/config_service.py。
路徑一律寫成相對於專案根目錄的字串（也可以寫絕對路徑）。

目錄
    1. 風險分數與分級    SCORERS、RISK、RISK_API          ← 最常調整
    2. 影像來源          SOURCES、DEFAULT_SOURCE、STREAM_DEFAULTS
    3. 即時分析          PIPELINE
    4. 範例庫            EXEMPLARS
    5. 模型              MODEL_SERVER、MODEL_SERVER_MODELS、ENCODERS
    6. 服務與網頁        SERVER、UI、SERVICE
    7. 路徑              PATHS

有寫 "driver" 的項目，名稱必須是 drivers/loader.py 裡登記過的名稱。
"""

# ============================================================
# 1. 風險分數與分級
# ============================================================
#
#   最近一段影格 → 特徵 → 與範例庫比對 → 原始分數 0～100 → 平滑 → 分級
#
# 原始分數 = 100 × d_normal^s / (d_normal^s + d_collision^s)
#   d_normal     與「正常」範例的距離
#   d_collision  與「碰撞」範例的距離
#   s            sharpness（銳利度）
#   兩邊一樣近時為 50；越像碰撞越接近 100。

# 評分方法
#   k          kNN 參考最近的幾個範例。範例多時可調大，較不受單一範例影響
#   sharpness  1 = 線性；調大分數更快往 0 或 100 靠（兩組差異小時較容易拉開），
#              調小則分數更集中在 50 附近。建議範圍 0.5～4
SCORERS = {
    "knn": {
        "driver": "knn",
        "kwargs": {"k": 3, "sharpness": 1.0},
    },
    "centroid": {
        "driver": "centroid",
        "kwargs": {"sharpness": 1.0},
    },
}

DEFAULT_SCORER = "knn"

RISK = {
    # 最終分數 = 最近幾次原始分數的平均。調大較穩定但反應較慢（每次間隔見 PIPELINE）
    "smoothing_window": 3,
    # 分級門檻：分數 >= min 即為該等級
    "levels": [
        {"name": "LOW", "min": 0, "color": "#2e9d5b"},
        {"name": "MEDIUM", "min": 60, "color": "#e0a526"},
        {"name": "HIGH", "min": 85, "color": "#d64545"},
    ],
    # 無法判斷時（來源未開、範例不足…）顯示的顏色
    "not_ready_color": "#8a8f98",
}

# 給 brain-device 等外部系統查詢：GET /api/risk/get_risk_level
RISK_API = {
    # 最後一次分析超過這個秒數，回報 STALE（相機停住、來源斷線、分析卡住）
    "stale_after_s": 2.0,
    # 這些等級的 alert = true
    "alert_levels": ["MEDIUM", "HIGH"],
}

# ============================================================
# 2. 影像來源
# ============================================================

SOURCES = {
    # 每個相機兩個 API：
    #   url           串流，用來即時分析。格式自動判斷：MJPEG 串流、單張 JPEG（自動輪詢）、rtsp://
    #   snapshot_url  拍照，收集範例時按「拍照」會呼叫它取得一張照片（回傳 JPEG / PNG）
    #                 沒有填的來源，拍照時改存目前串流畫面
    # 也可以個別覆寫 STREAM_DEFAULTS 的項目，例如 {"url": "...", "timeout_s": 10}
    "left_wrist": {
        "url": "http://192.168.50.148:5001/api/perception/get_camera_stream?camera_name=left",
        "snapshot_url": "http://192.168.50.148:5001/api/perception/get_camera_image?camera_name=left",
    },
    "right_wrist": {
        "url": "http://192.168.50.148:5001/api/perception/get_camera_stream?camera_name=right",
        "snapshot_url": "http://192.168.50.148:5001/api/perception/get_camera_image?camera_name=right",
    },
    # 回放 data/videos/ 裡的錄影（不用開手臂也能測試）
    "replay": {
        "driver": "video_file",
        "kwargs": {
            "video_dir": "data/videos",
            "loop": True,
        },
    },
}

# 網頁打開時預先選擇的來源
DEFAULT_SOURCE = "replay"

# 串流 API 來源的預設參數
STREAM_DEFAULTS = {
    "timeout_s": 5.0,  # 連線 / 第一張影像的等待時間
    "reconnect_s": 1.0,  # 斷線後多久重連
    "snapshot_fps": 15.0,  # 串流 API 回傳單張 JPEG 時，每秒抓幾張
}

# 拍照 API（snapshot_url）
SNAPSHOT = {
    "timeout_s": 5.0,  # 等待拍照 API 回應的時間
}

# ============================================================
# 3. 即時分析
# ============================================================

PIPELINE = {
    # 系統啟動後是否自動開始分析。False = 要在網頁按「開始分析」
    "autostart_analysis": False,
    # 從串流取樣的頻率。需 >= 分析頻率，且建議低於串流實際 fps（約 14～30），避免重複取到同一張
    "capture_fps": 10.0,
    # 每次分析使用的影格數。1 = 單張照片，與拍照 API 存下的範例格式一致
    #（改成多張會帶入動作資訊，但範例也必須改成連續影格才能公平比對）
    "clip_frames": 1,
    # 每隔多久分析一次。0.2 秒 = 每秒 5 次（單張分析約 50～65 ms，保留充足餘裕）
    "analysis_interval_s": 0.2,
    "history_size": 3000,  # 時間軸保留幾筆（3000 × 0.2 秒 = 10 分鐘）
    "frame_buffer_size": 8,  # 影格緩衝區大小，需 >= clip_frames
    "stream_fps": 15.0,  # 網頁影像串流的更新頻率
    "stream_quality": 80,  # 網頁影像串流的 JPEG 品質
}

# ============================================================
# 4. 範例庫
# ============================================================

EXEMPLARS = {
    # 分數 = 像 positive 的程度
    "positive_label": "collision",
    "negative_label": "normal",
    # 網頁上顯示的名稱
    "display_names": {"normal": "正常", "collision": "碰撞"},
    # 每一類至少要有幾個範例才開始打分數
    "min_per_label": 3,
    # 儲存格式
    "frame_jpeg_quality": 95,
    "thumbnail_size": 240,  # 縮圖長邊像素
    "thumbnail_jpeg_quality": 85,
}

# ============================================================
# 5. 模型
# ============================================================

# Model Server（python -m model_server.main）：唯一載入模型、使用 GPU 的服務
MODEL_SERVER = {
    "host": "0.0.0.0",
    "port": 5200,
    "default_model": "vjepa2_vitl",  # 啟動時自動載入；None 表示不自動載入
    "max_frames_per_request": 64,
    "max_upload_mb": 64,
}

# Model Server 可載入的模型（權重放在 models/ 底下）
MODEL_SERVER_MODELS = {
    "vjepa2_vitl": {
        "driver": "vjepa2_hf",
        "kwargs": {
            "model_path": "models/vjepa2-vitl-fpc64-256",
            "device": "cuda",
            "dtype": "float16",
        },
    },
}

# 主系統使用的特徵模型
ENCODERS = {
    # 透過 API 呼叫 Model Server
    "vjepa2_vitl": {
        "driver": "remote_http",
        "kwargs": {
            # Model Server 的位址；搬到別台 GPU 主機時改這裡
            "base_url": "http://127.0.0.1:5200",
            "model_name": "vjepa2_vitl",  # 對應 MODEL_SERVER_MODELS 的名稱
            "timeout_s": 10.0,
            "resize_short_side": 320,  # 傳送前縮圖（模型輸入為 256），減少傳輸量
            "jpeg_quality": 90,
        },
    },
}

DEFAULT_ENCODER = "vjepa2_vitl"

# ============================================================
# 6. 服務與網頁
# ============================================================

# 主系統（main.py）
SERVER = {
    "host": "0.0.0.0",
    "port": 5100,
    "max_upload_mb": 64,  # 單一請求的大小上限
}

# 網頁
UI = {
    "timeline_window_s": 120,  # 時間軸顯示最近幾秒
    "status_poll_ms": 2000,  # 狀態更新頻率
    "toast_ms": 3500,  # 提示訊息顯示時間
}

# 背景服務管理（start.sh / stop.sh / restart.sh）
SERVICE = {
    "start_timeout_s": 60,  # 啟動後等待服務回應的時間
    "stop_timeout_s": 10,  # 停止時等待正常結束的時間，超過則強制終止
}

# ============================================================
# 7. 路徑（相對於專案根目錄）
# ============================================================

PATHS = {
    "exemplars": "data/exemplars",
    "videos": "data/videos",
    "logs": "data/logs",
    "models": "models",
}
