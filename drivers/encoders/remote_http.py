"""
遠端 encoder：透過 HTTP 呼叫 model server（model_server/）取得特徵。

主系統用這個 driver 時，本身不載入任何模型、不需要 GPU。
model server 可以跑在同一台，也可以跑在另一台 GPU 主機，只要改 base_url。
"""
from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np
import requests

from core.interfaces import EncoderDriver

API_PREFIX = "/api/model_server"


class RemoteHTTPEncoder(EncoderDriver):
    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_s: float = 10.0,
        load_timeout_s: float = 300.0,
        connect_wait_s: float = 60.0,
        resize_short_side: int | None = 320,
        jpeg_quality: int = 90,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_s = float(timeout_s)
        self.load_timeout_s = float(load_timeout_s)
        self.connect_wait_s = float(connect_wait_s)
        self.resize_short_side = resize_short_side
        self.jpeg_quality = int(jpeg_quality)
        self._session = requests.Session()
        self._server_info: dict[str, Any] = {}

    # ---------- HTTP ----------

    def _url(self, action: str) -> str:
        return f"{self.base_url}{API_PREFIX}/{action}"

    def _call(self, method: str, action: str, timeout: float | None = None, **kwargs) -> Any:
        reply = self._session.request(method, self._url(action), timeout=timeout or self.timeout_s, **kwargs)
        try:
            payload = reply.json()
        except ValueError:
            reply.raise_for_status()
            raise RuntimeError(f"model server 回傳格式錯誤（HTTP {reply.status_code}）")
        if payload.get("status") != "success":
            raise RuntimeError(f"model server：{payload.get('message', payload.get('status'))}")
        return payload.get("data")

    def _status(self) -> dict[str, Any]:
        return self._call("GET", "get_status")

    # ---------- EncoderDriver ----------

    def load(self) -> None:
        # 1. 等 model server 啟動（兩個服務同時啟動時，主系統可能比較快）
        deadline = time.monotonic() + self.connect_wait_s
        while True:
            try:
                status = self._status()
                break
            except requests.RequestException as exc:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"無法連線 model server {self.base_url}：{exc}") from exc
                time.sleep(1.0)

        # 2. 需要時請 model server 載入指定模型
        if status["model"]["name"] != self.model_name or status["model"]["state"] == "error":
            self._call("POST", "load_model", json={"model_name": self.model_name})

        # 3. 等待載入完成
        deadline = time.monotonic() + self.load_timeout_s
        while True:
            model = self._status()["model"]
            if model["name"] != self.model_name:
                raise RuntimeError(f"model server 目前載入的是 {model['name']}，不是 {self.model_name}")
            if model["state"] == "ready":
                self._server_info = model.get("info") or {}
                return
            if model["state"] == "error":
                raise RuntimeError(f"model server 載入失敗：{model.get('error')}")
            if time.monotonic() > deadline:
                raise RuntimeError("等待 model server 載入模型逾時")
            time.sleep(1.0)

    def unload(self) -> None:
        # model server 可能同時服務其他系統，這裡只中斷自己的連線，不卸載遠端模型
        self._server_info = {}

    def _encode_jpeg(self, image: np.ndarray) -> bytes:
        if self.resize_short_side:
            height, width = image.shape[:2]
            scale = self.resize_short_side / min(height, width)
            if scale < 1:
                image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR),
                                   [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            raise RuntimeError("JPEG 編碼失敗")
        return encoded.tobytes()

    def encode(self, frames: list[np.ndarray]) -> np.ndarray:
        if not frames:
            raise ValueError("frames must not be empty")
        files = [("frames", (f"{i:03d}.jpg", self._encode_jpeg(image), "image/jpeg")) for i, image in enumerate(frames)]
        data = self._call("POST", "encode", files=files, data={"model_name": self.model_name})
        return np.asarray(data["embedding"], dtype=np.float32)

    def info(self) -> dict[str, Any]:
        return {"base_url": self.base_url, "model_name": self.model_name, **self._server_info}
