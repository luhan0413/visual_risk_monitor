from flask import Blueprint, send_from_directory

from services import config_service

WEB_DIR = config_service.PROJECT_ROOT / "web"

web_bp = Blueprint("web", __name__)


@web_bp.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@web_bp.route("/collect")
def collect():
    return send_from_directory(WEB_DIR, "collect.html")


@web_bp.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(WEB_DIR / "assets", filename)
