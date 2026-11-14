from flask import Blueprint, request, send_file

from routes.utils import api, get_json
from services.container import get_services

MODULE = "exemplar"

exemplar_bp = Blueprint(MODULE, __name__, url_prefix="/api/exemplar")


@exemplar_bp.route("/get_exemplars", methods=["GET"])
@api(MODULE, "get_exemplars")
def get_exemplars():
    return get_services().exemplars.summary(request.args.get("label"))


@exemplar_bp.route("/capture_exemplar", methods=["POST"])
@api(MODULE, "capture_exemplar")
def capture_exemplar():
    """把目前畫面存成範例：{"label": "collision", "note": "..."}"""
    data = get_json()
    if not data.get("label"):
        raise ValueError("label is required")
    return get_services().capture.capture_current(data["label"], data.get("note", ""))


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
