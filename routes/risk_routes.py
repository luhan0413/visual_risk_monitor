"""
給 brain-device 等外部系統查詢目前風險等級。

    GET /api/risk/get_risk_level
    GET /api/risk/get_risk_level?stale_after_s=1.0

輔助警示：level 為 NOT READY 或 STALE 時代表「不知道」，呼叫端不能當作安全。
"""
from flask import Blueprint, request

import config
from routes.utils import api
from services.container import get_services

MODULE = "risk"

risk_bp = Blueprint(MODULE, __name__, url_prefix="/api/risk")


@risk_bp.route("/get_risk_level", methods=["GET"])
@api(MODULE, "get_risk_level")
def get_risk_level():
    stale_after_s = config.RISK_API["stale_after_s"]
    if "stale_after_s" in request.args:
        try:
            stale_after_s = float(request.args["stale_after_s"])
        except ValueError as exc:
            raise ValueError("stale_after_s must be a number") from exc
        if stale_after_s <= 0:
            raise ValueError("stale_after_s must be > 0")
    return get_services().monitor.current_risk(stale_after_s, config.RISK_API["alert_levels"])
