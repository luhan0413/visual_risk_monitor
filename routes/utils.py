"""Route 共用工具。"""
from __future__ import annotations

import functools
import logging

from flask import jsonify, request

from utils import response

logger = logging.getLogger(__name__)


def get_json() -> dict:
    return request.get_json(silent=True) or {}


def api(module: str, action: str):
    """包裝 route：回傳值包成 success，例外包成 error（400 / 404 / 500）。"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return jsonify(response.success(module, action, data=func(*args, **kwargs)))
            except FileNotFoundError as exc:
                return jsonify(response.not_found(module, action, message=str(exc))), 404
            except (ValueError, TypeError) as exc:
                return jsonify(response.error(module, action, exc)), 400
            except Exception as exc:  # noqa: BLE001
                logger.exception("%s.%s failed", module, action)
                return jsonify(response.error(module, action, exc)), 500

        return wrapper

    return decorator
