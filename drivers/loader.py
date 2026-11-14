"""
Driver 登記表（對應 brain-device 的 control/loader.py）。

只負責「driver 名稱 → class」與建立物件，不讀 config；
要用哪個 driver、參數是什麼，由 services/config_service.py 決定。

新增 driver 的步驟：
    1. 在 drivers/<類型>/ 寫一個繼承 core.interfaces 基底類別的 class
    2. 在下面對應的 *_DRIVERS 登記 module 與 class
    3. 在 config.py 加一筆設定
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

from core.interfaces import EncoderDriver, ScorerDriver, SourceDriver

SOURCE_DRIVERS = {
    "http_stream": {"module": "drivers.sources.http_stream", "class": "HTTPStreamSource"},
    "usb_camera": {"module": "drivers.sources.usb_camera", "class": "USBCameraSource"},
    "video_file": {"module": "drivers.sources.video_file", "class": "VideoFileSource"},
}

ENCODER_DRIVERS = {
    "vjepa2_hf": {"module": "drivers.encoders.vjepa2_hf", "class": "VJEPA2HFEncoder"},
    "remote_http": {"module": "drivers.encoders.remote_http", "class": "RemoteHTTPEncoder"},
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


def load_source(driver_name: str, kwargs: dict | None = None) -> SourceDriver:
    return _load(SOURCE_DRIVERS, driver_name, kwargs, SourceDriver, "source")


def load_encoder(driver_name: str, kwargs: dict | None = None) -> EncoderDriver:
    return _load(ENCODER_DRIVERS, driver_name, kwargs, EncoderDriver, "encoder")


def load_scorer(driver_name: str, kwargs: dict | None = None) -> ScorerDriver:
    return _load(SCORER_DRIVERS, driver_name, kwargs, ScorerDriver, "scorer")
