"""
Driver 登記與動態載入（對應 brain-device 的 control/loader.py）。

新增 driver 的步驟：
    1. 在 drivers/<類型>/ 寫一個繼承 core.interfaces 基底類別的 class
    2. 在下面對應的 *_DRIVERS 登記 module 與 class
    3. 在 config.py 的 SOURCES / ENCODERS / SCORERS 加一筆設定
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

import config
from core.interfaces import EncoderDriver, ScorerDriver, SourceDriver

SOURCE_DRIVERS = {
    "http_stream": {"module": "drivers.sources.http_stream", "class": "HTTPStreamSource"},
    "usb_camera": {"module": "drivers.sources.usb_camera", "class": "USBCameraSource"},
    "video_file": {"module": "drivers.sources.video_file", "class": "VideoFileSource"},
}

ENCODER_DRIVERS = {
    "vjepa2_hf": {"module": "drivers.encoders.vjepa2_hf", "class": "VJEPA2HFEncoder"},
    "remote_http": {"module": "drivers.encoders.remote_http", "class": "RemoteHTTPEncoder"},
    "dummy": {"module": "drivers.encoders.dummy", "class": "DummyEncoder"},
}

SCORER_DRIVERS = {
    "knn": {"module": "drivers.scorers.knn", "class": "KNNScorer"},
    "centroid": {"module": "drivers.scorers.centroid", "class": "CentroidScorer"},
}


def _load(registry: dict, driver_name: str, kwargs: dict | None, base_class: type, kind: str) -> Any:
    if not isinstance(driver_name, str) or not driver_name.strip():
        raise ValueError(f"{kind} driver must be a non-empty string")
    driver_name = driver_name.strip().lower()
    definition = registry.get(driver_name)
    if definition is None:
        raise ValueError(
            f"Unsupported {kind} driver: {driver_name}. "
            f"Supported: {', '.join(sorted(registry))}"
        )
    module = import_module(definition["module"])
    cls = getattr(module, definition["class"])
    instance = cls(**(kwargs or {}))
    if not isinstance(instance, base_class):
        raise RuntimeError(f"{definition['class']} must inherit {base_class.__name__}")
    return instance


def _lookup(table: dict, name: str, kind: str) -> dict:
    if name not in table:
        raise ValueError(f"Unsupported {kind}: {name}. Supported: {', '.join(sorted(table))}")
    return table[name]


def source_driver_name(entry: dict) -> str:
    """只填 url 的來源（串流 API）不需要寫 driver，預設為 http_stream。"""
    return entry.get("driver", "http_stream")


def create_source(source_name: str) -> SourceDriver:
    entry = _lookup(config.SOURCES, source_name, "source")
    if "driver" in entry:
        kwargs = entry.get("kwargs")
    else:
        kwargs = {key: value for key, value in entry.items() if key != "label"}
    return _load(SOURCE_DRIVERS, source_driver_name(entry), kwargs, SourceDriver, "source")


def create_encoder(encoder_name: str, table: dict | None = None) -> EncoderDriver:
    """table 預設為 config.ENCODERS；model server 傳入 config.MODEL_SERVER_MODELS。"""
    entry = _lookup(config.ENCODERS if table is None else table, encoder_name, "encoder")
    return _load(ENCODER_DRIVERS, entry["driver"], entry.get("kwargs"), EncoderDriver, "encoder")


def create_scorer(scorer_name: str) -> ScorerDriver:
    entry = _lookup(config.SCORERS, scorer_name, "scorer")
    return _load(SCORER_DRIVERS, entry["driver"], entry.get("kwargs"), ScorerDriver, "scorer")
