import cv2
import numpy as np
from flask import Blueprint, request, send_file

import config
from routes.utils import api, get_json
from services.container import get_services

MODULE = "exemplar"

exemplar_bp = Blueprint(MODULE, __name__, url_prefix="/api/exemplar")


@exemplar_bp.route("/get_exemplars", methods=["GET"])
@api(MODULE, "get_exemplars")
def get_exemplars():
    exemplars = get_services().exemplars
    return {
        "labels": list(config.EXEMPLAR_LABELS),
        "counts": exemplars.counts(),
        "items": exemplars.list(request.args.get("label") or None),
    }


@exemplar_bp.route("/capture_exemplar", methods=["POST"])
@api(MODULE, "capture_exemplar")
def capture_exemplar():
    """把目前畫面（最近一段影格，與即時分析使用的長度相同）存成範例。"""
    services = get_services()
    data = get_json()
    label = data.get("label")
    if not label:
        raise ValueError("label is required")
    clip = services.buffer.clip(config.PIPELINE["clip_frames"])
    if not clip:
        raise ValueError("目前沒有影像，請先啟動影像來源")
    meta = {
        "source": services.sources.status().get("source_name"),
        "source_frame_index": clip[-1].index,
        "note": data.get("note", ""),
    }
    return services.exemplars.add(label, [frame.image for frame in clip], meta)


@exemplar_bp.route("/upload_exemplar", methods=["POST"])
@api(MODULE, "upload_exemplar")
def upload_exemplar():
    """上傳圖片當範例（multipart：label + 一或多個 files），每張圖片各成一個範例。"""
    label = request.form.get("label")
    if not label:
        raise ValueError("label is required")
    files = request.files.getlist("files")
    if not files:
        raise ValueError("files is required")
    created = []
    for file in files:
        image = cv2.imdecode(np.frombuffer(file.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"無法讀取圖片：{file.filename}")
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        created.append(get_services().exemplars.add(label, [rgb], {"source": "upload", "filename": file.filename}))
    return created


@exemplar_bp.route("/delete_exemplar", methods=["POST"])
@api(MODULE, "delete_exemplar")
def delete_exemplar():
    exemplar_id = get_json().get("exemplar_id")
    if not exemplar_id:
        raise ValueError("exemplar_id is required")
    get_services().exemplars.delete(exemplar_id)
    return {"exemplar_id": exemplar_id}


@exemplar_bp.route("/get_thumbnail/<exemplar_id>", methods=["GET"])
def get_thumbnail(exemplar_id):
    try:
        path = get_services().exemplars.thumbnail_path(exemplar_id)
    except (ValueError, FileNotFoundError):
        return "", 404
    return send_file(path, mimetype="image/jpeg", max_age=3600)
