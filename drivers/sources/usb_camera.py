"""本機 USB / UVC 相機（OpenCV）。"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from core.interfaces import SourceDriver


class USBCameraSource(SourceDriver):
    def __init__(self, device: int | str = 0, width: int | None = None, height: int | None = None):
        self.device = device
        self.width = width
        self.height = height
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> None:
        capture = cv2.VideoCapture(self.device)
        if self.width:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"無法開啟 USB 相機：{self.device}")
        self._capture = capture

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def read(self) -> np.ndarray | None:
        if self._capture is None:
            return None
        ok, image = self._capture.read()
        if not ok or image is None:
            return None
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    def status(self) -> dict[str, Any]:
        return {"device": self.device, "opened": self._capture is not None}
