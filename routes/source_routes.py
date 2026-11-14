from flask import Blueprint, Response

from routes.utils import api, get_json
from services.container import get_services

MODULE = "source"

source_bp = Blueprint(MODULE, __name__, url_prefix="/api/source")


@source_bp.route("/get_sources", methods=["GET"])
@api(MODULE, "get_sources")
def get_sources():
    return get_services().sources.list_sources()


@source_bp.route("/get_source_status", methods=["GET"])
@api(MODULE, "get_source_status")
def get_source_status():
    return get_services().sources.status()


@source_bp.route("/start_source", methods=["POST"])
@api(MODULE, "start_source")
def start_source():
    data = get_json()
    source_name = data.get("source_name")
    if not source_name:
        raise ValueError("source_name is required")
    return get_services().sources.start(source_name, data.get("options") or {})


@source_bp.route("/stop_source", methods=["POST"])
@api(MODULE, "stop_source")
def stop_source():
    return get_services().sources.stop()


@source_bp.route("/get_stream", methods=["GET"])
def get_stream():
    return Response(
        get_services().sources.mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@source_bp.route("/get_snapshot", methods=["GET"])
def get_snapshot():
    jpeg = get_services().sources.latest_jpeg(quality=90)
    if jpeg is None:
        return Response(status=204)
    return Response(jpeg, mimetype="image/jpeg")
