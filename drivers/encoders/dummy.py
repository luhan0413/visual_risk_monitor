"""
測試用 encoder：每張影像的 HSV 顏色直方圖取平均。

不需要 GPU 與模型權重，用來驗證「來源 → 特徵 → 評分 → 介面」整條流程。
它沒有理解畫面的能力，分數不代表實際風險。
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from core.interfaces import EncoderDriver


class DummyEncoder(EncoderDriver):
    def __init__(self, bins: int = 8):
        self.bins = int(bins)

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def encode(self, frames: list[np.ndarray]) -> np.ndarray:
        if not frames:
            raise ValueError("frames must not be empty")
        histograms = []
        for image in frames:
            small = cv2.resize(image, (64, 64))
            hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
            hist = cv2.calcHist([hsv], [0, 1, 2], None, [self.bins] * 3, [0, 180, 0, 256, 0, 256])
            histograms.append(hist.flatten())
        vector = np.mean(histograms, axis=0).astype(np.float32)
        return vector / (np.linalg.norm(vector) + 1e-8)

    def info(self) -> dict[str, Any]:
        return {"dim": self.bins**3, "note": "測試用，分數不代表實際風險"}
