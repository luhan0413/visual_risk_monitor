from flask import Blueprint, send_from_directory

import config

WEB_DIR = config.BASE_DIR / "web"

web_bp = Blueprint("web", __name__)


@web_bp.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@web_bp.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(WEB_DIR / "assets", filename)
