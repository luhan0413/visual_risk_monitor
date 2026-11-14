from flask import Blueprint

from routes.utils import api, get_json
from services.container import get_services

MODULE = "model"

model_bp = Blueprint(MODULE, __name__, url_prefix="/api/model")


@model_bp.route("/get_model_status", methods=["GET"])
@api(MODULE, "get_model_status")
def get_model_status():
    return get_services().model_status()


@model_bp.route("/select_encoder", methods=["POST"])
@api(MODULE, "select_encoder")
def select_encoder():
    name = get_json().get("encoder_name")
    if not name:
        raise ValueError("encoder_name is required")
    return get_services().encoders.select(name, background=True)


@model_bp.route("/select_scorer", methods=["POST"])
@api(MODULE, "select_scorer")
def select_scorer():
    name = get_json().get("scorer_name")
    if not name:
        raise ValueError("scorer_name is required")
    return get_services().scoring.select(name)
