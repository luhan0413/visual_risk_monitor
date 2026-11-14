"""
給 brain-device 等外部系統查詢目前風險等級。

    GET /api/risk/get_risk_level
    GET /api/risk/get_risk_level?stale_after_s=1.0

輔助警示：level 為 NOT READY 或 STALE 時代表「不知道」，呼叫端不能當作安全。
"""
from flask import Blueprint, request

from routes.utils import api
from services.container import get_services

MODULE = "risk"

risk_bp = Blueprint(MODULE, __name__, url_prefix="/api/risk")


@risk_bp.route("/get_risk_level", methods=["GET"])
@api(MODULE, "get_risk_level")
def get_risk_level():
    stale_after_s = request.args.get("stale_after_s", type=float)
    if "stale_after_s" in request.args and stale_after_s is None:
        raise ValueError("stale_after_s must be a number")
    return get_services().monitor.current_risk(stale_after_s)
