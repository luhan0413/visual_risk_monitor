"""
Model Server：把模型推論包成 API。

    python -m model_server.main          （在專案根目錄執行）

模型權重從 config.MODEL_DIR（models/）讀取，模型清單在 config.MODEL_SERVER_MODELS。
與主系統共用 drivers/encoders 與 services/encoder_service，所以新增模型只要寫 driver + 改設定。

API（/api/model_server/...）：
    GET  get_status     目前模型狀態
    GET  get_models     可用模型與權重是否齊全
    POST load_model     {"model_name": "vjepa2_vitl"}
    POST unload_model
    POST encode         multipart：frames（依時間排序的 JPEG，可多張）+ model_name
                        → {"embedding": [...], "dim": 1024, "latency_ms": 80.1}
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from flask import Blueprint, Flask, request  # noqa: E402

import config  # noqa: E402
from drivers import loader  # noqa: E402
from routes.utils import api, get_json  # noqa: E402
from services.encoder_service import EncoderService  # noqa: E402

MODULE = "model_server"
MAX_FRAMES = 64

logger = logging.getLogger(__name__)


def _model_entries() -> list[dict]:
    items = []
    for name, entry in config.MODEL_SERVER_MODELS.items():
        model_path = (entry.get("kwargs") or {}).get("model_path")
        items.append({
            "name": name,
            "driver": entry["driver"],
            "model_path": model_path,
            "weights_found": None if model_path is None else Path(model_path).is_dir(),
        })
    return items


def _gpu_info() -> dict:
    try:
        import torch

        if torch.cuda.is_available():
            return {"cuda": True, "device": torch.cuda.get_device_name(0)}
        return {"cuda": False}
    except ImportError:
        return {"cuda": False, "torch": "not installed"}


def create_app(encoders: EncoderService) -> Flask:
    bp = Blueprint(MODULE, __name__, url_prefix=f"/api/{MODULE}")

    @bp.route("/get_status", methods=["GET"])
    @api(MODULE, "get_status")
    def get_status():
        return {"model": encoders.status(), "models_dir": str(config.MODEL_DIR), "gpu": _gpu_info()}

    @bp.route("/get_models", methods=["GET"])
    @api(MODULE, "get_models")
    def get_models():
        return _model_entries()

    @bp.route("/load_model", methods=["POST"])
    @api(MODULE, "load_model")
    def load_model():
        name = get_json().get("model_name")
        if not name:
            raise ValueError("model_name is required")
        return encoders.select(name, background=True)

    @bp.route("/unload_model", methods=["POST"])
    @api(MODULE, "unload_model")
    def unload_model():
        return encoders.unload()

    @bp.route("/encode", methods=["POST"])
    @api(MODULE, "encode")
    def encode():
        name = request.form.get("model_name")
        if name and name != encoders.name:
            raise RuntimeError(f"目前載入的模型是 {encoders.name}，不是 {name}")
        files = request.files.getlist("frames")
        if not files:
            raise ValueError("frames is required")
        if len(files) > MAX_FRAMES:
            raise ValueError(f"frames 最多 {MAX_FRAMES} 張")
        frames = []
        for file in files:
            image = cv2.imdecode(np.frombuffer(file.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"無法解碼影像：{file.filename}")
            frames.append(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        vector = encoders.encode(frames)
        return {
            "model_name": encoders.name,
            "embedding": vector.tolist(),
            "dim": int(vector.shape[0]),
            "frames": len(frames),
            "latency_ms": encoders.status()["last_latency_ms"],
        }

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
    app.register_blueprint(bp)
    return app


def build_encoder_service() -> EncoderService:
    return EncoderService(factory=lambda name: loader.create_encoder(name, config.MODEL_SERVER_MODELS))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    encoders = build_encoder_service()
    default = config.MODEL_SERVER.get("default_model")
    if default:
        encoders.select(default, background=True)
    app = create_app(encoders)
    app.run(host=config.MODEL_SERVER["host"], port=config.MODEL_SERVER["port"], debug=False, threaded=True)


if __name__ == "__main__":
    main()
