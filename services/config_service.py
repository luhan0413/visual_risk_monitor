"""
設定服務：讀取 config.py，並負責所有「由設定推算出來」的值。

config.py 只放值；路徑解析、套用預設值、組出 driver 參數、
提供給網頁的設定內容，都在這裡計算。其他模組不直接 import config。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import config
from core.interfaces import EncoderDriver, ScorerDriver, SourceDriver
from drivers import loader

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# driver 參數中，名稱以這些結尾的值視為路徑，會解析成絕對路徑
_PATH_SUFFIXES = ("_dir", "_path")
DEFAULT_STREAM_DRIVER = "http_stream"
# SOURCES 裡不屬於 driver 參數的欄位
_SOURCE_META_KEYS = ("snapshot_url",)


# ============================================================
# 基本
# ============================================================

def get(name: str) -> Any:
    """直接取得 config 的某一項（例如 get("PIPELINE")）。"""
    return getattr(config, name)


def resolve_path(value: str | Path) -> Path:
    """相對路徑一律以專案根目錄為基準。"""
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def path(key: str) -> Path:
    """config.PATHS 裡的路徑，例如 path("exemplars")。"""
    return resolve_path(config.PATHS[key])


def _resolve_kwargs(kwargs: dict[str, Any] | None) -> dict[str, Any]:
    resolved = dict(kwargs or {})
    for key, value in resolved.items():
        if key.endswith(_PATH_SUFFIXES) and isinstance(value, (str, Path)):
            resolved[key] = str(resolve_path(value))
    return resolved


def _lookup(table: dict, name: str, kind: str) -> dict:
    if name not in table:
        raise ValueError(f"Unsupported {kind}: {name}. Supported: {', '.join(sorted(table))}")
    return table[name]


# ============================================================
# 範例庫
# ============================================================

def positive_label() -> str:
    return config.EXEMPLARS["positive_label"]


def negative_label() -> str:
    return config.EXEMPLARS["negative_label"]


def exemplar_labels() -> tuple[str, str]:
    return negative_label(), positive_label()


# ============================================================
# 影像來源
# ============================================================

def source_names() -> list[str]:
    return list(config.SOURCES)


def source_driver(name: str) -> tuple[str, dict[str, Any]]:
    """回傳 (driver 名稱, 參數)。只填 url 的來源使用 http_stream，並套用 STREAM_DEFAULTS。"""
    entry = _lookup(config.SOURCES, name, "source")
    if "driver" in entry:
        return entry["driver"], _resolve_kwargs(entry.get("kwargs"))
    kwargs = {key: value for key, value in entry.items() if key not in _SOURCE_META_KEYS}
    return DEFAULT_STREAM_DRIVER, _resolve_kwargs({**config.STREAM_DEFAULTS, **kwargs})


def snapshot_url(name: str | None) -> str | None:
    """來源的拍照 API；沒有設定時回傳 None。"""
    if not name or name not in config.SOURCES:
        return None
    return config.SOURCES[name].get("snapshot_url")


def snapshot_timeout_s() -> float:
    return float(config.SNAPSHOT["timeout_s"])


def make_source(name: str) -> SourceDriver:
    driver, kwargs = source_driver(name)
    return loader.load_source(driver, kwargs)


def source_info(name: str) -> dict[str, Any]:
    entry = _lookup(config.SOURCES, name, "source")
    driver, _ = source_driver(name)
    return {
        "name": name,
        "driver": driver,
        "url": entry.get("url"),
        "snapshot_url": entry.get("snapshot_url"),
        "default": name == config.DEFAULT_SOURCE,
    }


# ============================================================
# 模型與評分
# ============================================================

def make_encoder(name: str) -> EncoderDriver:
    """主系統使用的 encoder（config.ENCODERS）。"""
    entry = _lookup(config.ENCODERS, name, "encoder")
    return loader.load_encoder(entry["driver"], _resolve_kwargs(entry.get("kwargs")))


def make_server_encoder(name: str) -> EncoderDriver:
    """Model Server 載入的模型（config.MODEL_SERVER_MODELS）。"""
    entry = _lookup(config.MODEL_SERVER_MODELS, name, "model")
    return loader.load_encoder(entry["driver"], _resolve_kwargs(entry.get("kwargs")))


def server_models() -> list[dict[str, Any]]:
    """Model Server 可用的模型清單，以及權重是否存在。"""
    items = []
    for name, entry in config.MODEL_SERVER_MODELS.items():
        model_path = _resolve_kwargs(entry.get("kwargs")).get("model_path")
        items.append({
            "name": name,
            "driver": entry["driver"],
            "model_path": model_path,
            "weights_found": None if model_path is None else Path(model_path).is_dir(),
        })
    return items


def make_scorer(name: str) -> ScorerDriver:
    entry = _lookup(config.SCORERS, name, "scorer")
    return loader.load_scorer(entry["driver"], _resolve_kwargs(entry.get("kwargs")))


def model_catalog() -> dict[str, list[str]]:
    return {"available_encoders": list(config.ENCODERS), "available_scorers": list(config.SCORERS)}


# ============================================================
# 網頁
# ============================================================

def monitor_config() -> dict[str, Any]:
    """網頁需要的設定（分級、顯示名稱、介面參數）。"""
    return {
        "levels": config.RISK["levels"],
        "smoothing_window": config.RISK["smoothing_window"],
        "scorers": config.SCORERS,
        "display_names": config.EXEMPLARS["display_names"],
        "min_per_label": config.EXEMPLARS["min_per_label"],
        "positive_label": positive_label(),
        "negative_label": negative_label(),
        "ui": config.UI,
        "pipeline": config.PIPELINE,
    }


def max_upload_bytes(section: str) -> int:
    """section："SERVER" 或 "MODEL_SERVER"。"""
    return int(getattr(config, section)["max_upload_mb"] * 1024 * 1024)


# ============================================================
# 檢查
# ============================================================

def validate() -> list[str]:
    """回傳設定上的問題（啟動時寫進 log）。"""
    problems = []
    if config.DEFAULT_SOURCE not in config.SOURCES:
        problems.append(f"DEFAULT_SOURCE={config.DEFAULT_SOURCE!r} 不在 SOURCES 裡")
    if config.DEFAULT_ENCODER not in config.ENCODERS:
        problems.append(f"DEFAULT_ENCODER={config.DEFAULT_ENCODER!r} 不在 ENCODERS 裡")
    if config.DEFAULT_SCORER not in config.SCORERS:
        problems.append(f"DEFAULT_SCORER={config.DEFAULT_SCORER!r} 不在 SCORERS 裡")
    if config.PIPELINE["frame_buffer_size"] < config.PIPELINE["clip_frames"]:
        problems.append("PIPELINE.frame_buffer_size 必須 >= clip_frames")
    default_model = config.MODEL_SERVER.get("default_model")
    if default_model and default_model not in config.MODEL_SERVER_MODELS:
        problems.append(f"MODEL_SERVER.default_model={default_model!r} 不在 MODEL_SERVER_MODELS 裡")
    return problems
