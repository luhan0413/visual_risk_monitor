import json
import queue

from flask import Blueprint, Response, stream_with_context

from routes.utils import api
from services import config_service
from services.container import get_services

MODULE = "monitor"

monitor_bp = Blueprint(MODULE, __name__, url_prefix="/api/monitor")


@monitor_bp.route("/get_monitor_config", methods=["GET"])
@api(MODULE, "get_monitor_config")
def get_monitor_config():
    return config_service.monitor_config()


@monitor_bp.route("/get_monitor_status", methods=["GET"])
@api(MODULE, "get_monitor_status")
def get_monitor_status():
    return get_services().monitor.status()


@monitor_bp.route("/get_history", methods=["GET"])
@api(MODULE, "get_history")
def get_history():
    return get_services().monitor.history()


@monitor_bp.route("/start_monitor", methods=["POST"])
@api(MODULE, "start_monitor")
def start_monitor():
    return get_services().monitor.start()


@monitor_bp.route("/stop_monitor", methods=["POST"])
@api(MODULE, "stop_monitor")
def stop_monitor():
    return get_services().monitor.stop()


@monitor_bp.route("/reset_history", methods=["POST"])
@api(MODULE, "reset_history")
def reset_history():
    get_services().monitor.reset()
    return True


@monitor_bp.route("/get_events", methods=["GET"])
def get_events():
    """Server-Sent Events：即時推送每次分析結果。"""
    events = get_services().events

    def generate():
        subscription = events.subscribe()
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    event, data = subscription.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        finally:
            events.unsubscribe(subscription)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
