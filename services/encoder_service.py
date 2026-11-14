"""
特徵模型服務：管理目前使用的 EncoderDriver，模型在背景執行緒載入。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

import numpy as np

from core.interfaces import EncoderDriver


class EncoderService:
    def __init__(self, factory: Callable[[str], EncoderDriver]):
        self._factory = factory
        self._lock = threading.RLock()
        self._encode_lock = threading.Lock()
        self._driver: EncoderDriver | None = None
        self._name: str | None = None
        self._state = "idle"  # idle / loading / ready / error
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._load_time_s: float | None = None
        self._loaded = threading.Event()
        self.generation = 0  # 每次成功載入 +1，scoring 用來判斷範例特徵是否要重算

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def ready(self) -> bool:
        return self._state == "ready"

    def status(self) -> dict[str, Any]:
        with self._lock:
            info = {}
            if self._driver is not None and self._state == "ready":
                try:
                    info = self._driver.info()
                except Exception:  # noqa: BLE001
                    info = {}
            return {
                "name": self._name,
                "state": self._state,
                "error": self._error,
                "info": info,
                "last_latency_ms": self._last_latency_ms,
                "load_time_s": self._load_time_s,
            }

    def select(self, name: str, background: bool = True) -> dict[str, Any]:
        driver = self._factory(name)  # 名稱錯誤時直接 raise
        with self._lock:
            old = self._driver
            self._driver, self._name = None, name
            self._state, self._error = "loading", None
            self._loaded.clear()
        if old is not None:
            with self._encode_lock:
                old.unload()
        if background:
            threading.Thread(target=self._load, args=(driver, name), name="encoder-load", daemon=True).start()
        else:
            self._load(driver, name)
        return self.status()

    def unload(self) -> dict[str, Any]:
        with self._lock:
            old = self._driver
            self._driver, self._name = None, None
            self._state, self._error = "idle", None
        if old is not None:
            with self._encode_lock:
                old.unload()
        return self.status()

    def _load(self, driver: EncoderDriver, name: str) -> None:
        started = time.monotonic()
        try:
            driver.load()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                if self._name == name:
                    self._state, self._error = "error", f"{type(exc).__name__}: {exc}"
            self._loaded.set()
            return
        with self._lock:
            if self._name != name:  # 載入期間又被切換成別的模型
                driver.unload()
                return
            self._driver = driver
            self._state = "ready"
            self._load_time_s = round(time.monotonic() - started, 1)
            self.generation += 1
        self._loaded.set()

    def wait_until_loaded(self, timeout: float | None = None) -> bool:
        self._loaded.wait(timeout)
        return self.ready

    def encode(self, frames: list[np.ndarray]) -> np.ndarray:
        with self._lock:
            driver = self._driver
            if driver is None or self._state != "ready":
                raise RuntimeError(f"encoder 尚未就緒（{self._state}）")
        started = time.monotonic()
        with self._encode_lock:
            vector = driver.encode(frames)
        self._last_latency_ms = round((time.monotonic() - started) * 1000, 1)
        vector = np.asarray(vector, dtype=np.float32).reshape(-1)
        if not np.all(np.isfinite(vector)):
            raise RuntimeError("encoder 輸出包含 NaN / Inf")
        return vector
