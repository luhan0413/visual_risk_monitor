"""
Model Server：把模型推論包成 API。

    python -m model_server.main          （在專案根目錄執行）

模型清單在 config.MODEL_SERVER_MODELS，權重放在 models/。
計算都在 model_server/service.py；這裡只定義 API。

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

from flask import Blueprint, Flask, request  # noqa: E402

from model_server.service import ModelServerService, build_service  # noqa: E402
from routes.utils import api, get_json  # noqa: E402
from services import config_service as cfg  # noqa: E402

MODULE = "model_server"


def create_app(service: ModelServerService) -> Flask:
    bp = Blueprint(MODULE, __name__, url_prefix=f"/api/{MODULE}")

    @bp.route("/get_status", methods=["GET"])
    @api(MODULE, "get_status")
    def get_status():
        return service.status()

    @bp.route("/get_models", methods=["GET"])
    @api(MODULE, "get_models")
    def get_models():
        return service.models()

    @bp.route("/load_model", methods=["POST"])
    @api(MODULE, "load_model")
    def load_model():
        name = get_json().get("model_name")
        if not name:
            raise ValueError("model_name is required")
        return service.load(name)

    @bp.route("/unload_model", methods=["POST"])
    @api(MODULE, "unload_model")
    def unload_model():
        return service.unload()

    @bp.route("/encode", methods=["POST"])
    @api(MODULE, "encode")
    def encode():
        files = [(file.filename, file.read()) for file in request.files.getlist("frames")]
        if not files:
            raise ValueError("frames is required")
        return service.encode(files, request.form.get("model_name"))

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_upload_bytes("MODEL_SERVER")
    app.register_blueprint(bp)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for problem in cfg.validate():
        logging.warning("設定問題：%s", problem)
    service = build_service()
    settings = cfg.get("MODEL_SERVER")
    if settings.get("default_model"):
        service.load(settings["default_model"])
    create_app(service).run(host=settings["host"], port=settings["port"], debug=False, threaded=True)


if __name__ == "__main__":
    main()
