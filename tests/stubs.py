"""
僅供自動化測試使用的替身（不屬於系統，系統程式不會 import 這個檔案）。

StubEncoder：用顏色直方圖當作特徵，讓測試在沒有 GPU / 模型權重時也能驗證
「來源 → 特徵 → 比對 → 分級」的流程。
"""
import cv2
import numpy as np

from core.interfaces import EncoderDriver


class StubEncoder(EncoderDriver):
    def __init__(self, bins: int = 8):
        self.bins = bins

    def load(self):
        pass

    def unload(self):
        pass

    def encode(self, frames):
        if not frames:
            raise ValueError("frames must not be empty")
        histograms = []
        for image in frames:
            hsv = cv2.cvtColor(cv2.resize(image, (64, 64)), cv2.COLOR_RGB2HSV)
            hist = cv2.calcHist([hsv], [0, 1, 2], None, [self.bins] * 3, [0, 180, 0, 256, 0, 256])
            histograms.append(hist.flatten())
        vector = np.mean(histograms, axis=0).astype(np.float32)
        return vector / (np.linalg.norm(vector) + 1e-8)
